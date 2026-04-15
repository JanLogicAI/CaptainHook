"""Discord client for sending messages via webhook and bot API (threads)."""
import requests
from typing import Optional, Dict, List
from config import Config

DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_MESSAGE_LIMIT = 2000


class DiscordClient:
    """Client for sending messages to Discord via webhook and creating threads via bot API."""

    def __init__(self):
        self.webhook_url = Config.DISCORD_WEBHOOK_URL
        self.channel_id = Config.DISCORD_CHANNEL_ID
        self.bot_token = Config.DISCORD_BOT_TOKEN
        self.bot_headers = {
            "Authorization": f"Bot {self.bot_token}",
            "Content-Type": "application/json",
        } if self.bot_token else {}

    # ── Webhook methods (fallback when bot token not configured) ──

    def send_webhook_message(self, content: str, embed: Optional[Dict] = None) -> bool:
        """Send a message to Discord via webhook."""
        if not self.webhook_url:
            print("⚠️ Discord webhook URL not configured, skipping message")
            return False

        data = {"content": content}
        if embed:
            data["embeds"] = [embed]

        try:
            response = requests.post(self.webhook_url, json=data, timeout=10)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to send Discord webhook message: {e}")
            return False

    # ── Bot API methods (threads, channel messages) ──

    def create_thread(self, ticket_key: str, summary: str) -> Optional[str]:
        """Create a public thread in the configured channel. Returns thread (channel) ID."""
        if not self.bot_token or not self.channel_id:
            print("⚠️ Discord bot token or channel ID not configured, falling back to webhook")
            return None

        url = f"{DISCORD_API_BASE}/channels/{self.channel_id}/threads"
        thread_name = f"[{ticket_key}] {summary}"[:100]  # Discord limit
        data = {
            "name": thread_name,
            "type": 11,  # PUBLIC_THREAD
            "auto_archive_duration": 10080,  # 7 days
        }

        try:
            response = requests.post(url, json=data, headers=self.bot_headers, timeout=10)
            response.raise_for_status()
            thread_id = response.json().get("id")
            print(f"    🧵 Created Discord thread: {thread_name} ({thread_id})")
            return thread_id
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to create Discord thread: {e}")
            return None

    def send_thread_message(self, thread_id: str, content: str, embed: Optional[Dict] = None) -> bool:
        """Send a message inside a thread."""
        if not self.bot_token:
            return False

        url = f"{DISCORD_API_BASE}/channels/{thread_id}/messages"
        data: Dict = {}
        if content:
            data["content"] = content
        if embed:
            data["embeds"] = [embed]

        try:
            response = requests.post(url, json=data, headers=self.bot_headers, timeout=10)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to send thread message: {e}")
            return False

    def post_long_message(self, thread_id: str, text: str) -> bool:
        """Post a long message to a thread, splitting at the Discord 2000-char limit."""
        chunks = self._split_message(text)
        for chunk in chunks:
            if not self.send_thread_message(thread_id, chunk):
                return False
        return True

    # ── High-level helpers ──

    def notify_new_ticket(self, ticket_key: str, summary: str) -> Optional[str]:
        """
        Notify about a new ticket. Creates a thread if bot token is available,
        otherwise falls back to webhook. Returns thread_id if created, else None.
        """
        embed = {
            "title": f"🎫 New Ticket: {ticket_key}",
            "description": summary,
            "color": 5814783,  # Blue
            "footer": {"text": "Jira Agent"},
        }

        if self.bot_token and self.channel_id:
            thread_id = self.create_thread(ticket_key, summary)
            if thread_id:
                self.send_thread_message(thread_id, "", embed)
                return thread_id

        # Fallback to webhook
        self.send_webhook_message("", embed)
        return None

    def post_plan_to_thread(self, thread_id: str, ticket_key: str, plan: str) -> bool:
        """Post the full plan to a Discord thread, splitting if needed."""
        header = f"**📋 Implementation Plan for {ticket_key}**\n\n"
        return self.post_long_message(thread_id, header + plan)

    def notify_plan_complete(self, ticket_key: str, summary: str, thread_id: Optional[str] = None):
        """Notify that a plan has been completed."""
        embed = {
            "title": f"✅ Plan Ready: {ticket_key}",
            "description": summary,
            "color": 5763719,  # Green
            "footer": {"text": "Jira Agent"},
        }
        if thread_id and self.bot_token:
            self.send_thread_message(thread_id, "", embed)
        else:
            self.send_webhook_message("", embed)

    def ask_clarification(self, ticket_key: str, questions: list, thread_id: Optional[str] = None) -> bool:
        """Send a clarification request, preferring the thread if available."""
        content = f"🤔 **Need clarification for {ticket_key}**\n\n"
        for i, question in enumerate(questions, 1):
            content += f"{i}. {question}\n"
        content += "\n_Reply with your answers and I'll incorporate them into the plan!_"

        if thread_id and self.bot_token:
            return self.send_thread_message(thread_id, content)
        return self.send_webhook_message(content)

    # ── Internal helpers ──

    @staticmethod
    def _split_message(text: str) -> List[str]:
        """Split text into chunks that fit within Discord's message limit."""
        if len(text) <= DISCORD_MESSAGE_LIMIT:
            return [text]

        chunks = []
        while text:
            if len(text) <= DISCORD_MESSAGE_LIMIT:
                chunks.append(text)
                break

            # Try to split at a newline near the limit
            split_at = text.rfind("\n", 0, DISCORD_MESSAGE_LIMIT)
            if split_at == -1 or split_at < DISCORD_MESSAGE_LIMIT // 2:
                split_at = DISCORD_MESSAGE_LIMIT

            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")

        return chunks
