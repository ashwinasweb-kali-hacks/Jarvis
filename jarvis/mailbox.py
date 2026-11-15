"""Email and calendar, only where the user has configured them.

No credentials ship with the project. The module reads:

* ``email_address``, ``email_smtp_host``, ``email_smtp_port``,
  ``email_imap_host``, ``email_imap_port`` - plain settings;
* the password/token - from the key vault under ``email-password``, so it never
  lands in ``settings.json`` or in the HUD;
* ``calendar_ics_url`` - any published ICS feed (Google, Outlook, Fastmail).

When something is missing the caller gets ``configured: false`` with the exact
missing key, never a pretend success.
"""
from __future__ import annotations

import email
import imaplib
import logging
import re
import smtplib
import ssl
import urllib.request
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.mailbox")


def _setting(key: str, default: Any = None) -> Any:
    try:
        from jarvis import settings

        return settings.get(key, default)
    except Exception:
        return default


def _password() -> str:
    try:
        from jarvis import keyvault

        return keyvault.get_key("email-password") or ""
    except Exception:
        return ""


def configured() -> Dict[str, Any]:
    address = str(_setting("email_address", "") or "").strip()
    smtp = str(_setting("email_smtp_host", "") or "").strip()
    imap = str(_setting("email_imap_host", "") or "").strip()
    password = bool(_password())
    calendar = str(_setting("calendar_ics_url", "") or "").strip()

    missing = []
    if not address:
        missing.append("email_address")
    if not smtp:
        missing.append("email_smtp_host")
    if not password:
        missing.append("email-password (key vault)")
    return {
        "configured": bool(address and smtp and password),
        "address": address,
        "smtp": smtp,
        "imap": imap,
        "password_set": password,
        "calendar_configured": bool(calendar),
        "missing": missing,
    }


# --------------------------------------------------------------------------- sending
def send(to: str, subject: str, body: str, cc: str = "") -> Dict[str, Any]:
    """Send a plain-text email over SMTP (587 STARTTLS or 465 SSL)."""
    cfg = configured()
    if not cfg["configured"]:
        return {"ok": False, "not_configured": True,
                "error": "Email is not configured. Missing: %s." % ", ".join(cfg["missing"])}
    recipient = str(to or "").strip()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", recipient):
        return {"ok": False, "error": "that does not look like an email address: %r" % to}

    host = cfg["smtp"]
    port = int(_setting("email_smtp_port", 587) or 587)
    msg = EmailMessage()
    msg["From"] = cfg["address"]
    msg["To"] = recipient
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject or "Message from JARVIS"
    msg.set_content(body or "")

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=25) as smtp:
                smtp.login(cfg["address"], _password())
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=25) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
                smtp.login(cfg["address"], _password())
                smtp.send_message(msg)
    except Exception as exc:
        logger.warning("SMTP send failed: %s", exc)
        return {"ok": False, "error": "SMTP failed: %s" % exc}
    return {"ok": True, "to": recipient, "subject": msg["Subject"], "message": "Email sent to %s." % recipient}


def compose(to: str = "", subject: str = "", body: str = "") -> Dict[str, Any]:
    """Open the user's mail client with a prefilled draft (no credentials needed)."""
    import subprocess
    import urllib.parse

    url = "mailto:%s?subject=%s&body=%s" % (
        urllib.parse.quote(to or ""),
        urllib.parse.quote(subject or ""),
        urllib.parse.quote(body or ""),
    )
    try:
        subprocess.Popen(["cmd.exe", "/c", "start", "", url], shell=False)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "message": "Opened a draft in your mail app.", "url": url[:200]}


# --------------------------------------------------------------------------- reading
def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def unread(limit: int = 5) -> Dict[str, Any]:
    """Latest unread messages over IMAP (Gmail, Outlook, any IMAP host)."""
    cfg = configured()
    if not cfg["configured"] or not cfg["imap"]:
        return {"ok": False, "not_configured": True,
                "error": "IMAP is not configured (email_imap_host)."}
    port = int(_setting("email_imap_port", 993) or 993)
    try:
        with imaplib.IMAP4_SSL(cfg["imap"], port, timeout=25) as box:
            box.login(cfg["address"], _password())
            box.select("INBOX")
            status, data = box.search(None, "UNSEEN")
            ids = (data[0] or b"").split() if status == "OK" else []
            ids = ids[-max(1, int(limit)):][::-1]
            out = []
            for msg_id in ids:
                status, payload = box.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                if status != "OK" or not payload:
                    continue
                header = email.message_from_bytes(payload[0][1])
                out.append({
                    "from": _decode(header.get("From")),
                    "subject": _decode(header.get("Subject")),
                    "date": _decode(header.get("Date")),
                })
            return {"ok": True, "count": len(out), "messages": out,
                    "message": "%d unread email%s." % (len(out), "" if len(out) == 1 else "s")}
    except Exception as exc:
        logger.warning("IMAP read failed: %s", exc)
        return {"ok": False, "error": "IMAP failed: %s" % exc}


# --------------------------------------------------------------------------- calendar
def _unfold(raw: str) -> List[str]:
    return re.sub(r"\r?\n[ \t]", "", raw).splitlines()


def _parse_dt(value: str) -> Optional[datetime]:
    text = value.strip().split(":")[-1].strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc) if text.endswith("Z") else dt
        except ValueError:
            continue
    return None


def calendar(days: int = 1) -> Dict[str, Any]:
    """Events from a published ICS feed for today (or the next N days)."""
    url = str(_setting("calendar_ics_url", "") or "").strip()
    if not url:
        return {"ok": False, "not_configured": True,
                "error": "No calendar feed configured (calendar_ics_url)."}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except Exception as exc:
        return {"ok": False, "error": "could not fetch the calendar: %s" % exc}

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=max(1, int(days)))
    events: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}
    for line in _unfold(raw):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            if current.get("start"):
                events.append(current)
            current = {}
        elif line.startswith("SUMMARY"):
            current["summary"] = line.split(":", 1)[-1].strip()
        elif line.startswith("DTSTART"):
            current["start_dt"] = _parse_dt(line)
            current["start"] = line.split(":", 1)[-1].strip()
        elif line.startswith("DTEND"):
            current["end"] = line.split(":", 1)[-1].strip()
        elif line.startswith("LOCATION"):
            current["location"] = line.split(":", 1)[-1].strip()

    todays = []
    for event in events:
        start = event.get("start_dt")
        if not start:
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if now - timedelta(hours=12) <= start <= horizon:
            todays.append({
                "summary": event.get("summary", ""),
                "start": start.isoformat(),
                "location": event.get("location", ""),
            })
    todays.sort(key=lambda e: e["start"])
    spoken = "Nothing on your calendar." if not todays else "; ".join(
        "%s at %s" % (e["summary"], e["start"][11:16]) for e in todays[:5])
    return {"ok": True, "count": len(todays), "events": todays, "message": spoken}
