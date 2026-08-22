from __future__ import annotations

import email
import imaplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup


@dataclass
class FetchedEmail:
    uid: int
    message_id: str | None
    subject: str
    sender: str
    received_at: datetime | None
    body: str


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return value


def _extract_body(msg: email.message.Message) -> str:
    """Return a plain-text body, converting HTML when needed."""
    plain: str | None = None
    html: str | None = None

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            try:
                payload = part.get_payload(decode=True)
            except Exception:  # noqa: BLE001
                continue
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except LookupError:
                text = payload.decode("utf-8", errors="replace")
            if ctype == "text/plain" and plain is None:
                plain = text
            elif ctype == "text/html" and html is None:
                html = text
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        text = (payload or b"").decode(charset, errors="replace")
        if msg.get_content_type() == "text/html":
            html = text
        else:
            plain = text

    if plain:
        return plain.strip()
    if html:
        return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    return ""


def _connect(
    host: str, port: int, username: str, password: str, use_ssl: bool
) -> imaplib.IMAP4:
    # Timeout so a bad network/DNS can't hang the whole app on startup sync.
    if use_ssl:
        conn: imaplib.IMAP4 = imaplib.IMAP4_SSL(host, port, timeout=30)
    else:
        conn = imaplib.IMAP4(host, port, timeout=30)
    conn.login(username, password)
    return conn


def test_connection(
    host: str,
    port: int,
    username: str,
    password: str,
    use_ssl: bool,
    folder: str = "INBOX",
) -> tuple[bool, str]:
    try:
        conn = _connect(host, port, username, password, use_ssl)
    except Exception as exc:  # noqa: BLE001
        return False, f"Login failed: {exc}"
    try:
        status, _ = conn.select(folder, readonly=True)
        if status != "OK":
            return False, f"Could not open folder '{folder}'."
        return True, "Connection successful."
    except Exception as exc:  # noqa: BLE001
        return False, f"Error selecting folder: {exc}"
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass


def fetch_new_emails(
    host: str,
    port: int,
    username: str,
    password: str,
    use_ssl: bool,
    folder: str,
    last_seen_uid: int | None,
    limit: int = 25,
) -> tuple[list[FetchedEmail], int | None]:
    """Fetch emails with UID greater than last_seen_uid. Returns (emails, max_uid)."""
    conn = _connect(host, port, username, password, use_ssl)
    results: list[FetchedEmail] = []
    max_uid = last_seen_uid
    try:
        status, _ = conn.select(folder, readonly=True)
        if status != "OK":
            return [], last_seen_uid

        if last_seen_uid:
            search_criteria = f"UID {last_seen_uid + 1}:*"
        else:
            search_criteria = "ALL"
        status, data = conn.uid("search", None, search_criteria)
        if status != "OK" or not data or not data[0]:
            return [], last_seen_uid

        uids = [int(x) for x in data[0].split()]
        # When seeding (no last_seen_uid), only take the most recent `limit`.
        if last_seen_uid is None and len(uids) > limit:
            uids = uids[-limit:]
        else:
            uids = uids[-limit:] if len(uids) > limit else uids

        for uid in uids:
            if last_seen_uid is not None and uid <= last_seen_uid:
                continue
            status, msg_data = conn.uid("fetch", str(uid), "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            msg = email.message_from_bytes(raw)
            received: datetime | None = None
            if msg.get("Date"):
                try:
                    received = parsedate_to_datetime(msg["Date"])
                    if received and received.tzinfo:
                        received = received.astimezone(timezone.utc).replace(tzinfo=None)
                except Exception:  # noqa: BLE001
                    received = None
            results.append(
                FetchedEmail(
                    uid=uid,
                    message_id=_decode(msg.get("Message-ID")),
                    subject=_decode(msg.get("Subject")),
                    sender=_decode(msg.get("From")),
                    received_at=received,
                    body=_extract_body(msg),
                )
            )
            max_uid = uid if max_uid is None else max(max_uid, uid)

        return results, max_uid
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
