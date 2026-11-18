"""Audience-gated discussions with atomic message history and lifecycle fences."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, insert, or_, select, update

from mainsequence.client.exceptions import BadRequestError
from metatables import MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import GuardedStatement
from src.erp.module_access import require_module

from .errors import CollaborationError
from .metatables import AuditEvent, Discussion, Message, MessageRevision
from .schemas import DiscussionCreate, DiscussionInput, MessageCreate, MessageEdit, MessageRetract


def key(value):
    return UUID(str(value))


def now():
    return datetime.now(timezone.utc)


class Service:
    def __init__(self, store, actor_uid, capabilities, dependencies, actor_name="Team member"):
        self.actor_name = actor_name
        self.store, self.actor_uid, self.capabilities, self.dependencies = (
            store,
            key(actor_uid),
            set(capabilities),
            dependencies,
        )

    def require(self, cap):
        require_module("collaboration")
        if cap not in self.capabilities:
            raise CollaborationError(
                403, "forbidden", "Collaboration access does not permit this operation"
            )

    def raw(self, model, uid):
        self.require("collaboration.read")
        rows = self.store.read(select(model.__table__).where(model.uid == key(uid)).limit(1))
        if not rows:
            raise CollaborationError(404, "not_found", "Discussion record not found")
        return rows[0]

    def thread(self, uid, *, write=False):
        row = self.raw(Discussion, uid)
        if row["project_uid"]:
            project = self.dependencies.project(row["project_uid"], write=write)
            row["project_name"] = project["name"]
        else:
            row["project_name"] = ""
        return row

    def open_thread(self, uid):
        self.require("collaboration.write")
        row = self.thread(uid, write=True)
        if row["state"] != "open":
            raise CollaborationError(409, "closed", "Reopen the discussion before changing content")
        return row

    def owner_can_write(self, row):
        if row["project_uid"]:
            try:
                self.dependencies.project(row["project_uid"], write=True)
            except CollaborationError as exc:
                if exc.status in {403, 404}:
                    return False
                raise
        return True

    def writable(self, row):
        return (
            "collaboration.write" in self.capabilities
            and row["state"] == "open"
            and self.owner_can_write(row)
        )

    def get(self, uid):
        row = self.thread(uid)
        writable = self.writable(row)
        owner = row["created_by_uid"] == str(self.actor_uid)
        row.update(
            audience="authorized_project_readers"
            if row["scope"] == "project"
            else "collaboration_readers",
            can_post=writable,
            can_edit=writable and (owner or "collaboration.manage" in self.capabilities),
        )
        # Lifecycle authority is checked again on each command, including owner scope.
        row["can_manage"] = "collaboration.manage" in self.capabilities and self.owner_can_write(
            row
        )
        row["message_count"] = self.count(Message, Message.discussion_uid == key(uid))
        return row

    def count(self, model, *terms):
        return int(
            self.store.read(select(func.count().label("count")).select_from(model).where(*terms))[
                0
            ]["count"]
        )

    def paginate(self, model, terms, order, *, page_index=0, page_size=25):
        total = self.count(model, *terms)
        rows = self.store.read(
            select(model.__table__)
            .where(*terms)
            .order_by(*order)
            .offset(page_index * page_size)
            .limit(page_size),
            max_rows=page_size,
        )
        return {
            "items": rows,
            "pageInfo": {
                "pageIndex": page_index,
                "pageSize": page_size,
                "totalItems": total,
                "hasNextPage": (page_index + 1) * page_size < total,
                "hasPreviousPage": page_index > 0,
            },
        }

    def collection(self, *, page_index=0, page_size=25, search="", state=None, project_uid=None):
        self.require("collaboration.read")
        if project_uid:
            self.dependencies.project(project_uid)
            terms = [Discussion.scope == "project", Discussion.project_uid == key(project_uid)]
        else:
            terms = [Discussion.scope == "shared", Discussion.project_uid.is_(None)]
        if search:
            terms.append(
                or_(
                    func.lower(Discussion.name).contains(search.lower(), autoescape=True),
                    func.lower(Discussion.description).contains(search.lower(), autoescape=True),
                )
            )
        if state:
            terms.append(Discussion.state == state)
        return self.paginate(
            Discussion,
            terms,
            [Discussion.updated_at.desc(), Discussion.uid],
            page_index=page_index,
            page_size=page_size,
        )

    def message(self, uid):
        row = self.raw(Message, uid)
        thread = self.thread(row["discussion_uid"])
        row.update(discussion_version=thread["version"], discussion_state=thread["state"])
        self.message_flags(row, thread)
        return row

    def message_flags(self, row, thread, writable=None):
        writable = self.writable(thread) if writable is None else writable
        author = row["created_by_uid"] == str(self.actor_uid)
        row["can_edit"] = (
            author and row["state"] == "active" and thread["state"] == "open" and writable
        )
        row["can_retract"] = (
            (author or "collaboration.manage" in self.capabilities)
            and row["state"] == "active"
            and thread["state"] == "open"
            and writable
        )
        row["can_history"] = author or "collaboration.manage" in self.capabilities
        if row["state"] == "retracted":
            row["body"] = ""

    def messages(self, uid, **query):
        thread = self.thread(uid)
        result = self.paginate(
            Message, [Message.discussion_uid == key(uid)], [Message.sequence.desc()], **query
        )
        writable = self.writable(thread)
        for row in result["items"]:
            self.message_flags(row, thread, writable=writable)
        result["discussion_version"] = thread["version"]
        return result

    def revisions(self, uid, **query):
        row = self.message(uid)
        if not row["can_history"]:
            raise CollaborationError(
                403, "history", "Only the author or a moderator can read prior message text"
            )
        return self.paginate(
            MessageRevision,
            [MessageRevision.message_uid == key(uid)],
            [MessageRevision.version.desc()],
            **query,
        )

    def history(self, uid, **query):
        self.require("collaboration.manage")
        self.thread(uid)
        return self.paginate(
            AuditEvent,
            [AuditEvent.record_uid == key(uid)],
            [AuditEvent.occurred_at.desc(), AuditEvent.uid],
            **query,
        )

    def created(self):
        return dict(
            version=1,
            created_at=now(),
            updated_at=now(),
            created_by_uid=self.actor_uid,
            updated_by_uid=self.actor_uid,
        )

    def guard(self, model, row, expected, values):
        return GuardedStatement(
            update(model)
            .where(
                model.uid == key(row["uid"]), model.version == expected, model.state == row["state"]
            )
            .values(**values, version=expected + 1, updated_at=now(), updated_by_uid=self.actor_uid)
            .returning(model.uid),
            expect_rows=1,
            label="discussion_version" if model is Discussion else "message_version",
        )

    def audit(self, uid, action, version, fields, context=None):
        return insert(AuditEvent).values(
            uid=uuid4(),
            resource="discussions",
            record_uid=key(uid),
            action=action,
            version=version,
            actor_uid=self.actor_uid,
            occurred_at=now(),
            fields=sorted(fields),
            context=context or {},
        )

    def revision(self, uid, version, body, state, reason=""):
        return insert(MessageRevision).values(
            uid=uuid4(),
            message_uid=key(uid),
            actor_name=self.actor_name,
            version=version,
            body=body,
            state=state,
            reason=reason,
            actor_uid=self.actor_uid,
            occurred_at=now(),
        )

    def transact(self, steps):
        try:
            return self.store.write(steps)
        except MetaTableTransactionGuardError as exc:
            raise CollaborationError(
                409, "conflict", "Discussion or message changed; reload and review"
            ) from exc
        except BadRequestError as exc:
            detail = (getattr(exc, "payload", {}) or {}).get("detail", {})
            if isinstance(detail, dict) and detail.get("code") == "compiled_sql_database_error":
                raise CollaborationError(
                    409,
                    "constraint_conflict",
                    "Message, discussion or request already exists; check the saved record",
                ) from exc
            raise

    def create(self, payload):
        self.require("collaboration.write")
        data = DiscussionCreate.model_validate(payload).model_dump()
        uid = data.pop("request_uid")
        data.pop("audience")
        if data["project_uid"]:
            self.dependencies.project(data["project_uid"], write=True)
        self.transact(
            [
                insert(Discussion).values(
                    uid=uid, **data, **self.created(), state="open", message_sequence=0
                ),
                self.audit(uid, "create", 1, data),
            ]
        )
        return self.get(uid)

    def edit(self, uid, payload, expected_version):
        row = self.open_thread(uid)
        if row["created_by_uid"] != str(self.actor_uid):
            self.require("collaboration.manage")
        data = DiscussionInput.model_validate(payload).model_dump()
        self.transact(
            [
                self.guard(Discussion, row, expected_version, data),
                self.audit(uid, "edit", expected_version + 1, data),
            ]
        )
        return self.get(uid)

    def transition(self, uid, action, expected_version):
        self.require("collaboration.manage")
        row = self.thread(uid, write=True)
        transitions = {
            "close": ("open", "closed"),
            "reopen": ("closed", "open"),
            "archive": ("closed", "archived"),
            "restore": ("archived", "closed"),
        }
        if action not in transitions or row["state"] != transitions[action][0]:
            raise CollaborationError(409, "state", "Discussion action is unavailable in this state")
        self.transact(
            [
                self.guard(Discussion, row, expected_version, {"state": transitions[action][1]}),
                self.audit(uid, action, expected_version + 1, ["state"]),
            ]
        )
        return self.get(uid)

    def post(self, uid, payload):
        data = MessageCreate.model_validate(payload).model_dump()
        thread = self.open_thread(uid)
        message_uid = data["request_uid"]
        version = data["expected_discussion_version"]
        self.transact(
            [
                self.guard(
                    Discussion,
                    thread,
                    version,
                    {"message_sequence": thread["message_sequence"] + 1},
                ),
                insert(Message).values(
                    uid=message_uid,
                    author_name=self.actor_name,
                    discussion_uid=key(uid),
                    sequence=thread["message_sequence"] + 1,
                    body=data["body"],
                    state="active",
                    retraction_reason="",
                    **self.created(),
                ),
                self.revision(message_uid, 1, data["body"], "active"),
                self.audit(
                    uid,
                    "post-message",
                    version + 1,
                    ["messages"],
                    {"message_uid": str(message_uid), "message_version": 1},
                ),
            ]
        )
        return {"discussion": self.get(uid), "message": self.message(message_uid)}

    def edit_message(self, uid, payload):
        data = MessageEdit.model_validate(payload).model_dump()
        row = self.message(uid)
        thread = self.open_thread(row["discussion_uid"])
        if row["created_by_uid"] != str(self.actor_uid):
            raise CollaborationError(403, "author", "Only the author can edit message text")
        if row["state"] != "active":
            raise CollaborationError(409, "retracted", "Retracted messages cannot be edited")
        mv, tv = data["expected_version"], data["expected_discussion_version"]
        self.transact(
            [
                self.guard(Discussion, thread, tv, {}),
                self.guard(Message, row, mv, {"body": data["body"]}),
                self.revision(uid, mv + 1, data["body"], "active"),
                self.audit(
                    thread["uid"],
                    "edit-message",
                    tv + 1,
                    ["messages"],
                    {"message_uid": str(uid), "message_version": mv + 1},
                ),
            ]
        )
        return {"discussion": self.get(thread["uid"]), "message": self.message(uid)}

    def retract(self, uid, payload):
        data = MessageRetract.model_validate(payload).model_dump()
        row = self.message(uid)
        thread = self.open_thread(row["discussion_uid"])
        if row["created_by_uid"] != str(self.actor_uid):
            self.require("collaboration.manage")
        if row["state"] != "active":
            raise CollaborationError(409, "retracted", "Message is already retracted")
        mv, tv = data["expected_version"], data["expected_discussion_version"]
        self.transact(
            [
                self.guard(Discussion, thread, tv, {}),
                self.guard(
                    Message,
                    row,
                    mv,
                    {"body": "", "state": "retracted", "retraction_reason": data["reason"]},
                ),
                self.revision(uid, mv + 1, "", "retracted", data["reason"]),
                self.audit(
                    thread["uid"],
                    "retract-message",
                    tv + 1,
                    ["messages"],
                    {"message_uid": str(uid), "message_version": mv + 1},
                ),
            ]
        )
        return {"discussion": self.get(thread["uid"]), "message": self.message(uid)}
