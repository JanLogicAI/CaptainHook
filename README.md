# Jira Agent 🤖

A Python-based agent that automatically polls your Jira board for assigned tickets, analyzes them, and generates detailed implementation plans — with optional Discord integration for interactive clarification and codebase-aware analysis powered by Claude Code.

## ✨ Features

- 🔄 **Automatic Polling** — Continuously monitors Jira for new tickets assigned to you
- 📝 **Smart Plan Generation** — Creates detailed implementation plans with steps, considerations, and complexity estimation
- 🧠 **Codebase-Aware Analysis** — Pre-searches your codebase and uses Claude Code to generate project-specific plans
- 💬 **Discord Integration** — Creates threads for each ticket, asks clarification questions, and posts completed plans
- 💾 **State Tracking** — Remembers which tickets have been processed so nothing gets missed
- 📊 **Complexity Estimation** — Rates each ticket as Low 🟢, Medium 🟡, or High 🔴
- 🌐 **Jira Comments** — Auto-posts generated plans as comments on the original Jira tickets
- 🔍 **Smart Keyword Extraction** — Extracts meaningful keywords from ticket descriptions, including Dutch → English translation

## 📋 Prerequisites

- **Python 3.8+**
- **Jira Cloud** account with API access
- **Discord** (optional, for interactive planning)
- **Claude Code CLI** (optional, for codebase-aware analysis)
- **ripgrep** (`rg`) recommended for faster codebase search (falls back to `grep`)

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/JanLogicAI/jira-agent.git
cd jira-agent
```

### 2. Set up a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure your environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Jira Configuration (required)
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your_jira_api_token_here
JIRA_BASE_URL=https://your-domain.atlassian.net

# Discord Configuration (optional)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxx/xxx
DISCORD_CHANNEL_ID=123456789
DISCORD_BOT_TOKEN=your_discord_bot_token

# Polling Configuration
POLL_INTERVAL_SECONDS=300
```

### 5. Run the agent

```bash
python main.py
```

The agent will start polling Jira every 5 minutes (configurable) and begin processing your assigned tickets.

## ⚙️ Configuration

### Required: Jira API Token

1. Go to <https://id.atlassian.com/manage-profile/security/api-tokens>
2. Click **"Create API token"**
3. Give it a name (e.g., "Jira Agent")
4. Copy the token into your `.env` file as `JIRA_API_TOKEN`

### Optional: Discord Integration

The agent can send ticket notifications, ask clarification questions, and post completed plans to Discord. There are two levels of integration:

#### Option A: Webhook Only (Simple — No Bot Required)

A webhook lets the agent send messages to a specific channel. No bot account needed.

1. Open **Discord** and go to the server where you want notifications
2. Navigate to the channel (or create a new one, e.g. `#jira-agent`)
3. Click the ⚙️ gear icon next to the channel name → **Edit Channel**
4. Go to **Integrations** → **Webhooks**
5. Click **"New Webhook"**
6. Give it a name (e.g. "Jira Agent") and optionally upload an avatar
7. Click **"Copy Webhook URL"**
8. Paste it into your `.env` as `DISCORD_WEBHOOK_URL`

Your `.env` should look like:
```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/1234567890/abcdef...
```

With just a webhook, the agent will:
- ✅ Send ticket notifications
- ✅ Post plan completion messages
- ❌ Cannot create threads
- ❌ Cannot send clarification questions (plans are generated without asking)

#### Option B: Bot + Webhook (Full Interactive Experience)

For threaded conversations per ticket and interactive clarification:

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **"New Application"** → give it a name (e.g. "Jira Agent") → Create
3. Go to the **"Bot"** tab on the left sidebar
4. Click **"Reset Token"** → **"Copy"** the bot token
5. Under **"Privileged Gateway Intents"**, enable:
   - ✅ **Message Content Intent**
6. Go to **"OAuth2"** → **"URL Generator"**
7. Under **Scopes**, select: `bot`
8. Under **Bot Permissions**, select:
   - ✅ Send Messages
   - ✅ Create Public Threads
   - ✅ Send Messages in Threads
   - ✅ Embed Links
9. Copy the generated URL at the bottom and open it in your browser to invite the bot to your server
10. Set up a webhook in your notification channel (follow **Option A** steps above)

