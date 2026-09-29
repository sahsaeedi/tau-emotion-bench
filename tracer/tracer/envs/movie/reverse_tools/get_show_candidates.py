import json
import random
from typing import Any, Dict, List, Optional, Set

from tracer.envs.tool import Tool

# Max number of shows to return per call (paginated batch)
_MAX_SHOWS = 5

# Number of free seat ids sampled into each summary
_SEAT_SAMPLE = 6

# Call counter: each invoke returns the "next" batch so subsequent calls get different shows
_call_counter = 0


def _list_all_seat_ids(auditorium: Dict[str, Any]) -> Set[str]:
    seat_ids: Set[str] = set()
    for seats in auditorium.get("seat_map", {}).get("rows", {}).values():
        for seat in seats:
            seat_ids.add(seat["seat_id"])
    return seat_ids


def _list_wheelchair_seat_ids(auditorium: Dict[str, Any]) -> Set[str]:
    seat_ids: Set[str] = set()
    for seats in auditorium.get("seat_map", {}).get("rows", {}).values():
        for seat in seats:
            if seat.get("wheelchair_accessible"):
                seat_ids.add(seat["seat_id"])
    return seat_ids


def _booked_seats_for_show(
    data: Dict[str, Any], theater_id: str, show_id: str
) -> Set[str]:
    """Seats already booked for this show (only confirmed bookings count)."""
    seat_ids: Set[str] = set()
    for booking in data.get("bookings", {}).values():
        if (
            booking.get("theater_id") == theater_id
            and booking.get("show_id") == show_id
        ):
            if booking.get("status") == "confirmed":
                for s in booking.get("seats", []):
                    seat_ids.add(s["seat_id"])
    return seat_ids


def _matches_substring(value: Optional[str], needle: str) -> bool:
    if not needle.strip():
        return True
    return needle.strip().lower() in str(value or "").lower()


def _movie_has_genre(movie: Dict[str, Any], needle: str) -> bool:
    return any(_matches_substring(g, needle) for g in movie.get("genres", []))


