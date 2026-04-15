"""Configuration management for Jira Agent."""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    # Jira settings
    JIRA_BASE_URL: str = os.getenv("JIRA_BASE_URL", "https://your-domain.atlassian.net")
    JIRA_EMAIL: str = os.getenv("JIRA_EMAIL", "")
    JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "")

    # Discord settings
    DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "")
    DISCORD_CHANNEL_ID: str = os.getenv("DISCORD_CHANNEL_ID", "")
    DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")

    # Polling settings
    POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))

    # State file paths
    STATE_DIR: str = os.path.join(os.path.dirname(__file__), "state")
    PROCESSED_TICKETS_FILE: str = os.path.join(STATE_DIR, "processed_tickets.json")
    AWAITING_RESPONSES_FILE: str = os.path.join(STATE_DIR, "awaiting_responses.json")

    @classmethod
    def validate(cls) -> bool:
        """Validate that required configuration is present."""
        required = ["JIRA_EMAIL", "JIRA_API_TOKEN"]
        missing = [key for key in required if not getattr(cls, key, None)]

        if missing:
            print(f"❌ Missing required environment variables: {', '.join(missing)}")
            return False
        return True
