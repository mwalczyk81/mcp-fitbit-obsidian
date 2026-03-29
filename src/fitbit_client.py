"""
Fitbit API client.

Handles token refresh, authenticated requests, and fetching all health metrics
for a given date into a HealthData dataclass.
"""
import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

_log = logging.getLogger(__name__)

TOKEN_FILE = Path("fitbit_tokens.json")

_BASE = "https://api.fitbit.com/1"
_TOKEN_URL = "https://api.fitbit.com/oauth2/token"


@dataclass
class HealthData:
    """All health metrics for a single day.

    Every field except `date` defaults to None so that partial Fitbit data
    (e.g. no weight log that day) never crashes the writer.
    `weight_unit` defaults to "kg" and is updated from the activity summary
    when the user's account uses imperial units.
    """

    date: str
    weight: Optional[float] = None
    weight_unit: Optional[str] = "kg"
    workout: Optional[str] = None
    sleep: Optional[str] = None
    steps: Optional[int] = None
    calories_burned: Optional[int] = None
    resting_hr: Optional[int] = None
    azm: Optional[int] = None  # Active Zone Minutes


class FitbitClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_file: Path = TOKEN_FILE,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_file = Path(token_file)
        self._tokens: dict = self._load_tokens()

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _load_tokens(self) -> dict:
        if not self.token_file.exists():
            raise FileNotFoundError(
                f"Token file not found: {self.token_file}\n"
                "Run `uv run auth` to authorise with Fitbit and create the token file."
            )
        return json.loads(self.token_file.read_text(encoding="utf-8"))

    def _save_tokens(self, tokens: dict) -> None:
        """Write tokens to disk, closing the file immediately (no handle leak)."""
        self.token_file.write_text(json.dumps(tokens, indent=2), encoding="utf-8")

    def _refresh_tokens(self) -> None:
        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        resp = requests.post(
            _TOKEN_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._tokens["refresh_token"],
            },
            timeout=30,
        )
        resp.raise_for_status()
        self._tokens = resp.json()
        self._save_tokens(self._tokens)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, url: str) -> dict:
        """Authenticated GET, retrying once after a 401 (expired token)."""
        headers = {"Authorization": f"Bearer {self._tokens['access_token']}"}
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 401:
            self._refresh_tokens()
            headers = {"Authorization": f"Bearer {self._tokens['access_token']}"}
            resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Health data fetching
    # ------------------------------------------------------------------

    def get_health_data(self, for_date: str) -> "HealthData":
        """Fetch all available health metrics for `for_date` (YYYY-MM-DD).

        Each metric is fetched independently; a failure on one endpoint never
        prevents the others from being collected.  Failures are logged as
        warnings so they are visible in logs without crashing the caller.
        """
        data = HealthData(date=for_date)

        # Weight
        try:
            payload = self._get(
                f"{_BASE}/user/-/body/log/weight/date/{for_date}.json"
            )
            logs = payload.get("weight", [])
            if logs:
                data.weight = logs[-1].get("weight")
        except Exception as exc:
            _log.warning("Failed to fetch weight for %s: %s", for_date, exc)

        # Steps + calories (activity summary).
        # Also detect weight unit from distanceUnit: "Mile" → imperial (lbs),
        # anything else → metric (kg).
        try:
            payload = self._get(
                f"{_BASE}/user/-/activities/date/{for_date}.json"
            )
            summary = payload.get("summary", {})
            data.steps = summary.get("steps")
            data.calories_burned = summary.get("caloriesOut")

            dist_unit = summary.get("distanceUnit", "")
            data.weight_unit = "lbs" if dist_unit == "Mile" else "kg"

            # Workout names from activity log
            activities = payload.get("activities", [])
            if activities:
                names = [
                    a.get("activityParentName", a.get("name", "Unknown"))
                    for a in activities
                ]
                data.workout = ", ".join(names)
        except Exception as exc:
            _log.warning(
                "Failed to fetch activity summary for %s: %s", for_date, exc
            )

        # Resting heart rate
        try:
            payload = self._get(
                f"{_BASE}/user/-/activities/heart/date/{for_date}/1d.json"
            )
            hr_entries = payload.get("activities-heart", [])
            if hr_entries:
                data.resting_hr = hr_entries[0].get("value", {}).get(
                    "restingHeartRate"
                )
        except Exception as exc:
            _log.warning("Failed to fetch resting HR for %s: %s", for_date, exc)

        # Active Zone Minutes
        try:
            payload = self._get(
                f"{_BASE}/user/-/activities/active-zone-minutes/date/{for_date}/1d.json"
            )
            azm_entries = payload.get("activities-active-zone-minutes", [])
            if azm_entries:
                zones = azm_entries[0].get("value", {})
                # Sum all three intensity zones
                data.azm = sum(
                    zones.get(z, 0)
                    for z in (
                        "fatBurnActiveZoneMinutes",
                        "cardioActiveZoneMinutes",
                        "peakActiveZoneMinutes",
                    )
                )
        except Exception as exc:
            _log.warning("Failed to fetch AZM for %s: %s", for_date, exc)

        # Sleep
        try:
            payload = self._get(
                f"{_BASE}/user/-/sleep/date/{for_date}.json"
            )
            total_minutes = payload.get("summary", {}).get("totalMinutesAsleep")
            if total_minutes is not None:
                hours, mins = divmod(total_minutes, 60)
                data.sleep = f"{hours}h {mins}m"
        except Exception as exc:
            _log.warning("Failed to fetch sleep for %s: %s", for_date, exc)

        return data

    def get_weights(self, start: str, end: str) -> list:
        """Fetch weight logs for a date range in a single API call.

        Uses the /body/log/weight/date/{start}/{end} range endpoint instead of
        one call per day, which would exhaust Fitbit's hourly rate limit for
        windows longer than a few days.

        Returns a list of (date_str, weight_value) tuples sorted by date
        (Fitbit returns them in ascending date order).

        Args:
            start: First date of the range, YYYY-MM-DD.
            end:   Last date of the range (inclusive), YYYY-MM-DD.
        """
        payload = self._get(
            f"{_BASE}/user/-/body/log/weight/date/{start}/{end}.json"
        )
        logs = payload.get("weight", [])
        return [
            (entry["date"], entry["weight"])
            for entry in logs
            if "date" in entry and "weight" in entry
        ]
