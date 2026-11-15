"""WhatsApp tool - real messages and calls through the WhatsApp app on this PC.

The machine already has WhatsApp installed and signed in, so the assistant uses
that session: it opens the chat through the ``whatsapp://`` protocol, types the
message in the composer and sends it, or starts a voice call.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from jarvis.tools.base import Tool

logger = logging.getLogger("jarvis.tools.whatsapp")


class WhatsAppTool(Tool):
    name = "whatsapp"
    description = (
        "Send WhatsApp messages and place WhatsApp calls using the WhatsApp app "
        "signed in on this PC. Targets can be a phone number or a contact name."
    )
    risk = "safe"
    schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "send_message",
                    "call",
                    "unread_messages",
                    "recent_messages",
                    "read_contact",
                    "remember",
                    "contacts",
                    "status",
                    "allow",
                ],
                "description": "What to do on WhatsApp",
            },
            "target": {
                "type": "string",
                "description": "Contact name or phone number",
            },
            "text": {
                "type": "string",
                "description": "Message body",
            },
            "limit": {
                "type": "integer",
                "description": "Number of recent messages to return",
            },
            "name": {
                "type": "string",
                "description": "Contact name to remember",
            },
            "number": {
                "type": "string",
                "description": "Phone number to remember or allow",
            },
        },
        "required": ["action"],
    }

    def run(self, **kwargs: Any) -> Dict[str, Any]:
        from jarvis import wa

        action = str(kwargs.get("action", "")).strip().lower()
        target = str(kwargs.get("target", "") or "").strip()
        text = str(kwargs.get("text", "") or "")

        if action == "send_message":
            result = wa.send_message(target, text)
            result.setdefault("action", "send_message")
            return result

        if action == "call":
            result = wa.start_call(target)
            result.setdefault("action", "call")
            return result

        if action in ("unread_messages", "unread", "unreads"):
            result = wa.get_unread_messages()
            result.setdefault("action", "unread_messages")
            return result

        if action in ("recent_messages", "recent", "recents"):
            lim = int(kwargs.get("limit", 5) or 5)
            result = wa.get_recent_messages(limit=lim)
            result.setdefault("action", "recent_messages")
            return result

        if action in ("read_contact", "read_chat"):
            result = wa.read_contact_message(target)
            result.setdefault("action", "read_contact")
            return result

        if action == "allow":
            number = str(kwargs.get("number", "") or target).strip()
            allowed = wa.allow_number(number)
            return {
                "ok": True,
                "action": "allow",
                "number": wa.normalize_number(number),
                "allowed": allowed,
                "message": "{0} is now allowed, sir.".format(wa.normalize_number(number)),
            }

        if action == "remember":
            name = str(kwargs.get("name", "") or target).strip()
            number = str(kwargs.get("number", "") or "").strip()
            if not name or not number:
                return {"ok": False, "action": "remember", "error": "name and number are needed"}
            data = wa.save_contact(name, number)
            return {
                "ok": True,
                "action": "remember",
                "name": name,
                "number": wa.normalize_number(number),
                "contacts": len(data),
                "message": "I will remember {0} as {1}.".format(name, wa.normalize_number(number)),
            }

        if action == "contacts":
            contacts = wa.load_contacts()
            return {
                "ok": True,
                "action": "contacts",
                "count": len(contacts),
                "contacts": contacts,
                "message": "I know {0} contact(s).".format(len(contacts)),
            }

        if action == "status":
            info = wa.status()
            return {
                "ok": True,
                "action": "status",
                "status": info,
                "message": (
                    "WhatsApp is {0} on this PC. Allowed numbers: {1}.".format(
                        "ready" if info.get("ready") else "not available",
                        ", ".join(info.get("allowed_numbers") or []) or "none",
                    )
                ),
            }

        return {"ok": False, "action": action, "error": "Unknown WhatsApp action: {0}".format(action)}


__all__ = ["WhatsAppTool"]
