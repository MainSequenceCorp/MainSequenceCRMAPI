"""Governed email queries and atomic conversation/message/audit commands."""

import json
import uuid

from sqlalchemy import String, cast, func, or_, select

from src.erp.collections import page_result, read_page

from src.erp.crm.repositories.errors import ResourceConflict, ResourceNotFound
from src.erp.crm.repositories.gateway import GovernedGateway
from src.erp.module_access.collections import collection_admission

from .models import EmailQuery

THREAD = "mainsequence_crm__email_thread"
MESSAGE = "mainsequence_crm__email_message"
CONTACT = "mainsequence_crm__contact"
INTERACTION = "mainsequence_crm__interaction"
GRANT = "mainsequence_crm__google_oauth_connection"
AUDIT = "mainsequence_crm__activity_event"
LEAD = "mainsequence_crm__solution_selling_lead"
LEAD_LINK = "mainsequence_crm__email_lead_link"


class EmailStore(GovernedGateway):
    def query(self, sql, parameters=None, *, mutation=False, types=None, max_rows=100):
        result = self._operation(operation="insert" if mutation else "select", sql=sql,
                                 parameters=parameters or {}, parameter_types=types or {}, max_rows=max_rows)
        return result["rows"]

    def thread(self, uid):
        rows = self.query(f'SELECT * FROM "{THREAD}" WHERE uid=%(uid)s::uuid', {"uid": str(uid)})
        if not rows:
            raise ResourceNotFound("Email conversation not found")
        return rows[0]

    def source_thread(self, source_key, provider_thread_id):
        rows = self.query(f'SELECT * FROM "{THREAD}" WHERE source_key=%(key)s AND provider_thread_id=%(id)s',
                          {"key": source_key, "id": provider_thread_id})
        return rows[0] if rows else None

    def source_message(self, source_key, message_id):
        rows = self.query(f'SELECT uid FROM "{MESSAGE}" WHERE source_key=%(key)s AND provider_message_id=%(id)s',
                          {"key": source_key, "id": message_id})
        return rows[0]["uid"] if rows else None

    def detail(self, uid):
        rows = self.query(f'SELECT e.*, t.contact_uid, t.interaction_uid, i.company_uid, i.deal_uid '
                          f'FROM "{MESSAGE}" e JOIN "{THREAD}" t ON t.uid=e.thread_uid '
                          f'JOIN "{INTERACTION}" i ON i.uid=t.interaction_uid WHERE e.uid=%(uid)s::uuid', {"uid": str(uid)})
        if not rows:
            raise ResourceNotFound("Email not found")
        item = rows[0]
        item["lead_uids"] = [str(r["lead_uid"]) for r in self.query(
            f'SELECT lead_uid FROM "{LEAD_LINK}" WHERE interaction_uid=%(uid)s::uuid AND archived_at IS NULL',
            {"uid": str(item["interaction_uid"])})]
        item["possible_duplicate"] = bool(item.get("rfc_message_id") and self.query(
            f'SELECT uid FROM "{MESSAGE}" WHERE rfc_message_id=%(rfc)s AND source_key<>%(key)s AND archived_at IS NULL LIMIT 1',
            {"rfc": item["rfc_message_id"], "key": item["source_key"]}))
        return item

    def collection(self, query: EmailQuery):
        pending = collection_admission.get()
        if pending is not None and pending.local:
            return self._sqlite_collection(query)
        clauses = ["e.archived_at IS NULL", "t.archived_at IS NULL", "i.archived_at IS NULL"]
        params = {"limit": query.page_size, "offset": query.page_index * query.page_size}
        for key, value in query.filters.model_dump(exclude_none=True).items():
            if key == "lead_uid":
                clauses.append(f'EXISTS (SELECT 1 FROM "{LEAD_LINK}" l WHERE l.interaction_uid=t.interaction_uid AND l.lead_uid=%(lead_uid)s::uuid AND l.archived_at IS NULL)')
                params[key] = str(value)
                continue
            alias = "i" if key in {"company_uid", "deal_uid"} else "e" if key == "thread_uid" else "t"
            clauses.append(f'{alias}."{key}"=%({key})s::uuid')
            params[key] = str(value)
        if query.search:
            text = query.search.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params["search"] = "%" + text + "%"
            clauses.append("lower(concat(e.subject, ' ', e.sender::text, ' ', e.\"to\"::text, ' ', e.cc::text, ' ', e.body_text)) LIKE %(search)s")
        field = query.ordering.removeprefix("-")
        direction = "DESC" if query.ordering.startswith("-") else "ASC"
        projection = "e.uid, e.version, e.thread_uid, e.sender, e.subject, e.sent_at, e.source, e.body_state, e.original_url, e.created_by_uid, t.actor_uid AS mailbox_owner_uid, t.sync_enabled, t.contact_uid, t.interaction_uid, i.company_uid, i.deal_uid"
        result = self._collection_operation(f'WITH filtered AS (SELECT {projection} FROM "{MESSAGE}" e '
                          f'JOIN "{THREAD}" t ON t.uid=e.thread_uid JOIN "{INTERACTION}" i ON i.uid=t.interaction_uid '
                          f'WHERE {" AND ".join(clauses)}), paged AS (SELECT * FROM filtered '
                          f'ORDER BY "{field}" {direction} NULLS LAST, uid LIMIT %(limit)s OFFSET %(offset)s) '
                          f'SELECT COALESCE((SELECT jsonb_agg(to_jsonb(p) ORDER BY p."{field}" {direction} NULLS LAST, p.uid) FROM paged p), \'[]\'::jsonb) AS items, '
                          '(SELECT count(*) FROM filtered) AS total_items', params, {})
        row = result["rows"][0]
        return page_result(
            self._json(row["items"], expected=list, label="emails"),
            int(row["total_items"]),
            query.page_index,
            query.page_size,
        )

    def _sqlite_collection(self, query):
        from src.erp.crm.base_adoption.reads import table

        msg, thread, interaction, links = (
            table(name)
            for name in ("email_message", "email_thread", "interaction", "email_lead_link")
        )
        predicate = [
            msg.c.archived_at.is_(None),
            thread.c.archived_at.is_(None),
            interaction.c.archived_at.is_(None),
        ]
        for name, value in query.filters.model_dump(exclude_none=True).items():
            if name == "lead_uid":
                predicate.append(
                    select(links.c.uid)
                    .where(
                        links.c.interaction_uid == thread.c.interaction_uid,
                        links.c.lead_uid == value,
                        links.c.archived_at.is_(None),
                    )
                    .exists()
                )
                continue
            relation = (
                interaction
                if name in {"company_uid", "deal_uid"}
                else msg
                if name == "thread_uid"
                else thread
            )
            predicate.append(relation.c[name] == value)
        if query.search:
            term = (
                query.search.casefold()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            predicate.append(
                or_(
                    *(
                        func.lower(cast(msg.c[name], String)).like(f"%{term}%", escape="\\")
                        for name in ("subject", "sender", "to", "cc", "body_text")
                    )
                )
            )
        joined = msg.join(thread, thread.c.uid == msg.c.thread_uid).join(
            interaction, interaction.c.uid == thread.c.interaction_uid
        )
        key = query.ordering.removeprefix("-")
        ordering = msg.c[key].desc() if query.ordering.startswith("-") else msg.c[key].asc()
        return read_page(
            self,
            msg,
            predicate,
            (ordering.nulls_last(), msg.c.uid),
            page_index=query.page_index,
            page_size=query.page_size,
            match_from=joined,
            from_clause=joined,
            projection=(
                msg.c.uid, msg.c.version, msg.c.thread_uid, msg.c.sender, msg.c.subject,
                msg.c.sent_at, msg.c.source, msg.c.body_state, msg.c.original_url,
                msg.c.created_by_uid, thread.c.actor_uid.label("mailbox_owner_uid"),
                thread.c.sync_enabled, thread.c.contact_uid, thread.c.interaction_uid,
                interaction.c.company_uid, interaction.c.deal_uid,
            ),
        )

    def persist(self, actor, context, messages, *, source_key, source, provider_thread_id=None,
                thread=None, grant=None, selected_only=False):
        """One statement: fenced parent, messages, and final audit INSERT. No replay receipt."""
        thread_uid = str(thread["uid"] if thread else uuid.uuid4())
        interaction_uid = str(thread["interaction_uid"] if thread else uuid.uuid4())
        params = {"actor": str(actor), "contact": str(context["contact_uid"]),
                  "contact_version": context["contact_version"], "company": context.get("company_uid"),
                  "deal": context.get("deal_uid"), "key": source_key, "source": source,
                  "thread": thread_uid, "interaction": interaction_uid, "provider_thread": provider_thread_id,
                  "messages": json.dumps(messages, default=str), "subject": (messages[0]["subject"] if messages else "Email conversation")[:255] or "Email conversation",
                  "participants": json.dumps([{"contact_uid": str(context["contact_uid"]), "role": "attendee"}]),
                  "command": str(uuid.uuid4()), "event": str(uuid.uuid4()), "origin": "import" if source == "gmail" else "live",
                  "occurred": messages[0].get("sent_at") if messages else None}
        guard = f'SELECT c.uid FROM "{CONTACT}" c WHERE c.uid=%(contact)s::uuid AND c.archived_at IS NULL AND c.version=%(contact_version)s'
        if context.get("lead_uid"):
            params.update(lead=context["lead_uid"], lead_version=context["expected_lead_version"], link=str(uuid.uuid4()))
            guard += (f' AND EXISTS (SELECT 1 FROM "{LEAD}" l WHERE l.uid=%(lead)s::uuid '
                      'AND l.contact_uid=c.uid AND l.version=%(lead_version)s AND l.archived_at IS NULL FOR SHARE)')
        for name, table in (("company", "mainsequence_crm__company"), ("deal", "mainsequence_crm__deal")):
            if context.get(name + "_uid"):
                relation = ' AND p.company_uid=%(company)s::uuid' if name == "deal" else ""
                guard += f' AND EXISTS (SELECT 1 FROM "{table}" p WHERE p.uid=%({name})s::uuid AND p.archived_at IS NULL{relation} FOR SHARE)'
        if grant:
            params.update(grant_uid=str(grant["uid"]), grant_version=grant["version"], google_sub=grant["google_sub"])
            guard += (f' AND EXISTS (SELECT 1 FROM "{GRANT}" g WHERE g.uid=%(grant_uid)s::uuid '
                      "AND g.actor_uid=%(actor)s::uuid AND g.google_sub=%(google_sub)s AND g.version=%(grant_version)s "
                      "AND g.status='connected' AND g.granted_scopes @> '[\"https://www.googleapis.com/auth/gmail.readonly\"]'::jsonb FOR SHARE)")
        if thread:
            params["interaction"] = str(thread["interaction_uid"])
            params["parent_version"] = context.get("interaction_version")
            guard += (f' AND EXISTS (SELECT 1 FROM "{INTERACTION}" i WHERE i.uid=%(interaction)s::uuid '
                      "AND i.archived_at IS NULL AND i.kind='email' AND i.participants @> jsonb_build_array(jsonb_build_object('contact_uid', %(contact)s::text)) "
                      "AND (%(parent_version)s::bigint IS NULL OR i.version=%(parent_version)s) FOR SHARE)")
            params["thread_version"] = thread["version"]
            select_guard = " AND target.sync_enabled AND target.actor_uid=%(actor)s::uuid" if selected_only else ""
            changed_thread = (f'changed_thread AS (UPDATE "{THREAD}" target SET version=target.version+1, updated_at=NOW(), '
                              "updated_by_uid=%(actor)s::uuid" + (", last_synced_at=NOW()" if selected_only else "") +
                              " FROM gate WHERE target.uid=%(thread)s::uuid AND target.version=%(thread_version)s AND target.archived_at IS NULL" +
                              select_guard + " RETURNING target.uid)")
            parent_ctes = changed_thread
        else:
            if context.get("interaction_uid"):
                interaction_uid = str(context["interaction_uid"])
                params["interaction"] = interaction_uid
                params["interaction_version"] = context["interaction_version"]
                interaction_cte = (f'new_interaction AS (SELECT i.uid FROM "{INTERACTION}" i CROSS JOIN gate WHERE i.uid=%(interaction)s::uuid '
                                   "AND i.version=%(interaction_version)s AND i.kind='email' AND i.archived_at IS NULL FOR SHARE OF i)")
            else:
                interaction_cte = (f'new_interaction AS (INSERT INTO "{INTERACTION}" (uid, created_at, updated_at, created_by_uid, updated_by_uid, version, '
                                   "company_uid, deal_uid, participants, subject, kind, status, occurred_at) SELECT %(interaction)s::uuid, NOW(), NOW(), "
                                   "%(actor)s::uuid, %(actor)s::uuid, 1, %(company)s::uuid, %(deal)s::uuid, %(participants)s::jsonb, %(subject)s, 'email', 'completed', %(occurred)s::timestamptz FROM gate RETURNING uid)")
            parent_ctes = (interaction_cte + ", " +
                           f'changed_thread AS (INSERT INTO "{THREAD}" (uid, created_at, updated_at, created_by_uid, updated_by_uid, version, '
                           "contact_uid, interaction_uid, actor_uid, source_key, provider_thread_id, sync_enabled) SELECT %(thread)s::uuid, NOW(), NOW(), "
                           "%(actor)s::uuid, %(actor)s::uuid, 1, %(contact)s::uuid, n.uid, %(actor)s::uuid, %(key)s, %(provider_thread)s, false FROM new_interaction n RETURNING uid)")
        eligible = " AND (m->>'internal_date_ms')::bigint >= %(sync_after)s" if selected_only else ""
        if selected_only:
            params["sync_after"] = thread["sync_after_ms"]
        link_cte = ""
        if context.get("lead_uid"):
            link_cte = (f'linked AS (INSERT INTO "{LEAD_LINK}" (uid, created_at, updated_at, created_by_uid, updated_by_uid, version, interaction_uid, lead_uid) '
                        'SELECT %(link)s::uuid, NOW(), NOW(), %(actor)s::uuid, %(actor)s::uuid, 1, %(interaction)s::uuid, %(lead)s::uuid FROM changed_thread '
                        'ON CONFLICT (interaction_uid, lead_uid) DO NOTHING RETURNING uid), ')
        guard += " FOR SHARE OF c"
        sql = (f'WITH gate AS ({guard}), {parent_ctes}, '
               + link_cte +
               f'added AS (INSERT INTO "{MESSAGE}" (uid, created_at, updated_at, created_by_uid, updated_by_uid, version, thread_uid, source_key, source, '
               'provider_message_id, rfc_message_id, sender, "to", cc, subject, sent_at, internal_date_ms, body_text, body_state, original_url) '
               "SELECT (m->>'uid')::uuid, NOW(), NOW(), %(actor)s::uuid, %(actor)s::uuid, 1, changed_thread.uid, %(key)s, %(source)s, "
               "m->>'provider_message_id', m->>'rfc_message_id', m->'sender', m->'to', m->'cc', m->>'subject', (m->>'sent_at')::timestamptz, "
               "(m->>'internal_date_ms')::bigint, m->>'body_text', m->>'body_state', m->>'original_url' "
               "FROM changed_thread CROSS JOIN jsonb_array_elements(%(messages)s::jsonb) m WHERE true" + eligible +
               " ON CONFLICT (source_key, provider_message_id) DO NOTHING RETURNING uid) "
               f'INSERT INTO "{AUDIT}" (uid, entity_type, entity_uid, kind, occurred_at, recorded_at, actor_uid, origin, command_uid, summary, changes) '
               "SELECT %(event)s::uuid, 'contact', %(contact)s::uuid, 'email_captured', NOW(), NOW(), %(actor)s::uuid, %(origin)s, %(command)s::uuid, "
               "'Saved email history', jsonb_build_object('messages_added', (SELECT count(*) FROM added), 'thread_uid', changed_thread.uid, "
               "'lead_uid', %(audit_lead)s::text, 'audience', 'shared_crm_readers') FROM changed_thread RETURNING entity_uid")
        params["audit_lead"] = context.get("lead_uid")
        rows = self.query(sql, params, mutation=True, types={"messages": "jsonb", "participants": "jsonb"})
        if not rows:
            raise ResourceConflict("Email context or selected sync changed; read the saved version")
        return thread_uid

    def set_sync(self, actor, thread, enabled, grant=None):
        params = {"uid": str(thread["uid"]), "actor": str(actor), "version": thread["version"], "enabled": enabled,
                  "event": str(uuid.uuid4()), "command": str(uuid.uuid4())}
        guard = ""
        if enabled:
            params.update(grant_uid=str(grant["uid"]), google_sub=grant["google_sub"], grant_version=grant["version"])
            guard = (f' AND EXISTS (SELECT 1 FROM "{GRANT}" g WHERE g.uid=%(grant_uid)s::uuid AND g.actor_uid=%(actor)s::uuid '
                     "AND g.google_sub=%(google_sub)s AND g.version=%(grant_version)s AND g.status='connected')")
        sql = (f'WITH changed AS (UPDATE "{THREAD}" SET sync_enabled=%(enabled)s, '
               "sync_after_ms=CASE WHEN %(enabled)s AND NOT sync_enabled THEN (extract(epoch FROM NOW()) * 1000)::bigint ELSE sync_after_ms END, "
               "version=version+1, updated_at=NOW(), updated_by_uid=%(actor)s::uuid "
               "WHERE uid=%(uid)s::uuid AND actor_uid=%(actor)s::uuid AND version=%(version)s AND archived_at IS NULL "
               "AND provider_thread_id IS NOT NULL" + guard + " RETURNING uid, contact_uid) "
               f'INSERT INTO "{AUDIT}" (uid, entity_type, entity_uid, kind, occurred_at, recorded_at, actor_uid, origin, command_uid, summary, changes) '
               "SELECT %(event)s::uuid, 'contact', contact_uid, 'email_sync_selection', NOW(), NOW(), %(actor)s::uuid, 'live', %(command)s::uuid, "
               "'Changed selected email synchronization', jsonb_build_object('thread_uid', uid, 'enabled', %(enabled)s) FROM changed RETURNING entity_uid")
        if not self.query(sql, params, mutation=True):
            raise ResourceConflict("Email sync selection changed; read the saved version")
        return self.thread(thread["uid"])

    def selected(self, actor):
        return self.query(f'SELECT * FROM "{THREAD}" WHERE actor_uid=%(actor)s::uuid AND sync_enabled AND archived_at IS NULL '
                          'ORDER BY last_synced_at NULLS FIRST, uid LIMIT 5', {"actor": str(actor)})

    def validate_selection(self, actor, thread, grant):
        rows = self.query(f'SELECT t.uid FROM "{THREAD}" t JOIN "{GRANT}" g ON g.uid=%(grant)s::uuid '
                          "WHERE t.uid=%(thread)s::uuid AND t.actor_uid=%(actor)s::uuid AND t.version=%(version)s "
                          "AND t.sync_enabled AND t.archived_at IS NULL AND g.actor_uid=%(actor)s::uuid "
                          "AND g.version=%(grant_version)s AND g.status='connected' "
                          "AND g.granted_scopes @> '[\"https://www.googleapis.com/auth/gmail.readonly\"]'::jsonb",
                          {"grant": str(grant["uid"]), "thread": str(thread["uid"]), "actor": str(actor),
                           "version": thread["version"], "grant_version": grant["version"]})
        if not rows:
            raise ResourceConflict("Selected thread or Google connection changed")

    def known_message_ids(self, thread_uid):
        return {r["provider_message_id"] for r in self.query(f'SELECT provider_message_id FROM "{MESSAGE}" WHERE thread_uid=%(uid)s::uuid', {"uid": str(thread_uid)}, max_rows=10000)}

    def open_task(self, message_uid):
        rows = self.query('SELECT uid, version FROM mainsequence_crm__task WHERE source_email_message_uid=%(uid)s::uuid '
                          'AND completed_at IS NULL AND archived_at IS NULL ORDER BY uid LIMIT 1', {"uid": str(message_uid)})
        return rows[0] if rows else None

    def follow_up(self, actor, email, command):
        task_uid = command.existing_task_uid or uuid.uuid4()
        params = {"actor": str(actor), "email": str(email["uid"]), "contact": str(email["contact_uid"]), "task": str(task_uid),
                  "task_version": command.expected_task_version, "lead": str(command.lead_uid) if command.lead_uid else None,
                  "lead_version": command.expected_lead_version, "text": command.text,
                  "due": command.due_at.isoformat() if command.due_at else None,
                  "owner": str(command.owner_uid) if command.owner_uid else None, "event": str(uuid.uuid4()), "command": str(uuid.uuid4())}
        guard = (f'SELECT e.uid FROM "{MESSAGE}" e JOIN "{THREAD}" t ON t.uid=e.thread_uid JOIN "{CONTACT}" c ON c.uid=t.contact_uid '
                 "WHERE e.uid=%(email)s::uuid AND t.contact_uid=%(contact)s::uuid AND e.archived_at IS NULL AND t.archived_at IS NULL AND c.archived_at IS NULL")
        if command.lead_uid:
            guard += (' AND EXISTS (SELECT 1 FROM mainsequence_crm__solution_selling_lead l WHERE l.uid=%(lead)s::uuid '
                      'AND l.contact_uid=%(contact)s::uuid AND l.version=%(lead_version)s AND l.archived_at IS NULL FOR UPDATE)')
        guard += " FOR UPDATE OF e"
        if command.existing_task_uid:
            changed = ('changed AS (UPDATE mainsequence_crm__task t SET source_email_message_uid=%(email)s::uuid, version=t.version+1, '
                       "updated_at=NOW(), updated_by_uid=%(actor)s::uuid FROM gate WHERE t.uid=%(task)s::uuid AND t.version=%(task_version)s "
                       "AND t.contact_uid=%(contact)s::uuid AND t.completed_at IS NULL AND t.archived_at IS NULL "
                       "AND (t.source_email_message_uid IS NULL OR t.source_email_message_uid=%(email)s::uuid) RETURNING t.uid)")
        else:
            changed = ('changed AS (INSERT INTO mainsequence_crm__task (uid, created_at, updated_at, created_by_uid, updated_by_uid, version, '
                       'contact_uid, source_email_message_uid, owner_uid, type_key, text, due_at) SELECT %(task)s::uuid, NOW(), NOW(), '
                       "%(actor)s::uuid, %(actor)s::uuid, 1, %(contact)s::uuid, %(email)s::uuid, %(owner)s::uuid, 'follow-up', %(text)s, %(due)s::timestamptz FROM gate RETURNING uid)")
        lead_cte = (', lead_changed AS (UPDATE mainsequence_crm__solution_selling_lead l SET next_task_uid=changed.uid, version=l.version+1, '
                    'updated_at=NOW(), updated_by_uid=%(actor)s::uuid FROM changed WHERE l.uid=%(lead)s::uuid AND l.version=%(lead_version)s RETURNING l.uid)') if command.lead_uid else ''
        sql = (f'WITH gate AS ({guard}), {changed}{lead_cte} '
               f'INSERT INTO "{AUDIT}" (uid, entity_type, entity_uid, kind, occurred_at, recorded_at, actor_uid, origin, command_uid, summary, changes) '
               "SELECT %(event)s::uuid, 'task', changed.uid, 'email_follow_up', NOW(), NOW(), %(actor)s::uuid, 'live', %(command)s::uuid, "
               "'Linked email follow-up', jsonb_build_object('email_uid', %(email)s::text) FROM changed RETURNING entity_uid")
        if not self.query(sql, params, mutation=True):
            raise ResourceConflict("Email, Task or Lead changed; read the saved records")
        return task_uid
