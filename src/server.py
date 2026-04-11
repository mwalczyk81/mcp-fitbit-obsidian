"""
MCP server — exposes Fitbit sync tools via the `mcp` Python SDK.

Transports
----------
stdio (default)  — for Claude Desktop / Cowork; set MCP_TRANSPORT=stdio
sse              — for Claude.ai via Cloudflare Tunnel; set MCP_TRANSPORT=sse
                   Port controlled by MCP_PORT (default 8765).

Entry point: `uv run run-server`  or  `uv run python src/server.py`
"""

import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from src.fitbit_client import FitbitClient, HealthData
from src.obsidian import write_health_data

load_dotenv()

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
VAULT_DIR = os.getenv("VAULT_DIR", "")
TOKEN_FILE = Path(os.getenv("TOKEN_FILE", "fitbit_tokens.json"))
LOCALE = os.getenv("LOCALE", "en_US")
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
MCP_PORT = int(os.getenv("MCP_PORT", "8765"))

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------
mcp = FastMCP("fitbit-obsidian")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _client() -> FitbitClient:
    return FitbitClient(CLIENT_ID, CLIENT_SECRET, TOKEN_FILE, LOCALE)


def _summarise(data: HealthData) -> str:
    """Format a HealthData object as a multi-line human-readable string."""
    unit = data.weight_unit or "kg"
    lines = [f"Health data for {data.date}:"]
    if data.weight is not None:
        lines.append(f"  Weight:          {data.weight} {unit}")
    if data.sleep is not None:
        lines.append(f"  Sleep:           {data.sleep}")
    if data.steps is not None:
        lines.append(f"  Steps:           {data.steps:,}")
    if data.calories_burned is not None:
        lines.append(f"  Calories burned: {data.calories_burned:,}")
    if data.resting_hr is not None:
        lines.append(f"  Resting HR:      {data.resting_hr} bpm")
    if data.azm is not None:
        lines.append(f"  Active Zone Min: {data.azm}")
    if data.workout is not None:
        lines.append(f"  Workout:         {data.workout}")
    return "\n".join(lines)


def _brief(data: HealthData) -> str:
    """Format key HealthData fields as a compact single-line string."""
    unit = data.weight_unit or "kg"
    parts = []
    if data.weight is not None:
        parts.append(f"Weight: {data.weight} {unit}")
    if data.steps is not None:
        parts.append(f"Steps: {data.steps:,}")
    if data.sleep is not None:
        parts.append(f"Sleep: {data.sleep}")
    if data.calories_burned is not None:
        parts.append(f"Cal: {data.calories_burned:,}")
    return ", ".join(parts) if parts else "no data"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def sync_today() -> str:
    """Fetch today's Fitbit data and write it to today's Obsidian daily note."""
    try:
        today = date.today().isoformat()
        client = _client()
        data = await asyncio.to_thread(client.get_health_data, today)
        path = await asyncio.to_thread(write_health_data, VAULT_DIR, data)
        return f"Synced {today} → {path}\n{_summarise(data)}"
    except Exception as exc:
        return f"Error syncing today: {exc}"


@mcp.tool()
async def sync_yesterday() -> str:
    """Fetch yesterday's Fitbit data and write it to yesterday's daily note.

    Sleep data is more complete when fetched the following morning, so this
    tool is ideal when run at 7 am daily.
    """
    try:
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        client = _client()
        data = await asyncio.to_thread(client.get_health_data, yesterday)
        path = await asyncio.to_thread(write_health_data, VAULT_DIR, data)
        return f"Synced {yesterday} → {path}\n{_summarise(data)}"
    except Exception as exc:
        return f"Error syncing yesterday: {exc}"


@mcp.tool()
async def sync_date(date_str: str) -> str:
    """Sync Fitbit data for a specific date to the matching Obsidian daily note.

    Args:
        date_str: Target date in YYYY-MM-DD format.
    """
    try:
        client = _client()
        data = await asyncio.to_thread(client.get_health_data, date_str)
        path = await asyncio.to_thread(write_health_data, VAULT_DIR, data)
        return f"Synced {date_str} → {path}\n{_summarise(data)}"
    except Exception as exc:
        return f"Error syncing {date_str}: {exc}"


