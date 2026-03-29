"""
CLI script: run the Fitbit OAuth flow and save tokens to fitbit_tokens.json.

Usage:
    uv run auth
    # or
    uv run python scripts/auth.py
"""
import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path when the script is run directly
# (i.e. `python scripts/auth.py`).  When invoked via the installed entry
# point (`uv run auth`) this is handled by the package install.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from dotenv import load_dotenv  # noqa: E402 — must come after sys.path fix

load_dotenv(_project_root / ".env")

from src.auth import run_oauth_flow  # noqa: E402


def main() -> None:
    client_id = os.getenv("CLIENT_ID", "").strip()
    client_secret = os.getenv("CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv("REDIRECT_URI", "http://localhost:8080").strip()

    if not client_id or not client_secret:
        print("Error: CLIENT_ID and CLIENT_SECRET must be set in .env")
        print()
        print("Steps:")
        print("  1. Go to https://dev.fitbit.com/apps/new")
        print("  2. Create an app with OAuth 2.0 Application Type = Personal")
        print(f"  3. Set the Callback URL to: {redirect_uri}")
        print("  4. Copy the Client ID and Client Secret into your .env file")
        sys.exit(1)

    print("=== Fitbit OAuth Setup ===")
    print(f"  Client ID:    {client_id}")
    print(f"  Redirect URI: {redirect_uri}")
    print()

    try:
        tokens = run_oauth_flow(client_id, client_secret, redirect_uri)
    except Exception as exc:
        print(f"\nError: {exc}")
        sys.exit(1)

    print("\nSuccess! Tokens saved to fitbit_tokens.json")
    print(f"  Access token:  {tokens['access_token'][:20]}…")
    print(f"  Refresh token: {tokens['refresh_token'][:20]}…")


if __name__ == "__main__":
    main()
