import base64
import json
from datetime import datetime
from typing import Any

import httpx
from pathlib import Path


class EndurainError(Exception):
    pass


class EndurainClient:
    def __init__(
        self,
        server: str,
        username: str,
        password: str,
        session_file: str = (
            "/var/lib/pirowflo-control/endurain-session.json"
        ),
    ):
        self.server = server.rstrip("/")
        self.username = username
        self.password = password

        self.base_url = f"{self.server}/api/v1"
        self.session_file = Path(session_file)

        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.session_id: str | None = None

        self._load_session()

    def _load_session(self) -> None:
        if not self.session_file.exists():
            return

        try:
            data = json.loads(
                self.session_file.read_text()
            )

            self.access_token = data.get("access_token")
            self.refresh_token = data.get("refresh_token")
            self.session_id = data.get("session_id")

        except Exception:
            self.access_token = None
            self.refresh_token = None
            self.session_id = None


    def _save_session(self) -> None:
        self.session_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.session_file.write_text(
            json.dumps(
                {
                    "access_token": self.access_token,
                    "refresh_token": self.refresh_token,
                    "session_id": self.session_id,
                }
            )
        )

        self.session_file.chmod(0o600)

    def ensure_authenticated(self) -> None:
        if not self.access_token:
            self.login()

    def refresh(self) -> bool:
        if not self.refresh_token:
            return False

        response = httpx.post(
            f"{self.base_url}/auth/refresh",
            headers={
                "X-Client-Type": "mobile",
                "Authorization": f"Bearer {self.refresh_token}",
            },
            timeout=15,
        )

        if response.status_code != 200:
            return False

        data = response.json()

        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.session_id = data["session_id"]

        self._save_session()

        return True

    def login(self) -> None:
        response = httpx.post(
            f"{self.base_url}/auth/login",
            headers={
                "X-Client-Type": "mobile",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "username": self.username,
                "password": self.password,
            },
            timeout=15,
        )

        if response.status_code != 200:
            raise EndurainError(
                f"Endurain login failed "
                f"(HTTP {response.status_code}): {response.text}"
            )

        data = response.json()

        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.session_id = data["session_id"]
        self._save_session()

    def _user_id(self) -> int:
        if not self.access_token:
            raise EndurainError("No Endurain access token")

        try:
            parts = self.access_token.split(".")

            if len(parts) != 3:
                raise ValueError("Invalid JWT")

            payload = parts[1]
            payload += "=" * (-len(payload) % 4)

            decoded = base64.urlsafe_b64decode(payload)
            data = json.loads(decoded)

            return int(data["sub"])

        except Exception as exc:
            raise EndurainError(
                f"Could not determine Endurain user ID: {exc}"
            ) from exc

    def get(self, path: str) -> httpx.Response:
        if not self.access_token:
            self.login()

        def request() -> httpx.Response:
            return httpx.get(
                f"{self.base_url}{path}",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "X-Client-Type": "mobile",
                },
                timeout=15,
            )

        response = request()

        if response.status_code != 401:
            return response

        # Access-Token abgelaufen → Refresh versuchen.
        if self.refresh():
            response = request()

            if response.status_code != 401:
                return response

        # Refresh-Session ebenfalls nicht mehr verwendbar:
        # komplett neu anmelden.
        self.login()

        return request()

    def get_rowing_activities_for_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        self.ensure_authenticated()

        user_id = self._user_id()

        page_size = 50
        max_pages = 20

        activities: list[dict[str, Any]] = []

        for page in range(1, max_pages + 1):
            response = self.get(
                f"/activities/user/{user_id}/"
                f"page_number/{page}/num_records/{page_size}"
            )

            if response.status_code != 200:
                raise EndurainError(
                    f"Could not load Endurain activities "
                    f"(HTTP {response.status_code}): {response.text}"
                )

            data = response.json()

            if not isinstance(data, list):
                raise EndurainError(
                    "Unexpected Endurain activities response"
                )

            if not data:
                break

            reached_start = False

            for activity in data:
                activity_start = datetime.fromisoformat(
                    activity["start_time"]
                )

                if activity_start < start:
                    reached_start = True
                    continue

                if activity_start >= end:
                    continue

                if activity.get("activity_type") != 13:
                    continue

                activities.append(activity)

            if reached_start or len(data) < page_size:
                break

        activities.sort(
            key=lambda activity: datetime.fromisoformat(
                activity["start_time"]
            ),
            reverse=True,
        )

        return activities

    def get_recent_rowing_activities(
        self,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        self.ensure_authenticated()

        user_id = self._user_id()

        response = self.get(
            f"/activities/user/{user_id}/"
            "page_number/1/num_records/50"
        )

        if response.status_code != 200:
            raise EndurainError(
                f"Could not load Endurain activities "
                f"(HTTP {response.status_code}): {response.text}"
            )

        data = response.json()

        if not isinstance(data, list):
            raise EndurainError(
                "Unexpected Endurain activities response"
            )

        rowing = [
            activity
            for activity in data
            if activity.get("activity_type") == 13
        ]

        rowing.sort(
            key=lambda activity: datetime.fromisoformat(
                activity["start_time"]
            ),
            reverse=True,
        )

        return rowing[:limit]