@mcp.tool()
async def sync_range(start_date: str, end_date: str) -> str:
    """Sync Fitbit data for every date in a range (max 30 days).

    Args:
        start_date: First date, YYYY-MM-DD.
        end_date:   Last date (inclusive), YYYY-MM-DD.
    """
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        if end < start:
            return "Error: end_date must be on or after start_date."
        if (end - start).days > 30:
            return "Error: Date range must be 30 days or fewer."

        client = _client()
        results: list[str] = []
        current = start
        while current <= end:
            ds = current.isoformat()
            try:
                data = await asyncio.to_thread(client.get_health_data, ds)
                path = await asyncio.to_thread(write_health_data, VAULT_DIR, data)
                results.append(f"  {ds}: {_brief(data)} → {path}")
            except Exception as exc:
                results.append(f"  {ds}: error — {exc}")
            current += timedelta(days=1)

        total = len(results)
        return f"Synced {total} day(s):\n" + "\n".join(results)
    except Exception as exc:
        return f"Error: {exc}"


@mcp.tool()
async def get_health_summary(start_date: str, end_date: str) -> str:
    """Return health data as formatted text without writing to any note.

    Useful for a quick overview before deciding whether to sync.

    Args:
        start_date: First date, YYYY-MM-DD.
        end_date:   Last date (inclusive), YYYY-MM-DD.
    """
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        if end < start:
            return "Error: end_date must be on or after start_date."
        if (end - start).days > 30:
            return "Error: Date range must be 30 days or fewer."

        client = _client()
        summaries: list[str] = []
        current = start
        while current <= end:
            ds = current.isoformat()
            try:
                data = await asyncio.to_thread(client.get_health_data, ds)
                summaries.append(_summarise(data))
            except Exception as exc:
                summaries.append(f"{ds}: error — {exc}")
            current += timedelta(days=1)

        return "\n\n".join(summaries)
    except Exception as exc:
        return f"Error: {exc}"


@mcp.tool()
async def get_weight_trend(days: int = 30) -> str:
    """Return weight trend stats (min, max, avg, net change) over recent days.

    Uses a single Fitbit range API call instead of one call per day, avoiding
    rate-limit exhaustion for windows longer than a few days.

    Args:
        days: How many days to look back, including today (default 30).
    """
    try:
        end = date.today()
        start = end - timedelta(days=days - 1)

        client = _client()
        try:
            weights: list[tuple[str, float]] = await asyncio.to_thread(
                client.get_weights, start.isoformat(), end.isoformat()
            )
        except Exception as exc:
            _log.warning("get_weights failed for %s to %s: %s", start, end, exc)
            weights = []

        if not weights:
            return f"No weight data found in the last {days} day(s)."

        values = [w for _, w in weights]
        avg = sum(values) / len(values)
        net = values[-1] - values[0]
        min_val = min(values)
        max_val = max(values)
        min_date = weights[values.index(min_val)][0]
        max_date = weights[values.index(max_val)][0]

        lines = [
            f"Weight trend — last {days} day(s) ({len(weights)} data point(s)):",
            f"  Min:        {min_val:.1f} kg  ({min_date})",
            f"  Max:        {max_val:.1f} kg  ({max_date})",
            f"  Average:    {avg:.1f} kg",
            f"  Net change: {net:+.1f} kg  ({weights[0][0]} → {weights[-1][0]})",
        ]
        return "\n".join(lines)
    except Exception as exc:
        return f"Error: {exc}"


@mcp.tool()
def get_current_time() -> str:
    """Return the current date and time in the US Central timezone (America/Chicago).

    Automatically accounts for daylight saving time — displays CDT in summer
    and CST in winter.
    """
    central = ZoneInfo("America/Chicago")
    now = datetime.now(tz=central)
    # Build the string manually to avoid platform-specific no-padding strftime
    # directives (%-d/%-I on Linux vs %#d/%#I on Windows).
    day_name = now.strftime("%A")
    month_name = now.strftime("%B")
    hour_12 = now.hour % 12 or 12  # convert 0 → 12 for midnight
    am_pm = now.strftime("%p")
    tz_abbr = now.strftime("%Z")  # "CDT" or "CST" depending on DST
    return f"{day_name}, {month_name} {now.day}, {now.year} at {hour_12}:{now.minute:02d} {am_pm} {tz_abbr}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    if MCP_TRANSPORT == "sse":
        mcp.run(transport="sse", host="0.0.0.0", port=MCP_PORT)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
