"""Shared REST/MCP email operations under the effective human's CRM authority."""

import uuid
from datetime import UTC, datetime
from functools import lru_cache

from pydantic import TypeAdapter

wire = TypeAdapter(dict).dump_python

from src.crm.google_workspace.config import google_workspace_enabled
from src.crm.google_workspace.service import GoogleWorkspaceService
from src.crm.repositories.errors import ResourceConflict, ResourceNotFound
from src.crm.services.operations import AccessDenied, ServiceUnavailable, validated_model

from .gmail import GmailEmails, fingerprint, source_key
from .models import (
    EmailQuery,
    FollowUp,
    GmailConversationImport,
    GmailConversationPreview,
    GmailImport,
    GmailMessagePreview,
    GmailSearch,
    ManualEmailCreate,
    SyncChoice,
)
from .store import INTERACTION, LEAD


@lru_cache(maxsize=1)
def configured_google():
    try:
        return GoogleWorkspaceService()
    except RuntimeError as exc:
        raise ServiceUnavailable("Google integration is not configured") from exc


class EmailOperations:
    def __init__(self, context, *, resources, store=None, google=None):
        self.context, self.resources = context, resources
        self.store = store if store is not None else resources.emails
        self._google = google

    @property
    def gmail(self):
        if not google_workspace_enabled():
            raise ServiceUnavailable("Google Workspace is disabled")
        return GmailEmails(self._google if self._google is not None else configured_google())

    def _require(self, *capabilities):
        for cap in capabilities:
            self.context.require(cap)

    def _context(self, command):
        contact = self.resources.detail("contacts", command.contact_uid)
        if contact.get("archived_at"):
            raise ResourceConflict("Select an active Contact")
        result = {"contact_uid": str(command.contact_uid), "contact_version": contact["version"],
                  "company_uid": str(command.company_uid) if command.company_uid else None,
                  "deal_uid": str(command.deal_uid) if command.deal_uid else None}
        if command.lead_uid:
            from src.crm.solution_selling.config import solution_selling_enabled
            if not solution_selling_enabled():
                raise ResourceNotFound("Leads are unavailable")
            rows = self.store.query(f'SELECT contact_uid, version, archived_at FROM "{LEAD}" WHERE uid=%(uid)s::uuid', {"uid": str(command.lead_uid)})
            if not rows or rows[0].get("archived_at") or str(rows[0]["contact_uid"]) != str(command.contact_uid):
                raise ResourceConflict("Select an active Lead for this Contact")
            if rows[0]["version"] != command.expected_lead_version:
                raise ResourceConflict("Lead changed; review the current version")
            result.update(lead_uid=str(command.lead_uid), expected_lead_version=command.expected_lead_version)
        if command.company_uid and self.resources.detail("companies", command.company_uid).get("archived_at"):
            raise ResourceConflict("Select an active Company")
        if command.deal_uid:
            deal = self.resources.detail("deals", command.deal_uid)
            if deal.get("archived_at") or not command.company_uid or str(deal["company_uid"]) != str(command.company_uid):
                raise ValueError("Select the Deal's Company")
        if command.interaction_uid:
            rows = self.store.query(f'SELECT * FROM "{INTERACTION}" WHERE uid=%(uid)s::uuid', {"uid": str(command.interaction_uid)})
            if not rows:
                raise ResourceNotFound("Interaction not found")
            interaction = rows[0]
            people = self.store._json(interaction["participants"], expected=list, label="participants")
            if (interaction.get("archived_at") or interaction["kind"] != "email" or
                str(command.contact_uid) not in {str(p.get("contact_uid")) for p in people} or
                any(str(interaction.get(k) or "") != str(result.get(k) or "") for k in ("company_uid", "deal_uid"))):
                raise ResourceConflict("Select an active email Interaction with the same people and context")
            result.update(interaction_uid=str(command.interaction_uid), interaction_version=interaction["version"])
        return result

    def list(self, payload):
        self._require("crm.read")
        return self.store.collection(validated_model(EmailQuery, payload))

    def get(self, uid):
        self._require("crm.read")
        item = self.store.detail(uid)
        thread = self.store.thread(item["thread_uid"])
        item["thread"] = {key: thread[key] for key in ("uid", "version", "actor_uid", "sync_enabled", "sync_after_ms", "last_synced_at")}
        item["audience"] = "shared_crm_readers"
        item["thread"]["can_manage_sync"] = str(thread["actor_uid"]) == str(self.context.actor_uid) and bool(thread["provider_thread_id"])
        item["follow_up"] = self.store.open_task(uid)
        return wire(item, mode="json")

    def create(self, payload):
        self._require("crm.read", "crm.create")
        command = validated_model(ManualEmailCreate, payload)
        context = self._context(command)
        message = command.model_dump(mode="json", exclude={"contact_uid", "company_uid", "deal_uid", "interaction_uid", "lead_uid", "expected_lead_version"})
        message["uid"] = str(uuid.uuid4())
        self.store.persist(self.context.actor_uid, context, [message], source_key=uuid.uuid4().hex, source="manual")
        return self.get(message["uid"])

    def search(self, payload):
        self._require("crm.read", "crm.transfer.import")
        return self.gmail.search(self.context.actor_uid, validated_model(GmailSearch, payload))

    def preview(self, payload):
        self._require("crm.read", "crm.transfer.import")
        command = validated_model(GmailMessagePreview, payload)
        return self.gmail.preview(self.context.actor_uid, command, self._context(command))

    def preview_conversation(self, payload):
        self._require("crm.read", "crm.transfer.import")
        command = validated_model(GmailConversationPreview, payload)
        context = self._context(command)
        return self.gmail.conversation_preview(self.context.actor_uid, command, context)

    def import_conversation(self, payload):
        self._require("crm.read", "crm.transfer.import", "crm.create")
        command = validated_model(GmailConversationImport, payload)
        context = self._context(command)
        gmail, actor = self.gmail, self.context.actor_uid
        access, grant = gmail.oauth.access_token(actor, "gmail")
        try:
            review = gmail.oauth.sealer.open(command.review_token, purpose="email-conversation-review", uid=uuid.UUID(str(grant["uid"])), actor_uid=actor)
        except Exception as exc:
            raise ResourceConflict("Conversation review is unavailable; review it again") from exc
        if (review["google_sub"] != grant["google_sub"] or review["expires_at"] <= int(datetime.now(UTC).timestamp())
                or review["context"] != context):
            raise ResourceConflict("Review expired or CRM context changed; review the conversation again")
        if not set(command.message_ids).issubset(review["hashes"]):
            raise ResourceConflict("Only messages on the reviewed page may be imported")
        messages = []
        for identifier in command.message_ids:
            message = gmail.message(access, identifier, grant)
            if message["provider_thread_id"] != review["thread_id"] or fingerprint(message) != review["hashes"][identifier]:
                raise ResourceConflict("A selected message changed; review the conversation again")
            messages.append(message)
        key = source_key(actor, grant["google_sub"])
        thread = self.store.source_thread(key, review["thread_id"])
        if thread:
            original = self.store.query(f'SELECT company_uid, deal_uid, archived_at, version FROM "{INTERACTION}" WHERE uid=%(uid)s::uuid', {"uid": str(thread["interaction_uid"])})[0]
            if (thread.get("archived_at") or original.get("archived_at") or str(thread["contact_uid"]) != context["contact_uid"]
                    or (command.interaction_uid and str(thread["interaction_uid"]) != str(command.interaction_uid))
                    or any(str(original.get(k) or "") != str(context.get(k) or "") for k in ("company_uid", "deal_uid"))):
                raise ResourceConflict("This source conversation already has different CRM context")
            context["interaction_version"] = original["version"]
        for message in messages:
            existing = self.store.source_message(key, message["provider_message_id"])
            if existing and self.store.detail(existing).get("archived_at"):
                raise ResourceConflict("A selected message was archived; review saved history")
            message["uid"] = str(uuid.uuid4())
        self._require("crm.read", "crm.transfer.import", "crm.create")
        thread_uid = self.store.persist(actor, context, messages, source_key=key, source="gmail", provider_thread_id=review["thread_id"], thread=thread, grant=grant)
        saved = [self.get(self.store.source_message(key, m["provider_message_id"])) for m in messages]
        return {"items": [{key: item[key] for key in ("uid", "provider_message_id", "subject", "sent_at")} for item in saved], "thread_uid": thread_uid, "interaction_uid": saved[0]["interaction_uid"],
                "lead_uid": str(command.lead_uid) if command.lead_uid else None, "audience": command.audience,
                "sync_enabled": saved[0]["thread"]["sync_enabled"]}

    def import_message(self, payload):
        self._require("crm.read", "crm.transfer.import", "crm.create")
        command = validated_model(GmailImport, payload)
        context = self._context(command)
        gmail = self.gmail
        actor = self.context.actor_uid
        access, grant = gmail.oauth.access_token(actor, "gmail")
        try:
            token = gmail.oauth.sealer.open(command.preview_token, purpose="email-preview", uid=uuid.UUID(str(grant["uid"])), actor_uid=actor)
        except Exception as exc:
            raise ResourceConflict("Email preview is unavailable; review it again") from exc
        if token["google_sub"] != grant["google_sub"] or token["expires_at"] <= int(datetime.now(UTC).timestamp()) or token["context"] != context:
            raise ResourceConflict("Email preview expired or account changed")
        message = gmail.message(access, token["message_id"], grant)
        if fingerprint(message) != token["hash"]:
            raise ResourceConflict("Email changed; review it again")
        key = source_key(actor, grant["google_sub"])
        existing = self.store.source_message(key, message["provider_message_id"])
        if existing:
            item = self.get(existing)
            if item.get("archived_at") or (command.interaction_uid and str(item["interaction_uid"]) != str(command.interaction_uid)) or any(str(item.get(k) or "") != str(context.get(k) or "") for k in ("contact_uid", "company_uid", "deal_uid")):
                raise ResourceConflict("This message is already captured with different or archived CRM context")
            if command.lead_uid and str(command.lead_uid) not in item["lead_uids"]:
                thread = self.store.thread(item["thread_uid"])
                self.store.persist(actor, context, [], source_key=key, source="gmail", thread=thread, grant=grant)
                return self.get(existing)
            return wire(item, mode="json")
        thread = self.store.source_thread(key, message["provider_thread_id"])
        if thread:
            original = self.store.query(f'SELECT company_uid, deal_uid, version FROM "{INTERACTION}" WHERE uid=%(uid)s::uuid', {"uid": str(thread["interaction_uid"])})[0]
            if str(thread["contact_uid"]) != context["contact_uid"] or (command.interaction_uid and str(thread["interaction_uid"]) != str(command.interaction_uid)) or any(str(original.get(k) or "") != str(context.get(k) or "") for k in ("company_uid", "deal_uid")):
                raise ResourceConflict("This conversation is already linked to different CRM context")
            context["interaction_version"] = original["version"]
        message["uid"] = str(uuid.uuid4())
        self._require("crm.read", "crm.transfer.import", "crm.create")
        self.store.persist(actor, context, [message], source_key=key, source="gmail", provider_thread_id=message["provider_thread_id"], thread=thread, grant=grant)
        return self.get(message["uid"])

    def choose_sync(self, thread_uid, payload):
        command = validated_model(SyncChoice, payload)
        self._require("crm.read", "crm.edit")
        thread = self.store.thread(thread_uid)
        if str(thread["actor_uid"]) != str(self.context.actor_uid):
            raise AccessDenied("Only the mailbox owner can change synchronization")
        if thread["version"] != command.expected_version:
            raise ResourceConflict("Conversation changed; read it again")
        grant = None
        if command.enabled:
            self._require("crm.transfer.import", "crm.create")
            _access, grant = self.gmail.oauth.access_token(self.context.actor_uid, "gmail")
            if source_key(self.context.actor_uid, grant["google_sub"]) != thread["source_key"]:
                raise ResourceConflict("Connect the account that owns this thread")
        updated = self.store.set_sync(self.context.actor_uid, thread, command.enabled, grant)
        return wire({key: updated[key] for key in ("uid", "version", "sync_enabled", "sync_after_ms", "last_synced_at")}, mode="json")

    def sync(self, thread_uid):
        self._require("crm.read", "crm.transfer.import", "crm.create", "crm.edit")
        thread = self.store.thread(thread_uid)
        actor = self.context.actor_uid
        if str(thread["actor_uid"]) != str(actor):
            raise AccessDenied("Only the mailbox owner can sync this conversation")
        if not thread["sync_enabled"] or thread.get("archived_at"):
            raise ResourceConflict("Explicitly enable sync for this conversation first")
        def authorize_body(grant):
            self._require("crm.transfer.import")
            self.store.validate_selection(actor, thread, grant)
        messages, grant, has_more = self.gmail.selected_thread(actor, thread, self.store.known_message_ids(thread_uid), authorize_body)
        # Recheck permissions after external I/O, and fence selection/grant again in SQL.
        self._require("crm.read", "crm.transfer.import", "crm.create", "crm.edit")
        contact = self.resources.detail("contacts", thread["contact_uid"])
        for item in messages:
            item["uid"] = str(uuid.uuid4())
        self.store.persist(actor, {"contact_uid": str(thread["contact_uid"]), "contact_version": contact["version"]}, messages,
                           source_key=thread["source_key"], source="gmail", thread=thread, grant=grant, selected_only=True)
        updated = self.store.thread(thread_uid)
        return wire({"uid": updated["uid"], "version": updated["version"], "last_synced_at": updated["last_synced_at"], "has_more": has_more}, mode="json")

    def sync_selected(self):
        self._require("crm.read", "crm.transfer.import", "crm.create", "crm.edit")
        results = []
        for thread in self.store.selected(self.context.actor_uid):
            try:
                results.append({**self.sync(thread["uid"]), "status": "checked"})
            except ResourceConflict:
                results.append({"uid": thread["uid"], "status": "needs_attention"})
        return {"items": results}

    def follow_up(self, uid, payload):
        command = validated_model(FollowUp, payload)
        self._require("crm.read", "crm.edit")
        email = self.store.detail(uid)
        existing = self.store.open_task(uid)
        if existing and not command.existing_task_uid:
            command = command.model_copy(update={"existing_task_uid": existing["uid"], "expected_task_version": existing["version"]})
        if not command.existing_task_uid:
            self._require("crm.create")
        if command.owner_uid and not self.context.directory.is_selectable(command.owner_uid):
            raise ValueError("Select an available owner")
        task_uid = self.store.follow_up(self.context.actor_uid, email, command)
        return self.resources.detail("tasks", task_uid)
