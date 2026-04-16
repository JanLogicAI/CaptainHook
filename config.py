"""Configuration management for Jira Agent."""
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()


# Placeholder values that should be rejected during validation.
_PLACEHOLDER_BASE_URLS = {
    "https://your-domain.atlassian.net",
    "https://example.atlassian.net",
    "https://<your-domain>.atlassian.net",
}


class Config:
    """Application configuration loaded from environment variables."""

    # Jira settings (no default — must be set explicitly)
    JIRA_BASE_URL: str = os.getenv("JIRA_BASE_URL", "").strip().rstrip("/")
    JIRA_EMAIL: str = os.getenv("JIRA_EMAIL", "").strip()
    JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "").strip()

    # Discord settings
    DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "")
    DISCORD_CHANNEL_ID: str = os.getenv("DISCORD_CHANNEL_ID", "")
    DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")

    # Polling settings
    POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))

    # Codebase analysis settings
    # Path to the Claude Code CLI binary. Empty means "disabled / fall back to
    # a non-codebase-aware plan". `~` is expanded so users can set
    # CLAUDE_CLI_PATH=~/.local/bin/claude in their .env.
    CLAUDE_CLI_PATH: str = os.path.expanduser(
        os.getenv("CLAUDE_CLI_PATH", "").strip()
    )

    # State file paths
    STATE_DIR: str = os.path.join(os.path.dirname(__file__), "state")
    PROCESSED_TICKETS_FILE: str = os.path.join(STATE_DIR, "processed_tickets.json")
    AWAITING_RESPONSES_FILE: str = os.path.join(STATE_DIR, "awaiting_responses.json")

    @classmethod
    def validate(cls) -> bool:
        """Validate that required configuration is present and well-formed."""
        errors: list[str] = []

        if not cls.JIRA_EMAIL:
            errors.append("JIRA_EMAIL is not set")
        if not cls.JIRA_API_TOKEN:
            errors.append("JIRA_API_TOKEN is not set")

        if not cls.JIRA_BASE_URL:
            errors.append(
                "JIRA_BASE_URL is not set — expected something like "
                "https://your-company.atlassian.net"
            )
        elif cls.JIRA_BASE_URL in _PLACEHOLDER_BASE_URLS:
            errors.append(
                f"JIRA_BASE_URL is still the placeholder value "
                f"({cls.JIRA_BASE_URL}). Replace it with your real Jira host."
            )
        else:
            parsed = urlparse(cls.JIRA_BASE_URL)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                errors.append(
                    f"JIRA_BASE_URL is not a valid URL: {cls.JIRA_BASE_URL!r} "
                    f"(expected e.g. https://your-company.atlassian.net)"
                )

        if errors:
            print("❌ Configuration error:")
            for err in errors:
                print(f"   • {err}")
            return False
        return True
