"""Bounded Gmail retrieval. Search never persists; sync fetches one enrolled thread."""

import base64
import json
import uuid
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from time import monotonic
from urllib.parse import quote, urlencode

import httpx

from src.erp.crm.google_workspace.security import digest
from src.erp.crm.repositories.errors import ResourceConflict

from .models import Address, GmailPreview, MessageFields

ROOT = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class TextFromHtml(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self.hidden += 1
        elif not self.hidden and tag in {"p", "br", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def source_key(actor, sub):
    return digest(f"{actor}:{sub}")


def fingerprint(message):
    return digest(json.dumps(message, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def header_map(payload):
    result = {}
    for header in payload.get("headers", []):
        if not isinstance(header, dict):
            continue
        name, value = header.get("name", "").lower(), header.get("value", "")
        if isinstance(value, str):
            try:
                decoded = str(make_header(decode_header(value)))
            except (LookupError, UnicodeError, ValueError):
                decoded = value
            result[name] = result.get(name, "") + (", " if name in result else "") + decoded
    return result


def addresses(value):
    output = []
    for name, email in getaddresses([value]):
        if email:
            output.append(Address(email=email, name=name or None).model_dump(mode="json"))
    return output


class GmailEmails:
    def __init__(self, oauth):
        self.oauth = oauth

    def get(self, access, path, params=None):
        try:
            response = self.oauth.http.get(ROOT + path, headers={"Authorization": f"Bearer {access}"}, params=params)
            response.raise_for_status()
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise ResourceConflict("Selected email content is too large; choose individual messages")
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("Invalid Google response")
            return body
        except (httpx.HTTPError, ValueError) as exc:
            raise ResourceConflict("Selected Gmail content could not be read; check the connection") from exc

    def search(self, actor, query):
        access, _connection = self.oauth.access_token(actor, "gmail")
        selection = f"({query.query}) after:{int(query.time_min.timestamp())} before:{int(query.time_max.timestamp())}"
        page = self.get(access, "/messages", {"q": selection, "maxResults": 25, **({"pageToken": query.page_token} if query.page_token else {})})
        items = []
        for item in page.get("messages", [])[:25]:
            identifier = GmailPreview(message_id=item["id"]).message_id
            raw = self.get(access, "/messages/" + quote(identifier, safe=""),
                           {"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date"]})
            h = header_map(raw.get("payload", {}))
            items.append({"message_id": identifier, "subject": h.get("subject", ""), "from": h.get("from", ""), "date": h.get("date", "")})
        return {"items": items, "next_page_token": page.get("nextPageToken")}

    def message(self, access, message_id, connection):
        raw = self.get(access, "/messages/" + quote(message_id, safe=""), {"format": "full"})
        if raw.get("id") != message_id:
            raise ResourceConflict("Google returned a different email")
        return self.parse(access, raw, connection)

    def parse(self, access, raw, connection):
        message_id = GmailPreview(message_id=raw["id"]).message_id
        thread_id = GmailPreview(message_id=raw["threadId"]).message_id
        payload = raw.get("payload", {})
        headers = header_map(payload)
        sender = addresses(headers.get("from", ""))
        if len(sender) != 1:
            raise ResourceConflict("Selected email needs one identifiable sender")
        plain, html = [], []
        visited = 0

        def parts(part):
            nonlocal visited
            visited += 1
            if visited > 1000:
                raise ResourceConflict("Email MIME structure is too large")
            mime = part.get("mimeType", "").lower()
            if mime in {"text/plain", "text/html"} and not part.get("filename"):
                body = part.get("body", {})
                data = body.get("data")
                if not data and body.get("attachmentId"):
                    data = self.get(access, "/messages/" + quote(message_id, safe="") + "/attachments/" + quote(body["attachmentId"], safe="")).get("data")
                if data:
                    if len(data) > 1000000:
                        raise ResourceConflict("Selected email body is too large")
                    decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
                    from email.message import Message
                    content_type = Message()
                    content_type["Content-Type"] = header_map(part).get("content-type", mime)
                    text = decoded.decode(content_type.get_content_charset() or "utf-8", errors="strict")
                    (plain if mime == "text/plain" else html).append(text)
            for child in part.get("parts", []):
                parts(child)

        try:
            parts(payload)
            if plain:
                body_text = "\n".join(plain)
            else:
                parser = TextFromHtml()
                parser.feed("\n".join(html))
                body_text = "".join(parser.parts).strip()
            date = None
            if headers.get("date"):
                try:
                    date = parsedate_to_datetime(headers["date"])
                    if date.tzinfo is None:
                        date = None
                except (ValueError, TypeError, OverflowError):
                    pass
            rfc = headers.get("message-id") or None
            if rfc and len(rfc) > 1000:
                raise ValueError("Message ID too long")
            url = "https://mail.google.com/mail/?" + urlencode({"authuser": connection["display_email"]})
            url += "#search/" + quote("rfc822msgid:" + rfc.strip("<>"), safe="") if rfc else "#all/" + quote(thread_id, safe="")
            content = MessageFields(sender=sender[0], to=addresses(headers.get("to", "")), cc=addresses(headers.get("cc", "")),
                                    subject=headers.get("subject", ""), sent_at=date, body_text=body_text,
                                    body_state="complete" if plain or html else "unavailable", original_url=url)
            internal = int(raw["internalDate"])
            if internal < 0:
                raise ValueError("Invalid Gmail date")
            return {**content.model_dump(mode="json"), "provider_message_id": message_id, "provider_thread_id": thread_id,
                    "internal_date_ms": internal, "rfc_message_id": rfc}
        except (ValueError, LookupError, UnicodeError, KeyError, RecursionError) as exc:
            raise ResourceConflict("Selected email cannot be captured completely within supported text limits") from exc

    def preview(self, actor, command, context):
        access, connection = self.oauth.access_token(actor, "gmail")
        message = self.message(access, command.message_id, connection)
        token = self.oauth.sealer.seal({"message_id": command.message_id, "google_sub": connection["google_sub"], "context": context,
                                        "hash": fingerprint(message), "expires_at": int(datetime.now(UTC).timestamp()) + 900},
                                       purpose="email-preview", uid=uuid.UUID(str(connection["uid"])), actor_uid=actor)
        return {"message": message, "preview_token": token}

    def conversation_preview(self, actor, command, context):
        """Read at most one review page; the sealed snapshot never authorizes other IDs."""
        access, connection = self.oauth.access_token(actor, "gmail")
        seed = self.get(access, "/messages/" + quote(command.message_id, safe=""), {"format": "metadata", "fields": "id,threadId"})
        if seed.get("id") != command.message_id:
            raise ResourceConflict("Google returned a different message")
        thread_id = GmailPreview(message_id=seed["threadId"]).message_id
        raw = self.get(access, "/threads/" + quote(thread_id, safe=""), {"format": "metadata", "fields": "id,messages(id,threadId,internalDate)"})
        if raw.get("id") != thread_id:
            raise ResourceConflict("Google returned a different conversation")
        candidates = sorted(raw.get("messages", []), key=lambda m: (int(m["internalDate"]), m["id"]))
        if len(candidates) > 1000:
            raise ResourceConflict("Conversation exceeds 1000 messages; review individual messages")
        items, budget = [], 0
        for candidate in candidates[command.offset:command.offset + 25]:
            if candidate.get("threadId") != thread_id:
                raise ResourceConflict("Message is outside the selected conversation")
            item = self.message(access, GmailPreview(message_id=candidate["id"]).message_id, connection)
            if item["provider_thread_id"] != thread_id:
                raise ResourceConflict("Message changed conversations; review it again")
            budget += len(json.dumps(item).encode())
            if items and budget > 90000:
                break
            items.append(item)
        if not items:
            raise ResourceConflict("No messages on this review page")
        token = self.oauth.sealer.seal({"thread_id": thread_id, "google_sub": connection["google_sub"],
            "context": context, "hashes": {m["provider_message_id"]: fingerprint(m) for m in items},
            "expires_at": int(datetime.now(UTC).timestamp()) + 900},
            purpose="email-conversation-review", uid=uuid.UUID(str(connection["uid"])), actor_uid=actor)
        next_offset = command.offset + len(items)
        return {"items": items, "review_token": token, "context": context, "audience": "shared_crm_readers",
                "total_messages": len(candidates), "next_offset": next_offset if next_offset < len(candidates) else None}

    def selected_thread(self, actor, thread, known_ids=(), authorize=None):
        access, connection = self.oauth.access_token(actor, "gmail")
        if source_key(actor, connection["google_sub"]) != thread["source_key"]:
            raise ResourceConflict("This thread belongs to a different Google account")
        raw = self.get(access, "/threads/" + quote(thread["provider_thread_id"], safe=""), {"format": "metadata", "fields": "id,messages(id,threadId,internalDate)"})
        if raw.get("id") != thread["provider_thread_id"]:
            raise ResourceConflict("Google returned a different conversation")
        candidates = sorted([item for item in raw.get("messages", []) if int(item.get("internalDate", -1)) >= thread["sync_after_ms"] and item.get("id") not in known_ids], key=lambda item: (int(item["internalDate"]), item["id"]))
        messages = []
        budget, deadline = 0, monotonic() + 20
        for candidate in candidates[:25]:
            if messages and monotonic() >= deadline:
                break
            if candidate.get("threadId") != thread["provider_thread_id"]:
                raise ResourceConflict("Google metadata is outside the selected thread")
            if authorize is not None:
                authorize(connection)
            message = self.message(access, candidate["id"], connection)
            size = len(json.dumps(message).encode())
            if messages and budget + size > 2 * 1024 * 1024:
                break
            messages.append(message)
            budget += size
        if any(m["provider_thread_id"] != thread["provider_thread_id"] for m in messages):
            raise ResourceConflict("Google message is outside the selected thread")
        if len(json.dumps(messages).encode()) > 2 * 1024 * 1024:
            raise ResourceConflict("Selected thread update is too large; review individual messages")
        return messages, connection, len(messages) < len(candidates)