Your `.env` should look like:
```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/1234567890/abcdef...
DISCORD_CHANNEL_ID=1234567890123456789
DISCORD_BOT_TOKEN=your_discord_bot_token_here
```

**How to get your Channel ID** (enable Developer Mode first):
1. Discord Settings → Advanced → Enable **Developer Mode**
2. Right-click the channel → **"Copy Channel ID"**

With the full bot setup, the agent will:
- ✅ Create a **separate thread** for each ticket
- ✅ Post plan details inside the thread
- ✅ Ask clarification questions in the thread
- ✅ Notify when plans are complete

### Optional: Codebase-Aware Analysis

For project-specific implementation plans that reference actual code:

1. Install [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
2. Set `CLAUDE_CLI_PATH` in your `.env` to the absolute path of the `claude` binary (e.g. `~/.local/bin/claude` — `~` is expanded). If left blank, the agent falls back to looking for `claude` on your `PATH`; if neither is available, codebase-aware analysis is skipped.
3. Create a `repo_mappings.json` file mapping Jira project prefixes to local repo paths:

```bash
cp repo_mappings.example.json repo_mappings.json
```

Edit `repo_mappings.json`:

```json
{
    "PROJ": "/home/user/projects/my-project",
    "WEB": "/home/user/projects/web-app",
    "API": "/home/user/projects/api-service"
}
```

When a ticket like `PROJ-123` comes in, the agent will:
1. Look up the repo path for the `PROJ` prefix
2. Extract keywords from the ticket title and description
3. Search the codebase with `ripgrep` for relevant files
4. Feed the context to Claude Code for a targeted implementation plan

**Note:** `repo_mappings.json` is in `.gitignore` — it contains your local paths.

## 🏗️ Project Structure

```
jira-agent/
├── main.py                  # Entry point, polling loop
├── config.py                # Configuration management (env vars)
├── jira_client.py           # Jira API wrapper (REST v2/v3)
├── discord_client.py        # Discord webhook + bot API client
├── state_manager.py         # Tracks processed/awaiting tickets
├── plan_generator.py        # Plan generation with complexity estimation
├── codebase_analyzer.py     # Codebase search + Claude Code integration
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── repo_mappings.example.json  # Repository mapping template
├── .gitignore
├── README.md
├── state/                   # Runtime state (auto-created, gitignored)
│   ├── processed_tickets.json
│   └── awaiting_responses.json
└── plans/                   # Generated plans (auto-created, gitignored)
    └── PROJ-123_20260415_103000.md
```

## 🔄 How It Works

### Polling Flow

```
┌─────────────┐
│   Start Up   │
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│  Poll Jira API   │◄──────────────────┐
│  (every N sec)   │                    │
└──────┬──────────┘                    │
       │                               │
       ▼                               │
┌──────────────────┐                   │
│  Get Assigned    │                   │
│  Tickets         │                   │
└──────┬──────────┘                    │
       │                               │
       ▼                               │
  For each ticket:                     │
       │                               │
       ├── Already processed? ── Skip  │
       │                               │
       ├── Awaiting response? ── Skip  │
       │                               │
       └── New ticket ──────────┐      │
                                  │    │
                                  ▼    │
                    ┌─────────────────┐│
                    │  Analyze Ticket  ││
                    └───────┬─────────┘│
                            │          │
              ┌─────────────┴──────┐   │
              │                    │   │
         Needs clarification?   Clear  │
              │                    │   │
              ▼                    ▼   │
     ┌────────────────┐   ┌───────────┴──┐
     │ Ask via Discord │   │ Generate Plan │
     │ Mark awaiting   │   └───────┬──────┘
     └────────────────┘           │
                                  ▼
                    ┌──────────────────────┐
                    │ • Save plan to file   │
                    │ • Post to Jira comment│
                    │ • Post to Discord     │
                    │ • Mark completed      │
                    └──────────┬───────────┘
                               │
                               └──── Wait & Repeat ────┘
```

### Plan Generation

Plans include:
- **Ticket metadata** — key, summary, priority, status, labels, components
- **Implementation steps** — generated based on ticket type (API, frontend, bug, etc.)
- **Questions & considerations** — potential risks and dependencies
- **Definition of done** — standard checklist for completion
- **Complexity estimation** — Low 🟢 / Medium 🟡 / High 🔴 based on description length, components, and priority

### Codebase-Aware Plans (with Claude Code)

When repo mappings are configured and Claude Code is installed:

1. **Keyword extraction** — Pulls meaningful terms from the ticket, including Dutch → English translation
2. **Code search** — Uses `ripgrep` to find relevant files and code snippets (capped at 15K chars)
3. **Targeted Claude prompt** — Sends pre-searched context to Claude Code for a fast, specific plan (~30s)
4. **Fallback** — If pre-search finds nothing, falls back to full repo analysis (slower, ~5min)

## 🛠️ Running as a Service

### macOS (launchd)

Create `~/Library/LaunchAgents/com.jiraagent.plist`. Substitute `/path/to/jira-agent` with the absolute path to this checkout (e.g. `/Users/<you>/Developer/jira-agent`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.jiraagent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/jira-agent/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/jira-agent</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/path/to/jira-agent/logs/jira-agent.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/jira-agent/logs/jira-agent.stderr.log</string>
</dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.jiraagent.plist
```

### Linux (systemd)

Create `/etc/systemd/system/jira-agent.service`:

```ini
[Unit]
Description=Jira Agent
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/jira-agent
ExecStart=/path/to/jira-agent/venv/bin/python main.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable jira-agent
sudo systemctl start jira-agent
```

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

```bash
docker build -t jira-agent .
docker run -d --name jira-agent --env-file .env jira-agent
```

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `requests` | HTTP client for Jira and Discord APIs |
| `python-dotenv` | Load environment variables from `.env` file |

That's it. Just two dependencies.

## 🔒 Security Notes

- **Never commit your `.env` file** — it's in `.gitignore` for a reason
- `repo_mappings.json` is also gitignored (contains local paths)
- The Jira API token has the same permissions as your account — consider using a dedicated service account
- Discord bot tokens should be kept secret; rotate immediately if leaked

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| "Configuration error: JIRA_BASE_URL is not set / is still the placeholder value" | Set `JIRA_BASE_URL` in `.env` to your real Jira host (e.g. `https://acme.atlassian.net`). The example placeholder is rejected on purpose. |
| "Missing required environment variables" | Make sure `.env` exists with `JIRA_EMAIL`, `JIRA_API_TOKEN`, and `JIRA_BASE_URL` |
| "Jira rejected credentials (401/403)" | The startup self-check couldn't authenticate — regenerate the API token at <https://id.atlassian.com/manage-profile/security/api-tokens> and verify `JIRA_EMAIL` matches the token owner. After 3 consecutive auth failures in the poll loop the agent exits instead of looping silently. |
| "Jira returned 404 for /rest/api/3/myself" | `JIRA_BASE_URL` is pointing at the wrong host. |
| "Failed to send Discord message" | Check webhook URL and bot permissions |
| "Request to Jira timed out" | Network issue; agent will retry next cycle |
| Codebase analysis not working | Install Claude Code CLI, set `CLAUDE_CLI_PATH` in `.env` (or ensure `claude` is on `PATH`), and configure `repo_mappings.json` |
| `rg` not found | Install [ripgrep](https://github.com/BurntSushi/ripgrep) or accept slower `grep` fallback |

### Startup self-check

On launch the agent calls `GET /rest/api/3/myself` once before entering the polling loop. If this fails (bad URL, bad credentials, network), the agent prints an explicit reason and exits with code `2` — it will **not** start polling with broken auth. Token values are never printed, only masked error messages.

## 🗺️ Roadmap

- [ ] Receive Discord responses and incorporate into plans
- [ ] Multi-user support (multiple Jira accounts)
- [ ] Webhook mode (real-time instead of polling)
- [ ] Web dashboard for plan management
- [ ] Support for Jira Server / Data Center
- [ ] GitHub Issues integration
- [ ] Configurable plan templates

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

## 🤝 Contributing

Contributions are welcome! Feel free to:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes
4. Open a Pull Request

---

*Built with ☕ and 🤖 by [JanLogicAI](https://github.com/JanLogicAI)*
