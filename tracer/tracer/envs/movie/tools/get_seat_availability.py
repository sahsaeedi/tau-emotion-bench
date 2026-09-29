import json
from typing import Any, Dict, Optional, Set, Tuple

from tracer.envs.tool import Tool


def _find_show(
    data: Dict[str, Any], theater_id: str, show_id: str
) -> Tuple[Optional[dict], Optional[str]]:
    """Find a show by ID in a given theater, searching across all dates.

    Returns (show, error) - show is None if error is set.
    """
    theater = data["theaters"].get(theater_id)
    if theater is None:
        return None, f"Error: Theater {theater_id} not found"
    for day in theater["dates"].values():
        for show in day["shows"]:
            if show["show_id"] == show_id:
                return show, None
    return None, f"Error: Show {show_id} not found at theater {theater_id}"


def _list_all_seat_ids(auditorium: Dict[str, Any]) -> Set[str]:
    seat_ids: Set[str] = set()
    for seats in auditorium["seat_map"]["rows"].values():
        for seat in seats:
            seat_ids.add(seat["seat_id"])
    return seat_ids


def _booked_seats_for_show(
    data: Dict[str, Any], theater_id: str, show_id: str
) -> Set[str]:
    """Seats already booked for this show (only confirmed bookings count)."""
    seat_ids: Set[str] = set()
    for booking in data["bookings"].values():
        if booking["theater_id"] == theater_id and booking["show_id"] == show_id:
            if booking["status"] == "confirmed":
                for s in booking["seats"]:
                    seat_ids.add(s["seat_id"])
    return seat_ids


class GetSeatAvailabilityTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], theater_id: str, show_id: str) -> str:
        theater = data["theaters"].get(theater_id)
        if theater is None:
            return f"Error: Theater {theater_id} not found"
        show, err = _find_show(data, theater_id, show_id)
        if err:
            return err
        auditorium = theater["auditoriums"].get(show["auditorium_id"])
        if auditorium is None:
            return f"Error: Auditorium {show['auditorium_id']} not found at theater {theater_id}"

        all_seats = _list_all_seat_ids(auditorium)
        booked = _booked_seats_for_show(data, theater_id, show_id)
        available = sorted(all_seats - booked)
        booked_list = sorted(booked)
        return json.dumps({"available": available, "booked": booked_list})

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_seat_availability",
                "description": "Get seat availability for a show. Returns an object with keys: available, booked.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "theater_id": {
                            "type": "string",
                            "description": "The theater id.",
                        },
                        "show_id": {"type": "string", "description": "The show id."},
                    },
                    "required": ["theater_id", "show_id"],
                },
            },
        }
