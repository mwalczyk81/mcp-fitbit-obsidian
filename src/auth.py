"""
Fitbit OAuth 2.0 authorization-code flow.

Fixes vs. the original scaffolded version:
  1. Uses `threading.Event` + a daemon thread for the CherryPy server instead of
     a busy-wait loop or blocking quickstart call.
  2. `while self.redirect_url is None` / `hasattr` check replaced with a proper
     Event.wait().
  3. Token persistence uses Path.write_text() — no leaked file handles.
"""
import base64
import json
import threading
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional

import cherrypy
import requests

TOKEN_FILE = Path("fitbit_tokens.json")

_AUTH_URL = "https://www.fitbit.com/oauth2/authorize"
_TOKEN_URL = "https://api.fitbit.com/oauth2/token"
_SCOPES = [
    "activity",
    "heartrate",
    "sleep",
    "weight",
    "profile",
]


class _CallbackHandler:
    """Minimal CherryPy app that captures the OAuth authorization code."""

    def __init__(self) -> None:
        self.code: Optional[str] = None
        # Set once the redirect has been received.
        self.received = threading.Event()

    @cherrypy.expose
    def index(self, code: str = None, error: str = None, **kwargs) -> str:  # type: ignore[override]
        if error:
            self.code = None
        else:
            self.code = code
        self.received.set()
        return (
            "<html><body>"
            "<h1>Authorization successful!</h1>"
            "<p>You can close this tab and return to the terminal.</p>"
            "</body></html>"
        )


def _save_tokens(tokens: dict, token_file: Path) -> None:
    """Write tokens to disk, closing the handle immediately."""
    token_file.write_text(json.dumps(tokens, indent=2), encoding="utf-8")


def run_oauth_flow(
    client_id: str,
    client_secret: str,
    redirect_uri: str = "http://localhost:8080",
    token_file: Path = TOKEN_FILE,
) -> dict:
    """Run the full OAuth2 authorization-code flow.

    Opens the browser, waits for the redirect, exchanges the code for tokens,
    saves them to `token_file`, and returns the token dict.

    Raises
    ------
    RuntimeError
        If the user denies access or the flow times out after 120 s.
    """
    handler = _CallbackHandler()

    # Silence CherryPy's access/error logs so they don't pollute the terminal.
    cherrypy.config.update(
        {
            "server.socket_host": "127.0.0.1",
            "server.socket_port": 8080,
            "log.screen": False,
            "log.access_file": "",
            "log.error_file": "",
        }
    )

    # quickstart() calls engine.block(), which would hang the main thread, so
    # we run it in a daemon thread.  The daemon flag ensures it is killed
    # automatically when the main thread exits.
    server_thread = threading.Thread(
        target=cherrypy.quickstart,
        args=(handler,),
        kwargs={"config": {"/": {}}},
        daemon=True,
    )
    server_thread.start()

    # Build the authorization URL and open the browser.
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(_SCOPES),
        "expires_in": "604800",
    }
    auth_url = _AUTH_URL + "?" + urllib.parse.urlencode(params)
    print(f"Opening browser for Fitbit authorization…")
    print(f"If the browser does not open automatically, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    # Block until the redirect arrives (or timeout after 2 minutes).
    received = handler.received.wait(timeout=120)
    if not received or handler.code is None:
        raise RuntimeError(
            "OAuth flow timed out or was denied.  "
            "Did you approve access in the browser?"
        )

    # Exchange the authorization code for tokens.
    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode()
    resp = requests.post(
        _TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": handler.code,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    resp.raise_for_status()
    tokens = resp.json()

    _save_tokens(tokens, Path(token_file))

    # Shut down CherryPy cleanly.
    cherrypy.engine.exit()

    return tokens
