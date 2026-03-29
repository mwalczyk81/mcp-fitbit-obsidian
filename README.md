# mcp-fitbit-obsidian

A Python MCP server that syncs Fitbit health data directly into Obsidian daily notes.

Exposes tools usable in **Claude Desktop / Cowork** (stdio transport) and **Claude.ai** (SSE transport via Cloudflare Tunnel).

---

## What it does

For each day it syncs, the server writes a `## 📊 Health Summary` block into the matching daily note at `{VAULT_DIR}/01 - Daily Notes/YYYY-MM-DD.md` using Obsidian inline fields:

```markdown
## 📊 Health Summary

Weight:: 81.2 kg
Workout:: Running
Sleep:: 7h 22m
Steps:: 9,847
CaloriesBurned:: 2,341
RestingHR:: 58 bpm
AZM:: 38
```

- If the note **doesn't exist**, it is created with frontmatter and default Tasks / Notes sections.
- If the note **exists and already has a health block**, only that block is replaced — Mood, Tasks, Notes, and any other sections are untouched.
- If the note **exists but has no health block**, one is inserted before the first section.

---

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) for dependency management
- A [Fitbit developer app](https://dev.fitbit.com/apps/new) (free, Personal type)
- An Obsidian vault with daily notes at `01 - Daily Notes/YYYY-MM-DD.md`

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/yourname/mcp-fitbit-obsidian
cd mcp-fitbit-obsidian
uv sync
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `CLIENT_ID` | OAuth 2.0 Client ID from your Fitbit app |
| `CLIENT_SECRET` | OAuth 2.0 Client Secret from your Fitbit app |
| `VAULT_DIR` | Absolute path to your Obsidian vault root |
| `REDIRECT_URI` | Must match the Callback URL in your Fitbit app (`http://localhost:8080`) |
| `MCP_TRANSPORT` | `stdio` (default) for Claude Desktop, or `sse` for Claude.ai |
| `MCP_PORT` | Port for SSE transport (default `8765`) |
| `TOKEN_FILE` | Path for stored OAuth tokens (default `fitbit_tokens.json`) |

### 3. Create a Fitbit app

1. Go to [dev.fitbit.com/apps/new](https://dev.fitbit.com/apps/new)
2. Set **OAuth 2.0 Application Type** to `Personal`
3. Set **Callback URL** to `http://localhost:8080`
4. Copy the Client ID and Client Secret into `.env`

### 4. Authorise with Fitbit

```bash
uv run auth
```

This opens your browser, asks you to approve access, and saves tokens to `fitbit_tokens.json`. Tokens are refreshed automatically on every subsequent run.

---

## MCP tools

| Tool | Description |
|---|---|
| `sync_today` | Fetch today's data and write to today's note |
| `sync_yesterday` | Fetch yesterday's data (sleep is more complete the next morning) |
| `sync_date` | Sync a specific `YYYY-MM-DD` date |
| `sync_range` | Sync a date range (max 30 days) |
| `get_health_summary` | Return data as text without writing to any note |
| `get_weight_trend` | Min / max / avg / net change over a rolling window (default 30 days) |

---

## Claude Desktop integration

Add the server to `claude_desktop_config.json` (stdio transport):

```json
{
  "mcpServers": {
    "fitbit-obsidian": {
      "command": "uv",
      "args": ["run", "--directory", "C:/path/to/mcp-fitbit-obsidian", "run-server"],
      "env": {
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

## Claude.ai integration (SSE via Cloudflare Tunnel)

```bash
# Start the SSE server
MCP_TRANSPORT=sse uv run run-server

# In a separate terminal, expose it via Cloudflare Tunnel
cloudflared tunnel --url http://localhost:8765
```

Then add the tunnel URL as a remote MCP server in Claude.ai settings.

---

## Daily automation (Windows Task Scheduler)

`scripts/run_daily.py` is designed to run at 7 am daily and sync the previous day's data. It logs to `logs/sync.log` and exits with code 1 on failure so Task Scheduler can alert you.

To register it:

1. Open **Task Scheduler** → Create Basic Task
2. Trigger: **Daily** at **7:00 AM**
3. Action: **Start a program**
   - Program: `C:\path\to\mcp-fitbit-obsidian\.venv\Scripts\python.exe`
   - Arguments: `scripts/run_daily.py`
   - Start in: `C:\path\to\mcp-fitbit-obsidian`

---

## Development

```bash
# Run tests
uv run pytest -v

# Run the server manually (stdio)
uv run run-server

# Run the server manually (SSE)
MCP_TRANSPORT=sse MCP_PORT=8765 uv run run-server
```

### Project layout

```
src/
  fitbit_client.py   # Fitbit API client, HealthData dataclass, token refresh
  obsidian.py        # Daily note writer (create / replace-block / append)
  auth.py            # OAuth 2.0 authorization-code flow
  server.py          # FastMCP server, all tool definitions
scripts/
  auth.py            # `uv run auth` entrypoint
  run_daily.py       # Windows Task Scheduler entrypoint
tests/
  test_obsidian.py   # Unit tests for the note writer
logs/
  sync.log           # Written by run_daily.py
```

---

## Licence

MIT
