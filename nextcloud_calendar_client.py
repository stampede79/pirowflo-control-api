import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4
from urllib.parse import urljoin

import httpx


class NextcloudCalendarError(Exception):
    pass


class NextcloudCalendarClient:
    def __init__(
        self,
        calendar_url: str,
        username: str,
        app_password: str,
    ):
        self.calendar_url = calendar_url
        self.username = username
        self.app_password = app_password

    @staticmethod
    def _caldav_date(value: datetime) -> str:
        return value.strftime("%Y%m%dT%H%M%SZ")

    @staticmethod
    def _unfold_ics(ics: str) -> str:
        return re.sub(r"\r?\n[ \t]", "", ics)

    @classmethod
    def _ics_value(
        cls,
        ics: str,
        property_name: str,
    ) -> str | None:
        unfolded = cls._unfold_ics(ics)

        match = re.search(
            rf"^{re.escape(property_name)}(?:;[^:]*)?:(.*)$",
            unfolded,
            flags=re.IGNORECASE | re.MULTILINE,
        )

        if match is None:
            return None

        value = match.group(1)

        return (
            value
            .replace(r"\n", "\n")
            .replace(r"\,", ",")
            .replace(r"\;", ";")
            .replace(r"\\", "\\")
        )

    @staticmethod
    def _parse_ics_datetime(
        value: str,
    ) -> tuple[datetime, bool]:
        if len(value) == 8:
            return (
                datetime.strptime(value, "%Y%m%d"),
                True,
            )

        if value.endswith("Z"):
            return (
                datetime.strptime(
                    value,
                    "%Y%m%dT%H%M%SZ",
                ),
                False,
            )

        return (
            datetime.strptime(
                value[:15],
                "%Y%m%dT%H%M%S",
            ),
            False,
        )

    def get_events_for_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        body = f"""<?xml version="1.0" encoding="utf-8" ?>
<c:calendar-query
    xmlns:d="DAV:"
    xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:getetag />
    <c:calendar-data />
  </d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VEVENT">
        <c:time-range
            start="{self._caldav_date(start)}"
            end="{self._caldav_date(end)}" />
      </c:comp-filter>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>
"""

        response = httpx.request(
            "REPORT",
            self.calendar_url,
            auth=(
                self.username,
                self.app_password,
            ),
            headers={
                "Content-Type":
                    "application/xml; charset=utf-8",
                "Depth": "1",
            },
            content=body.encode("utf-8"),
            timeout=15,
        )

        if response.status_code != 207:
            raise NextcloudCalendarError(
                f"CalDAV HTTP {response.status_code}: "
                f"{response.text}"
            )

        return self._parse_events(response.text)

    def _parse_events(
        self,
        xml: str,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        root = ET.fromstring(xml)

        namespaces = {
            "d": "DAV:",
            "c": "urn:ietf:params:xml:ns:caldav",
        }

        for response in root.findall(
            ".//d:response",
            namespaces,
        ):
            href_node = response.find(
                "d:href",
                namespaces,
            )

            etag_node = response.find(
                ".//d:getetag",
                namespaces,
            )

            calendar_node = response.find(
                ".//c:calendar-data",
                namespaces,
            )

            if (
                href_node is None
                or calendar_node is None
                or not calendar_node.text
            ):
                continue

            ics = html.unescape(calendar_node.text)

            summary = self._ics_value(
                ics,
                "SUMMARY",
            )
            description = self._ics_value(
                ics,
                "DESCRIPTION",
            )
            dtstart = self._ics_value(
                ics,
                "DTSTART",
            )
            dtend = self._ics_value(
                ics,
                "DTEND",
            )
            uid = self._ics_value(
                ics,
                "UID",
            )

            if summary is None or dtstart is None:
                continue

            try:
                start, all_day = (
                    self._parse_ics_datetime(
                        dtstart,
                    )
                )
            except ValueError:
                continue

            end = None

            if dtend is not None:
                try:
                    end, _ = self._parse_ics_datetime(
                        dtend,
                    )
                except ValueError:
                    end = None

            events.append(
                {
                    "summary": summary,
                    "description":
                        description or "",
                    "start": start,
                    "all_day": all_day,
                    "end": end,
                    "href": html.unescape(
                        href_node.text or ""
                    ),
                    "etag": (
                        html.unescape(etag_node.text)
                        if etag_node is not None
                        and etag_node.text
                        else None
                    ),
                    "uid": uid,
                    "raw_ics": ics,
                }
            )

        events.sort(
            key=lambda event: event["start"],
            reverse=True,
        )

        return events

    @staticmethod
    def _escape_ics_text(
        value: str,
    ) -> str:
        return (
            value
            .replace("\\", "\\\\")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\n", r"\n")
            .replace(",", r"\,")
            .replace(";", r"\;")
        )
    
    @classmethod
    def _replace_ics_description(
        cls,
        ics: str,
        description: str,
    ) -> str:
        escaped = cls._escape_ics_text(
            description
        )

        # Nur DESCRIPTION inklusive eventuell
        # gefalteter Folgezeilen ersetzen.
        pattern = re.compile(
            r"^DESCRIPTION(?:;[^:]*)?:.*"
            r"(?:\r?\n[ \t].*)*",
            flags=re.IGNORECASE | re.MULTILINE,
        )

        replacement = (
            f"DESCRIPTION:{escaped}"
        )

        if pattern.search(ics):
            return pattern.sub(
                lambda _: replacement,
                ics,
                count=1,
            )

        # DESCRIPTION fehlt vollständig.
        marker = "END:VEVENT"

        if marker not in ics:
            raise NextcloudCalendarError(
                "Calendar event has no VEVENT"
            )

        newline = (
            "\r\n"
            if "\r\n" in ics
            else "\n"
        )

        return ics.replace(
            marker,
            (
                f"DESCRIPTION:{escaped}"
                f"{newline}"
                f"{marker}"
            ),
            1,
        )

    @classmethod
    def _replace_ics_date(
        cls,
        ics: str,
        new_date: datetime,
    ) -> str:
        date_value = new_date.strftime(
            "%Y%m%d"
        )

        next_day = (
            new_date
            + timedelta(days=1)
        ).strftime("%Y%m%d")

        unfolded = cls._unfold_ics(ics)

        start_pattern = re.compile(
            r"^DTSTART(?:;[^:]*)?:.*$",
            flags=re.IGNORECASE | re.MULTILINE,
        )

        end_pattern = re.compile(
            r"^DTEND(?:;[^:]*)?:.*$",
            flags=re.IGNORECASE | re.MULTILINE,
        )

        if not start_pattern.search(unfolded):
            raise NextcloudCalendarError(
                "Calendar event has no DTSTART"
            )

        updated = start_pattern.sub(
            f"DTSTART;VALUE=DATE:{date_value}",
            unfolded,
            count=1,
        )

        if end_pattern.search(updated):
            updated = end_pattern.sub(
                f"DTEND;VALUE=DATE:{next_day}",
                updated,
                count=1,
            )
        else:
            marker = "END:VEVENT"

            if marker not in updated:
                raise NextcloudCalendarError(
                    "Calendar event has no VEVENT"
                )

            newline = (
                "\r\n"
                if "\r\n" in updated
                else "\n"
            )

            updated = updated.replace(
                marker,
                (
                    f"DTEND;VALUE=DATE:{next_day}"
                    f"{newline}"
                    f"{marker}"
                ),
                1,
            )

        return updated

    def update_event_description(
        self,
        event: dict[str, Any],
        description: str,
    ) -> None:
        href = event.get("href")
        etag = event.get("etag")
        raw_ics = event.get("raw_ics")

        if not href:
            raise NextcloudCalendarError(
                "Calendar event has no href"
            )

        if not etag:
            raise NextcloudCalendarError(
                "Calendar event has no ETag"
            )

        if not raw_ics:
            raise NextcloudCalendarError(
                "Calendar event has no raw ICS"
            )

        updated_ics = (
            self._replace_ics_description(
                raw_ics,
                description,
            )
        )

        if (
            href.startswith("http://")
            or href.startswith("https://")
        ):
            event_url = href
        else:
            event_url = urljoin(
                self.calendar_url,
                href,
            )

        response = httpx.put(
            event_url,
            auth=(
                self.username,
                self.app_password,
            ),
            headers={
                "Content-Type":
                    "text/calendar; charset=utf-8",
                "If-Match": etag,
            },
            content=updated_ics.encode("utf-8"),
            timeout=15,
        )

        if response.status_code not in {
            200,
            201,
            204,
        }:
            raise NextcloudCalendarError(
                "Could not update calendar event "
                f"(HTTP {response.status_code}): "
                f"{response.text}"
            )

    def update_event_date(
        self,
        event: dict[str, Any],
        new_date: datetime,
    ) -> None:
        href = event.get("href")
        etag = event.get("etag")
        raw_ics = event.get("raw_ics")

        if not href:
            raise NextcloudCalendarError(
                "Calendar event has no href"
            )

        if not etag:
            raise NextcloudCalendarError(
                "Calendar event has no ETag"
            )

        if not raw_ics:
            raise NextcloudCalendarError(
                "Calendar event has no raw ICS"
            )

        updated_ics = self._replace_ics_date(
            raw_ics,
            new_date,
        )

        if (
            href.startswith("http://")
            or href.startswith("https://")
        ):
            event_url = href
        else:
            event_url = urljoin(
                self.calendar_url,
                href,
            )

        response = httpx.put(
            event_url,
            auth=(
                self.username,
                self.app_password,
            ),
            headers={
                "Content-Type":
                    "text/calendar; charset=utf-8",
                "If-Match": etag,
            },
            content=updated_ics.encode("utf-8"),
            timeout=15,
        )

        if response.status_code not in {
            200,
            201,
            204,
        }:
            raise NextcloudCalendarError(
                "Could not move calendar event "
                f"(HTTP {response.status_code}): "
                f"{response.text}"
            )

    def delete_event(
        self,
        event: dict[str, Any],
    ) -> None:
        href = event.get("href")
        etag = event.get("etag")

        if not href:
            raise NextcloudCalendarError(
                "Calendar event has no href"
            )

        if not etag:
            raise NextcloudCalendarError(
                "Calendar event has no ETag"
            )

        if href.startswith("http://") or \
                href.startswith("https://"):
            event_url = href
        else:
            event_url = urljoin(
                self.calendar_url,
                href,
            )

        response = httpx.delete(
            event_url,
            auth=(
                self.username,
                self.app_password,
            ),
            headers={
                "If-Match": etag,
            },
            timeout=15,
        )

        if response.status_code not in {
            200,
            204,
        }:
            raise NextcloudCalendarError(
                "Could not delete calendar event "
                f"(HTTP {response.status_code}): "
                f"{response.text}"
            )

    def create_event(
        self,
        *,
        date: datetime,
        summary: str,
        description: str,
        uid: str | None = None,
    ) -> str:

        if uid is None:
            uid = f"{uuid4()}@pirowflo"

        date_value = date.strftime("%Y%m%d")
        next_day = date.fromordinal(
            date.toordinal() + 1
        ).strftime("%Y%m%d")

        def escape_ics(value: str) -> str:
            return (
                value
                .replace("\\", "\\\\")
                .replace("\r\n", "\n")
                .replace("\r", "\n")
                .replace("\n", "\\n")
                .replace(",", "\\,")
                .replace(";", "\\;")
            )

        now_utc = datetime.utcnow().strftime(
            "%Y%m%dT%H%M%SZ"
        )

        ics = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//PiRowFlo//Training Planner//DE\r\n"
            "CALSCALE:GREGORIAN\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:{uid}\r\n"
            f"DTSTAMP:{now_utc}\r\n"
            f"DTSTART;VALUE=DATE:{date_value}\r\n"
            f"DTEND;VALUE=DATE:{next_day}\r\n"
            f"SUMMARY:{escape_ics(summary)}\r\n"
            f"DESCRIPTION:{escape_ics(description)}\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )

        event_url = (
            self.calendar_url.rstrip("/")
            + "/"
            + uid
            + ".ics"
        )

        response = httpx.put(
            event_url,
            auth=(
                self.username,
                self.app_password,
            ),
            headers={
                "Content-Type":
                    "text/calendar; charset=utf-8",
                # Wichtig: niemals bestehenden Termin überschreiben.
                "If-None-Match": "*",
            },
            content=ics.encode("utf-8"),
            timeout=15,
        )

        if response.status_code not in {
            200,
            201,
            204,
        }:
            raise NextcloudCalendarError(
                "Could not create calendar event "
                f"(HTTP {response.status_code}): "
                f"{response.text}"
            )

        return uid
