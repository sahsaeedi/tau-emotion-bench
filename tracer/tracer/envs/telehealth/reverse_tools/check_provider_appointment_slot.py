# Copyright Sierra
"""Read-only slot check mirroring schedule_appointment / reschedule_appointment validation."""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool


def _slot_busy(
    appointments: Dict[str, Any],
    provider_id: str,
    date: str,
    time: str,
    exclude_appointment_id: Optional[str],
) -> bool:
    for appt_id, appt in appointments.items():
        if exclude_appointment_id and appt_id == exclude_appointment_id:
            continue
        if (
            appt.get("provider_id") == provider_id
            and appt.get("date") == date
            and appt.get("time") == time
            and appt.get("status") in {"scheduled", "pending_approval"}
        ):
            return True
    return False


def _free_times_on_date(
    data: Dict[str, Any],
    provider_id: str,
    date: str,
    day_key: str,
    exclude_appointment_id: Optional[str],
) -> List[str]:
    providers = data.get("providers") or {}
    provider = providers.get(provider_id) or {}
    schedule = provider.get("schedule") or {}
    raw = list(schedule.get(day_key, []) or [])
    appointments = data.get("appointments") or {}
    free: List[str] = []
    for t in raw:
        if not _slot_busy(appointments, provider_id, date, t, exclude_appointment_id):
            free.append(t)
    return free


def _collect_suggestions(
    data: Dict[str, Any],
    provider_id: str,
    start_date: datetime.date,
    exclude_appointment_id: Optional[str],
    max_days: int,
    max_suggestions: int,
) -> List[Dict[str, str]]:
    providers = data.get("providers") or {}
    if provider_id not in providers:
        return []
    provider = providers[provider_id]
    schedule = provider.get("schedule") or {}
    appointments = data.get("appointments") or {}
    out: List[Dict[str, str]] = []
    for offset in range(max_days):
        current = start_date + datetime.timedelta(days=offset)
        day_key = current.strftime("%A").lower()
        slots = list(schedule.get(day_key, []) or [])
        date_s = current.isoformat()
        for t in slots:
            if _slot_busy(appointments, provider_id, date_s, t, exclude_appointment_id):
                continue
            out.append({"date": date_s, "time": t})
            if len(out) >= max_suggestions:
                return out
    return out


class CheckProviderAppointmentSlot(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        provider_id: str,
        date: str,
        time: Optional[str] = None,
        exclude_appointment_id: Optional[str] = None,
        max_suggestions: int = 5,
    ) -> str:
        providers = data.get("providers") or {}
        appointments = data.get("appointments") or {}

        if provider_id not in providers:
            return json.dumps(
                {
                    "error": f"Provider with ID {provider_id} not found.",
                    "bookable": False,
                },
                indent=2,
            )

        try:
            appointment_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return json.dumps(
                {
                    "error": f"Invalid date format: {date}. Use YYYY-MM-DD.",
                    "bookable": False,
                },
                indent=2,
            )

        day_key = appointment_date.strftime("%A").lower()
        provider = providers[provider_id]
        schedule = provider.get("schedule") or {}
        scheduled_times = list(schedule.get(day_key, []) or [])

        payload: Dict[str, Any] = {
            "provider_id": provider_id,
            "date": date,
            "day_of_week": day_key,
            "time_checked": time,
            "exclude_appointment_id": exclude_appointment_id,
            "bookable": None,
            "issues": [],
            "available_times_on_date": scheduled_times,
            "free_times_on_date": _free_times_on_date(
                data, provider_id, date, day_key, exclude_appointment_id
            ),
            "suggested_alternatives": [],
        }

        if day_key not in schedule:
            payload["bookable"] = False
            payload["issues"].append(f"Provider does not work on {day_key.title()}.")
            payload["suggested_alternatives"] = _collect_suggestions(
                data,
                provider_id,
                appointment_date,
                exclude_appointment_id,
                max_days=45,
                max_suggestions=max_suggestions,
            )
            return json.dumps(payload, indent=2)

        if time is None or not str(time).strip():
            payload["bookable"] = None
            payload["issues"].append(
                "No time provided; see free_times_on_date and suggested_alternatives."
            )
            payload["suggested_alternatives"] = _collect_suggestions(
                data,
                provider_id,
                appointment_date,
                exclude_appointment_id,
                max_days=14,
                max_suggestions=max_suggestions,
            )
            return json.dumps(payload, indent=2)

        time_s = str(time).strip()
        if time_s not in scheduled_times:
            payload["bookable"] = False
            payload["issues"].append(
                f"Provider is not available at {time_s} on {day_key.title()}. "
                f"Available times that day: {', '.join(scheduled_times) if scheduled_times else 'None'}"
            )
            payload["suggested_alternatives"] = _collect_suggestions(
                data,
                provider_id,
                appointment_date,
                exclude_appointment_id,
                max_days=45,
                max_suggestions=max_suggestions,
            )
            return json.dumps(payload, indent=2)

        if _slot_busy(appointments, provider_id, date, time_s, exclude_appointment_id):
            payload["bookable"] = False
            payload["issues"].append(
                f"Slot {date} {time_s} is already taken for this provider (scheduled or pending_approval)."
            )
            payload["suggested_alternatives"] = _collect_suggestions(
                data,
                provider_id,
                appointment_date,
                exclude_appointment_id,
                max_days=45,
                max_suggestions=max_suggestions,
            )
            return json.dumps(payload, indent=2)

        payload["bookable"] = True
        payload["issues"] = []
        return json.dumps(payload, indent=2)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "check_provider_appointment_slot",
                "description": (
                    "Read-only check whether a provider can take an appointment on a given date and optional time, "
                    "using the same rules as schedule_appointment and reschedule_appointment (weekly schedule + "
                    "no double-booking with scheduled/pending_approval visits). Returns available and free times for "
                    "that date plus suggested alternative (date, time) pairs if the requested slot is invalid. "
                    "For reschedule flows, pass exclude_appointment_id so the appointment being moved does not block "
                    "its own current slot when validating the new slot."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "provider_id": {
                            "type": "string",
                            "description": "Healthcare provider identifier",
                        },
                        "date": {
                            "type": "string",
                            "description": "Calendar date YYYY-MM-DD",
                        },
                        "time": {
                            "type": "string",
                            "description": "Optional time HH:MM (24h). If omitted, only schedule and free times for the date are returned.",
                        },
                        "exclude_appointment_id": {
                            "type": "string",
                            "description": "Optional appointment_id to ignore in conflict checks (e.g. the visit being rescheduled).",
                        },
                        "max_suggestions": {
                            "type": "integer",
                            "description": "Max number of alternative date/time suggestions to return (default 5).",
                        },
                    },
                    "required": ["provider_id", "date"],
                },
            },
        }
