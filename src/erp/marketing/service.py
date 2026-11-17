"""Versioned audiences and capture-only execution through owned MetaTables commands."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, or_, select, update

from mainsequence.client.exceptions import BadRequestError
from metatables import MetaTableTransactionGuardError
from metatables.compiled_sql.v1 import GuardedStatement

from .errors import MarketingError
from .metatables import RESOURCES, AuditEvent, DeliveryEvent, Mailing, Recipient, Subscriber
from .schemas import (
    FollowupInput,
    MailingCreate,
    MailingInput,
    QueueInput,
    RecipientCreate,
    SimulationInput,
    SubscriberCreate,
    SubscriptionChange,
)
from .store import require_local_runtime


def key(value):
    return UUID(str(value))


def now():
    return datetime.now(timezone.utc)


class Service:
    def __init__(self, store, actor_uid, capabilities, dependencies):
        self.store, self.actor_uid, self.capabilities, self.dependencies = (
            store,
            key(actor_uid),
            set(capabilities),
            dependencies,
        )

    def require(self, cap):
        if cap not in self.capabilities:
            raise MarketingError(
                403, "forbidden", "Marketing access does not permit this operation"
            )

    def local_capture(self):
        if not self.store.local_only or str(require_local_runtime()) != self.store.data_source_uid:
            raise MarketingError(
                403,
                "local_only",
                "Capture and simulation require the verified local SQLite runtime",
            )

    def raw(self, resource, uid):
        self.require("marketing.read")
        if resource not in RESOURCES:
            raise MarketingError(404, "not_found", "Unknown Marketing resource")
        model = RESOURCES[resource]
        rows = self.store.read(select(model.__table__).where(model.uid == key(uid)).limit(1))
        if not rows:
            raise MarketingError(404, "not_found", "Marketing record not found")
        return rows[0]

    def count(self, model, *terms):
        return int(
            self.store.read(select(func.count().label("count")).select_from(model).where(*terms))[
                0
            ]["count"]
        )

    def get(self, resource, uid):
        row = self.raw(resource, uid)
        if resource == "mailings":
            counts = self.store.read(
                select(Recipient.state, func.count().label("count"))
                .where(Recipient.mailing_uid == key(uid))
                .group_by(Recipient.state)
            )
            row["results"] = {x["state"]: x["count"] for x in counts}
            row["recipient_count"] = sum(row["results"].values())
            stats = self.store.read(
                select(DeliveryEvent.kind, func.count().label("count"))
                .join(Recipient, Recipient.uid == DeliveryEvent.recipient_uid)
                .where(Recipient.mailing_uid == key(uid), DeliveryEvent.mode == "simulated")
                .group_by(DeliveryEvent.kind)
            )
            row["simulated_engagement"] = {x["kind"]: x["count"] for x in stats}
        if resource == "recipients":
            subscriber = self.raw("subscribers", row["subscriber_uid"])
            mailing = self.raw("mailings", row["mailing_uid"])
            row.update(
                name=subscriber["name"],
                email=subscriber["email"],
                party_uid=subscriber["party_uid"],
                mailing_name=mailing["name"],
                mailing_version=mailing["version"],
                mailing_state=mailing["state"],
                mode="local_capture",
            )
            row["events"] = self.events(uid)["items"]
        return row

    def paginate(self, model, terms, order, *, page_index=0, page_size=25):
        total = self.count(model, *terms)
        return {
            "items": self.store.read(
                select(model.__table__)
                .where(*terms)
                .order_by(*order)
                .offset(page_index * page_size)
                .limit(page_size),
                max_rows=page_size,
            ),
            "pageInfo": {
                "pageIndex": page_index,
                "pageSize": page_size,
                "totalItems": total,
                "hasNextPage": (page_index + 1) * page_size < total,
                "hasPreviousPage": page_index > 0,
            },
        }

    def collection(
        self, resource, *, search="", state=None, page_index=0, page_size=25, mailing_uid=None
    ):
        self.require("marketing.read")
        if resource not in RESOURCES:
            raise MarketingError(404, "not_found", "Unknown Marketing resource")
        model = RESOURCES[resource]
        terms = []
        if state:
            terms.append(model.state == state)
        if resource == "recipients":
            if not mailing_uid:
                raise MarketingError(
                    422, "mailing_required", "Choose a mailing to inspect its audience"
                )
            self.raw("mailings", mailing_uid)
            terms.append(Recipient.mailing_uid == key(mailing_uid))
            if search:
                matching = select(Subscriber.uid).where(
                    or_(
                        func.lower(Subscriber.name).contains(search.lower(), autoescape=True),
                        func.lower(Subscriber.email).contains(search.lower(), autoescape=True),
                    )
                )
                terms.append(Recipient.subscriber_uid.in_(matching))
        elif search:
            terms.append(
                or_(
                    func.lower(model.name).contains(search.lower(), autoescape=True),
                    func.lower(
                        Subscriber.email if resource == "subscribers" else Mailing.subject
                    ).contains(search.lower(), autoescape=True),
                )
            )
        result = self.paginate(
            model,
            terms,
            [model.created_at.desc(), model.uid],
            page_index=page_index,
            page_size=page_size,
        )
        if resource == "recipients":
            result["items"] = [self.get(resource, row["uid"]) for row in result["items"]]
        return result

    def events(self, uid, **query):
        self.raw("recipients", uid)
        return self.paginate(
            DeliveryEvent,
            [DeliveryEvent.recipient_uid == key(uid)],
            [DeliveryEvent.occurred_at.desc(), DeliveryEvent.uid],
            **query,
        )

    def history(self, resource, uid, **query):
        self.require("marketing.manage")
        self.raw(resource, uid)
        return self.paginate(
            AuditEvent,
            [AuditEvent.resource == resource, AuditEvent.record_uid == key(uid)],
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
            label="marketing_version",
        )

    def audit(self, resource, uid, action, version, fields):
        return insert(AuditEvent).values(
            uid=uuid4(),
            resource=resource,
            record_uid=key(uid),
            action=action,
            version=version,
            actor_uid=self.actor_uid,
            occurred_at=now(),
            fields=sorted(fields),
        )

    def event_data(self, uid, kind, evidence, *, simulated=False):
        return dict(
            uid=uuid4(),
            recipient_uid=key(uid),
            kind=kind,
            evidence=evidence,
            actor_uid=self.actor_uid,
            occurred_at=now(),
            mode="simulated" if simulated else "local_capture",
        )

    def transact(self, steps):
        try:
            return self.store.write(steps)
        except MetaTableTransactionGuardError as exc:
            raise MarketingError(
                409, "conflict", "Mailing, recipient or subscription changed; reload and review"
            ) from exc
        except BadRequestError as exc:
            detail = (getattr(exc, "payload", {}) or {}).get("detail", {})
            if isinstance(detail, dict) and detail.get("code") == "compiled_sql_database_error":
                raise MarketingError(
                    409,
                    "constraint_conflict",
                    "This address, audience member, event or request already exists; check the saved record",
                ) from exc
            raise

    def subscriber(self, payload):
        self.require("marketing.write")
        data = SubscriberCreate.model_validate(payload).model_dump()
        uid = data.pop("request_uid")
        person = self.dependencies.person(data["party_uid"])
        data["email"] = str(data["email"]).casefold()
        if data["email"] not in {str(email).casefold() for email in person["emails"]}:
            raise MarketingError(
                422, "email_mismatch", "Choose an email recorded on this shared person"
            )
        self.transact(
            [
                insert(Subscriber).values(
                    uid=uid, **data, name=person["name"], state="subscribed", **self.created()
                ),
                self.audit("subscribers", uid, "subscribe", 1, data),
            ]
        )
        return self.get("subscribers", uid)

    def subscription(self, uid, payload):
        self.require("marketing.write")
        data = SubscriptionChange.model_validate(payload).model_dump()
        expected = data.pop("expected_version")
        row = self.raw("subscribers", uid)
        if data["state"] == "subscribed":
            person = self.dependencies.person(row["party_uid"])
            if row["email"] not in {str(email).casefold() for email in person["emails"]}:
                raise MarketingError(
                    422,
                    "email_mismatch",
                    "Update the shared person before resubscribing this address",
                )
        self.transact(
            [
                self.guard(Subscriber, row, expected, data),
                self.audit("subscribers", uid, data["state"], expected + 1, data),
            ]
        )
        return self.get("subscribers", uid)

    def mailing(self, payload, *, uid=None, expected_version=None):
        self.require("marketing.write")
        if uid:
            row = self.raw("mailings", uid)
            self.draft(row)
            data = MailingInput.model_validate(payload).model_dump()
            steps = [self.guard(Mailing, row, expected_version, data)]
        else:
            data = MailingCreate.model_validate(payload).model_dump()
            uid = data.pop("request_uid")
            steps = [
                insert(Mailing).values(
                    uid=uid,
                    **data,
                    **self.created(),
                    state="draft",
                    mode="local_capture",
                    queued_at=None,
                    finished_at=None,
                )
            ]
        steps.append(
            self.audit(
                "mailings",
                uid,
                "edit" if expected_version else "create",
                (expected_version or 0) + 1,
                data,
            )
        )
        self.transact(steps)
        return self.get("mailings", uid)

    def draft(self, row):
        if row["state"] != "draft":
            raise MarketingError(409, "frozen", "Content and audience are frozen after queueing")

    def add_recipient(self, uid, payload):
        self.require("marketing.write")
        data = RecipientCreate.model_validate(payload).model_dump()
        row = self.raw("mailings", uid)
        self.draft(row)
        subscriber = self.raw("subscribers", data["subscriber_uid"])
        if subscriber["state"] != "subscribed":
            raise MarketingError(422, "unsubscribed", "Choose a subscribed audience member")
        if self.count(Recipient, Recipient.mailing_uid == key(uid)) >= 100:
            raise MarketingError(
                422, "audience_limit", "A bounded mailing supports at most 100 recipients"
            )
        rid = data["request_uid"]
        version = data["expected_version"]
        self.transact(
            [
                self.guard(Mailing, row, version, {}),
                self.guard(Subscriber, subscriber, subscriber["version"], {}),
                insert(Recipient).values(
                    uid=rid,
                    mailing_uid=key(uid),
                    subscriber_uid=key(subscriber["uid"]),
                    state="pending",
                    reason="",
                    payload={},
                    captured_at=None,
                    crm_task_uid=None,
                    **self.created(),
                ),
                self.audit("mailings", uid, "add-recipient", version + 1, ["recipients"]),
            ]
        )
        return {"mailing": self.get("mailings", uid), "recipient": self.get("recipients", rid)}

    def remove_recipient(self, uid, expected_version, expected_mailing_version):
        self.require("marketing.write")
        row = self.raw("recipients", uid)
        mailing = self.raw("mailings", row["mailing_uid"])
        self.draft(mailing)
        self.transact(
            [
                self.guard(Mailing, mailing, expected_mailing_version, {}),
                GuardedStatement(
                    delete(Recipient)
                    .where(
                        Recipient.uid == key(uid),
                        Recipient.version == expected_version,
                        Recipient.state == "pending",
                    )
                    .returning(Recipient.uid),
                    expect_rows=1,
                    label="recipient_version",
                ),
                self.audit(
                    "mailings",
                    mailing["uid"],
                    "remove-recipient",
                    expected_mailing_version + 1,
                    ["recipients"],
                ),
            ]
        )
        return self.get("mailings", mailing["uid"])

    def queue(self, uid, payload):
        self.require("marketing.manage")
        self.local_capture()
        data = QueueInput.model_validate(payload)
        row = self.raw("mailings", uid)
        self.draft(row)
        if not data.acknowledge_local_capture:
            raise MarketingError(
                422, "acknowledgement", "Acknowledge local capture without sending email"
            )
        eligible = self.store.read(
            select(func.count().label("count"))
            .select_from(Recipient)
            .join(Subscriber, Subscriber.uid == Recipient.subscriber_uid)
            .where(Recipient.mailing_uid == key(uid), Subscriber.state == "subscribed")
        )[0]["count"]
        if not eligible:
            raise MarketingError(
                422, "empty_audience", "Add at least one subscribed recipient before queueing"
            )
        self.transact(
            [
                self.guard(
                    Mailing, row, data.expected_version, {"state": "queued", "queued_at": now()}
                ),
                self.audit(
                    "mailings",
                    uid,
                    "queue-local",
                    data.expected_version + 1,
                    ["state", "queued_at"],
                ),
            ]
        )
        return self.get("mailings", uid)

    def capture(self, uid, expected_version):
        self.require("marketing.manage")
        self.local_capture()
        row = self.raw("mailings", uid)
        if row["state"] != "queued":
            raise MarketingError(409, "state", "Only queued mailings can run local capture")
        pending = self.store.read(
            select(Recipient.__table__)
            .where(Recipient.mailing_uid == key(uid), Recipient.state == "pending")
            .order_by(Recipient.created_at, Recipient.uid)
            .limit(10),
            max_rows=10,
        )
        total = self.count(
            Recipient, Recipient.mailing_uid == key(uid), Recipient.state == "pending"
        )
        finished = total <= 10
        steps = [
            self.guard(
                Mailing,
                row,
                expected_version,
                {
                    "state": "completed" if finished else "queued",
                    "finished_at": now() if finished else None,
                },
            )
        ]
        for recipient in pending:
            subscriber = self.raw("subscribers", recipient["subscriber_uid"])
            reason = "Subscription withdrawn" if subscriber["state"] != "subscribed" else ""
            if not reason:
                from src.erp.base.service import BaseError

                try:
                    person = self.dependencies.person(subscriber["party_uid"])
                    if subscriber["email"] not in {
                        str(email).casefold() for email in person["emails"]
                    }:
                        reason = "Address is no longer on the shared person"
                except (MarketingError, BaseError) as exc:
                    if exc.status not in {404, 422}:
                        raise
                    reason = "Shared person is no longer available"
            state = "suppressed" if reason else "captured"
            values = dict(
                state=state,
                reason=reason or "Captured locally; no email sent",
                captured_at=None if reason else now(),
                payload={}
                if reason
                else {
                    "sender": row["sender_email"],
                    "email": subscriber["email"],
                    "subject": row["subject"],
                    "body": row["body"],
                    "mode": "local_capture",
                },
            )
            steps.extend(
                [
                    self.guard(Subscriber, subscriber, subscriber["version"], {}),
                    self.guard(Recipient, recipient, recipient["version"], values),
                    insert(DeliveryEvent).values(
                        **self.event_data(recipient["uid"], state, values["reason"])
                    ),
                ]
            )
        steps.append(
            self.audit("mailings", uid, "capture-local", expected_version + 1, ["results", "state"])
        )
        self.transact(steps)
        return self.get("mailings", uid)

    def cancel(self, uid, expected_version):
        self.require("marketing.manage")
        row = self.raw("mailings", uid)
        if row["state"] not in {"draft", "queued"}:
            raise MarketingError(409, "state", "Only draft or queued mailings can be cancelled")
        pending = self.store.read(
            select(Recipient.uid).where(
                Recipient.mailing_uid == key(uid), Recipient.state == "pending"
            ),
            max_rows=100,
        )
        steps = [
            self.guard(Mailing, row, expected_version, {"state": "cancelled", "finished_at": now()})
        ]
        if pending:
            steps.extend(
                [
                    GuardedStatement(
                        update(Recipient)
                        .where(Recipient.mailing_uid == key(uid), Recipient.state == "pending")
                        .values(
                            state="cancelled",
                            reason="Mailing cancelled",
                            version=Recipient.version + 1,
                            updated_at=now(),
                            updated_by_uid=self.actor_uid,
                        )
                        .returning(Recipient.uid),
                        expect_rows=len(pending),
                        label="cancel_pending",
                    ),
                    insert(DeliveryEvent).values(
                        [
                            self.event_data(item["uid"], "cancelled", "Mailing cancelled")
                            for item in pending
                        ]
                    ),
                ]
            )
        steps.append(
            self.audit("mailings", uid, "cancel", expected_version + 1, ["state", "results"])
        )
        self.transact(steps)
        return self.get("mailings", uid)

    def simulate(self, uid, payload):
        self.require("marketing.manage")
        self.local_capture()
        data = SimulationInput.model_validate(payload)
        row = self.raw("recipients", uid)
        mailing = self.raw("mailings", row["mailing_uid"])
        if row["state"] != "captured":
            raise MarketingError(
                409, "not_captured", "Capture this recipient locally before simulating engagement"
            )
        kinds = {event["kind"] for event in self.events(uid)["items"]}
        if (
            data.kind in kinds
            or "bounced" in kinds
            or data.kind == "bounced"
            and kinds & {"opened", "clicked", "replied"}
        ):
            raise MarketingError(
                409, "outcome", "This event conflicts with already recorded simulated engagement"
            )
        self.transact(
            [
                self.guard(Mailing, mailing, data.expected_mailing_version, {}),
                self.guard(Recipient, row, data.expected_version, {}),
                insert(DeliveryEvent).values(
                    **self.event_data(uid, data.kind, data.evidence, simulated=True)
                ),
                self.audit(
                    "recipients",
                    uid,
                    "simulate-" + data.kind,
                    data.expected_version + 1,
                    ["events"],
                ),
            ]
        )
        return self.get("recipients", uid)

    def link_followup(self, uid, payload):
        self.require("marketing.manage")
        data = FollowupInput.model_validate(payload)
        row = self.get("recipients", uid)
        mailing = self.raw("mailings", row["mailing_uid"])
        if (
            row["crm_task_uid"]
            or row["state"] != "captured"
            or not any(event["kind"] == "replied" for event in row["events"])
        ):
            raise MarketingError(
                409,
                "followup",
                "Record a simulated reply before linking one existing CRM follow-up",
            )
        self.dependencies.followup(data.task_uid, row["party_uid"])
        self.transact(
            [
                self.guard(Mailing, mailing, data.expected_mailing_version, {}),
                self.guard(Recipient, row, data.expected_version, {"crm_task_uid": data.task_uid}),
                self.audit(
                    "recipients", uid, "link-followup", data.expected_version + 1, ["crm_task_uid"]
                ),
            ]
        )
        return self.get("recipients", uid)