class GetShowCandidates(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        show_status: Optional[str] = None,
        min_free_seats: Optional[int] = None,
        min_free_wheelchair_seats: Optional[int] = None,
        theater_id: Optional[str] = None,
        movie_id: Optional[str] = None,
        date: Optional[str] = None,
        format: Optional[str] = None,
        language: Optional[str] = None,
        subtitles: Optional[str] = None,
        genre: Optional[str] = None,
        mpaa_rating: Optional[str] = None,
        max_adult_price: Optional[float] = None,
        has_existing_bookings: Optional[bool] = None,
    ) -> str:
        global _call_counter

        theaters: Dict[str, Any] = data.get("theaters") or {}
        movies: Dict[str, Any] = data.get("movies") or {}

        candidates: List[Dict[str, Any]] = []

        for tid, theater in theaters.items():
            if theater_id is not None and tid != theater_id:
                continue
            for show_date, day in (theater.get("dates") or {}).items():
                if date is not None and show_date != date:
                    continue
                for show in day.get("shows", []):
                    if show_status is not None and show.get("status") != show_status:
                        continue
                    if movie_id is not None and show.get("movie_id") != movie_id:
                        continue
                    if format is not None and show.get("format") != format:
                        continue
                    if language is not None and not _matches_substring(
                        show.get("language"), language
                    ):
                        continue
                    if subtitles is not None and not _matches_substring(
                        show.get("subtitles"), subtitles
                    ):
                        continue

                    movie = movies.get(show.get("movie_id")) or {}
                    if genre is not None and not _movie_has_genre(movie, genre):
                        continue
                    if (
                        mpaa_rating is not None
                        and movie.get("mpaa_rating") != mpaa_rating
                    ):
                        continue

                    price_schema = show.get("price_schema") or {}
                    try:
                        adult_price = float(price_schema.get("adult"))
                    except (TypeError, ValueError):
                        adult_price = None
                    if max_adult_price is not None:
                        try:
                            if adult_price is None or adult_price > float(
                                max_adult_price
                            ):
                                continue
                        except (TypeError, ValueError):
                            pass

                    auditorium = (theater.get("auditoriums") or {}).get(
                        show.get("auditorium_id")
                    )
                    if auditorium is None:
                        continue
                    all_ids = _list_all_seat_ids(auditorium)
                    wheelchair_ids = _list_wheelchair_seat_ids(auditorium)
                    booked_ids = _booked_seats_for_show(data, tid, show.get("show_id"))
                    free_ids = all_ids - booked_ids
                    free_regular = sorted(free_ids - wheelchair_ids)
                    free_wheelchair = sorted(free_ids & wheelchair_ids)

                    if min_free_seats is not None:
                        try:
                            if len(free_regular) < int(min_free_seats):
                                continue
                        except (TypeError, ValueError):
                            pass
                    if min_free_wheelchair_seats is not None:
                        try:
                            if len(free_wheelchair) < int(min_free_wheelchair_seats):
                                continue
                        except (TypeError, ValueError):
                            pass
                    if has_existing_bookings is not None and bool(booked_ids) != bool(
                        has_existing_bookings
                    ):
                        continue

                    candidates.append(
                        {
                            "show_id": show.get("show_id"),
                            "theater_id": tid,
                            "theater_name": theater.get("name", ""),
                            "date": show_date,
                            "start_time_local": show.get("start_time_local"),
                            "status": show.get("status"),
                            "movie_id": show.get("movie_id"),
                            "movie_title": movie.get("title", ""),
                            "genres": movie.get("genres", []),
                            "mpaa_rating": movie.get("mpaa_rating"),
                            "runtime_minutes": movie.get("runtime_minutes"),
                            "format": show.get("format"),
                            "language": show.get("language"),
                            "subtitles": show.get("subtitles"),
                            "auditorium_id": show.get("auditorium_id"),
                            "price_adult": adult_price,
                            "price_child": price_schema.get("child"),
                            "price_senior": price_schema.get("senior"),
                            "free_regular_seat_count": len(free_regular),
                            "free_wheelchair_seat_count": len(free_wheelchair),
                            "free_regular_seat_sample": free_regular[:_SEAT_SAMPLE],
                            "booked_seat_count": len(booked_ids),
                        }
                    )

        random.shuffle(candidates)
        total = len(candidates)
        if total == 0:
            return json.dumps(
                {"total_matching": 0, "returned_count": 0, "shows": []}, indent=2
            )

        offset = (_call_counter * _MAX_SHOWS) % total
        _call_counter += 1
        doubled = candidates + candidates
        batch = doubled[offset : offset + _MAX_SHOWS]

        payload = {
            "total_matching": total,
            "returned_count": len(batch),
            "shows": batch,
        }
        return json.dumps(payload, indent=2)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_show_candidates",
                "description": (
                    "Read-only roster of shows across ALL theaters and dates, matching zero or more filters, for "
                    "finding a real show that already satisfies a scenario precondition (e.g. a scheduled show "
                    "that still has three free non-accessible seats, so a new booking can actually be made). "
                    "list_shows requires a theater_id AND a date up front, so without this tool a bookable show "
                    "can only be found by guessing dates; this tool searches every theater and date at once and "
                    "reports the theater_id, date and free seat ids needed to drive price_preview and "
                    "create_booking. All filter parameters are optional; when a filter is omitted, no constraint "
                    "is applied for that field. Filters combine with AND semantics — a show must satisfy every "
                    "filter provided to match. Returns concise summaries, not full records — use get_show_details, "
                    "get_seat_availability and get_movie_details for full details once a candidate show is chosen. "
                    "The list is randomized; each call returns the next batch "
                    f"(up to {_MAX_SHOWS} shows, different from previous calls)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "show_status": {
                            "type": "string",
                            "enum": ["scheduled", "canceled", "completed"],
                            "description": (
                                "If set, only shows in this status. Only 'scheduled' shows can be priced with "
                                "price_preview or booked with create_booking, so use 'scheduled' to ground any "
                                "task that must succeed. Note: every show in the current dataset is 'scheduled', "
                                "so filtering on 'canceled' or 'completed' returns nothing."
                            ),
                        },
                        "min_free_seats": {
                            "type": "integer",
                            "description": (
                                "If set, only shows with at least this many free NON-wheelchair-accessible seats. "
                                "create_booking fails if any requested seat is already taken, and policy forbids "
                                "assigning accessible seats unless explicitly requested, so set this to the number "
                                "of tickets the story wants to book."
                            ),
                        },
                        "min_free_wheelchair_seats": {
                            "type": "integer",
                            "description": (
                                "If set, only shows with at least this many free wheelchair-accessible seats. Use "
                                "it to ground a story where the customer explicitly asks for accessible seating, "
                                "which is the only case in which such seats may be assigned."
                            ),
                        },
                        "theater_id": {
                            "type": "string",
                            "description": "If set, only shows at this theater.",
                        },
                        "movie_id": {
                            "type": "string",
                            "description": "If set, only shows of this movie.",
                        },
                        "date": {
                            "type": "string",
                            "description": (
                                "If set, only shows on this date, in the format YY-MM-DD (e.g. 25-09-15). Shows "
                                "are not spread evenly over the calendar, so prefer discovering a real date from "
                                "an unfiltered call rather than guessing one."
                            ),
                        },
                        "format": {
                            "type": "string",
                            "enum": ["2D", "3D", "IMAX", "Dolby"],
                            "description": (
                                "If set, only shows in this presentation format. Useful for grounding a customer "
                                "preference such as 'the IMAX screening'."
                            ),
                        },
                        "language": {
                            "type": "string",
                            "description": (
                                "If set, only shows whose audio language contains this substring "
                                "(case-insensitive), e.g. 'Spanish' or 'French'."
                            ),
                        },
                        "subtitles": {
                            "type": "string",
                            "description": (
                                "If set, only shows whose subtitle track contains this substring "
                                "(case-insensitive). Useful for grounding an accessibility or language request."
                            ),
                        },
                        "genre": {
                            "type": "string",
                            "description": (
                                "If set, only shows whose movie has a genre containing this substring "
                                "(case-insensitive), e.g. 'Horror'. Grounds a vague customer ask like 'something "
                                "scary tonight'."
                            ),
                        },
                        "mpaa_rating": {
                            "type": "string",
                            "enum": ["G", "PG", "PG-13", "R", "NR"],
                            "description": (
                                "If set, only shows whose movie carries this MPAA rating. Useful for grounding a "
                                "family booking that includes child tickets."
                            ),
                        },
                        "max_adult_price": {
                            "type": "number",
                            "description": (
                                "If set, only shows whose adult ticket price is at most this amount. Prices come "
                                "from the show's price_schema and must never be invented, so use this to ground a "
                                "budget-driven story in real numbers."
                            ),
                        },
                        "has_existing_bookings": {
                            "type": "boolean",
                            "description": (
                                "If set, selects shows that already have (True) or do not have (False) at least "
                                "one confirmed booking. True grounds a story about a partially filled screening; "
                                "False grounds a completely empty auditorium."
                            ),
                        },
                    },
                    "required": [],
                },
            },
        }
