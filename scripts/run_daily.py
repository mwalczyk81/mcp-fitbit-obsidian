"""
Standalone daily sync script for Windows Task Scheduler.

Schedule at 7 am daily.  Syncs yesterday's Fitbit data so that overnight
sleep data is fully recorded before we write it.

Exit codes
----------
0  — success
1  — any failure (Task Scheduler can be configured to alert on non-zero exit)

Log file: <project_root>/logs/sync.log
"""
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Ensure the project root is on sys.path when the script is run directly.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_project_root / ".env")

from src.fitbit_client import FitbitClient  # noqa: E402
from src.obsidian import write_health_data  # noqa: E402


def _setup_logging() -> logging.Logger:
    log_dir = _project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(log_dir / "sync.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("run_daily")


def main() -> None:
    log = _setup_logging()

    client_id = os.getenv("CLIENT_ID", "").strip()
    client_secret = os.getenv("CLIENT_SECRET", "").strip()
    vault_dir = os.getenv("VAULT_DIR", "").strip()
    token_file = Path(
        os.getenv("TOKEN_FILE", str(_project_root / "fitbit_tokens.json"))
    )

    if not client_id or not client_secret:
        log.error("CLIENT_ID and CLIENT_SECRET must be set in .env")
        sys.exit(1)

    if not vault_dir:
        log.error("VAULT_DIR must be set in .env")
        sys.exit(1)

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    log.info("Starting daily sync for %s", yesterday)

    try:
        client = FitbitClient(client_id, client_secret, token_file)
        data = client.get_health_data(yesterday)
        path = write_health_data(vault_dir, data)
        log.info("Successfully synced %s → %s", yesterday, path)
    except Exception:
        log.exception("Failed to sync %s", yesterday)
        sys.exit(1)


if __name__ == "__main__":
    main()
