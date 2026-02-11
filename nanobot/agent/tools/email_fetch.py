"""Email fetch tool for the agent to query the inbox on demand."""

import asyncio
from datetime import date, datetime, timedelta
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.config.schema import EmailConfig


class EmailFetchTool(Tool):
    """Fetch emails from the configured email account."""

    def __init__(self, email_config: EmailConfig):
        self._config = email_config

    @property
    def name(self) -> str:
        return "email_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch emails from the configured email account. "
            "Supports two modes: 'unread' fetches all unread/unseen emails, "
            "'recent' fetches emails from the last N hours. "
            "Does NOT mark emails as read."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["unread", "recent"],
                    "description": "Fetch mode: 'unread' for unseen emails, 'recent' for last N hours",
                },
                "hours": {
                    "type": "integer",
                    "description": "Hours to look back (for 'recent' mode, default 24)",
                    "minimum": 1,
                    "maximum": 720,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max emails to fetch (default 50)",
                    "minimum": 1,
                    "maximum": 200,
                },
            },
        }

    async def execute(
        self,
        mode: str = "unread",
        hours: int = 24,
        limit: int = 50,
        **kwargs: Any,
    ) -> str:
        from nanobot.channels.email import EmailChannel

        if not self._config.imap_host or not self._config.imap_password:
            return "Error: Email not configured. Set imap_host and imap_password in config."

        # Create a temporary EmailChannel just for fetching (bus unused for reads)
        channel = EmailChannel(self._config, bus=None)  # type: ignore[arg-type]

        try:
            if mode == "unread":
                messages = await asyncio.to_thread(
                    channel._fetch_messages,
                    search_criteria=("UNSEEN",),
                    mark_seen=False,
                    dedupe=False,
                    limit=max(1, limit),
                )
            elif mode == "recent":
                end = date.today() + timedelta(days=1)  # include today
                start = (datetime.now() - timedelta(hours=hours)).date()
                messages = await asyncio.to_thread(
                    channel.fetch_messages_between_dates,
                    start_date=start,
                    end_date=end,
                    limit=max(1, limit),
                )
            else:
                return f"Error: Unknown mode '{mode}'. Use 'unread' or 'recent'."
        except Exception as e:
            return f"Error fetching emails: {e}"

        if not messages:
            label = "unread" if mode == "unread" else f"from the last {hours} hours"
            return f"No {label} emails found."

        lines = [f"Found {len(messages)} email(s):\n"]
        for i, msg in enumerate(messages, 1):
            meta = msg.get("metadata", {})
            lines.append(f"--- Email {i} ---")
            lines.append(f"From: {msg['sender']}")
            lines.append(f"Subject: {msg.get('subject', '(no subject)')}")
            lines.append(f"Date: {meta.get('date', 'Unknown')}")
            lines.append(f"\n{msg['content']}\n")

        return "\n".join(lines)
