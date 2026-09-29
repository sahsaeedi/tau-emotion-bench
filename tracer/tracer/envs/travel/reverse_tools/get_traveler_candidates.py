import json
import random
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool

# Max number of travelers to return per call (paginated batch)
_MAX_TRAVELERS = 5

# Call counter: each invoke returns the "next" batch so subsequent calls get different travelers
_call_counter = 0

# Insurance labels that _calc_total_price actually prices (+$50/+$100 per traveler).
# Every other label is priced at $0.00 by the write tools.
_PRICED_INSURANCE = ("standard", "premium")


def _bookings(traveler: Dict[str, Any]) -> List[Dict[str, Any]]:
    return traveler.get("bookings") or []


def _has_booking_status(traveler: Dict[str, Any], status: str) -> bool:
    return any(b.get("status") == status for b in _bookings(traveler))


def _departure(
    packages: Dict[str, Any], booking: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    package = packages.get(booking.get("package_id"))
    if package is None:
        return None
    return (package.get("departures") or {}).get(booking.get("departure_date"))


def _can_update_add_ons(traveler: Dict[str, Any], packages: Dict[str, Any]) -> bool:
    """update_booking_add_ons needs a saved payment method and a still-available departure."""
    if not traveler.get("payment_methods"):
        return False
    for booking in _bookings(traveler):
        dep = _departure(packages, booking)
        if dep is not None and dep.get("status") == "available":
            return True
    return False


def _can_change_departure_date(
    traveler: Dict[str, Any], packages: Dict[str, Any]
) -> bool:
    """update_booking_departure_date needs a saved payment method and an alternative
    departure on the same package that is 'available' with slots for every traveler."""
    if not traveler.get("payment_methods"):
        return False
    for booking in _bookings(traveler):
        package = packages.get(booking.get("package_id"))
        if package is None:
            continue
        needed = len(booking.get("travelers") or [])
        for date, dep in (package.get("departures") or {}).items():
            if date == booking.get("departure_date"):
                continue
            if (
                dep.get("status") == "available"
                and dep.get("available_slots", 0) >= needed
            ):
                return True
    return False


def _has_unavailable_departure(
    traveler: Dict[str, Any], packages: Dict[str, Any]
) -> bool:
    for booking in _bookings(traveler):
        package = packages.get(booking.get("package_id"))
        if package is None:
            continue
        if any(
            d.get("status") != "available"
            for d in (package.get("departures") or {}).values()
        ):
            return True
    return False


def _has_insurance_pricing(traveler: Dict[str, Any], kind: str) -> bool:
    for booking in _bookings(traveler):
        label = booking.get("insurance")
        if not label:
            continue
        priced = str(label).strip().lower() in _PRICED_INSURANCE
        if (kind == "priced") == priced:
            return True
    return False


def _has_payment_method_source(traveler: Dict[str, Any], source: str) -> bool:
    return any(
        pm.get("source") == source
        for pm in (traveler.get("payment_methods") or {}).values()
    )


def _has_rooming_room_type(traveler: Dict[str, Any], room_type: str) -> bool:
    return any(
        (b.get("rooming") or {}).get("room_type") == room_type
        for b in _bookings(traveler)
    )


def _max_booking_party_size(traveler: Dict[str, Any]) -> int:
    return max((len(b.get("travelers") or []) for b in _bookings(traveler)), default=0)


def _has_free_agent_slot(traveler: Dict[str, Any], agents: Dict[str, Any]) -> bool:
    """schedule_agent_meeting fails unless the agent still has an unreserved slot."""
    for booking in _bookings(traveler):
        agent = agents.get(booking.get("agent_id"))
        if agent is None:
            continue
        if any(day.get("slots") for day in (agent.get("availability") or {}).values()):
            return True
    return False


def _travels_to_country(
    traveler: Dict[str, Any], packages: Dict[str, Any], country: str
) -> bool:
    needle = country.strip().lower()
    for booking in _bookings(traveler):
        package = packages.get(booking.get("package_id"))
        if package is None:
            continue
        for dest in package.get("destinations") or []:
            if str(dest.get("country", "")).strip().lower() == needle:
                return True
    return False


class GetTravelerCandidates(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        has_booking: Optional[bool] = None,
        min_bookings: Optional[int] = None,
        booking_status: Optional[str] = None,
        has_saved_payment_method: Optional[bool] = None,
        payment_method_source: Optional[str] = None,
        can_update_add_ons: Optional[bool] = None,
        can_change_departure_date: Optional[bool] = None,
        package_has_unavailable_departure: Optional[bool] = None,
        insurance_pricing: Optional[str] = None,
        min_travelers_in_booking: Optional[int] = None,
        rooming_room_type: Optional[str] = None,
        min_saved_companions: Optional[int] = None,
        booking_agent_has_free_slot: Optional[bool] = None,
        destination_country: Optional[str] = None,
    ) -> str:
        global _call_counter

        travelers: Dict[str, Any] = data.get("travelers") or {}
        packages: Dict[str, Any] = data.get("packages") or {}
        agents: Dict[str, Any] = data.get("agents") or {}

        candidates: List[Dict[str, Any]] = []

        for traveler_id, traveler in travelers.items():
            bookings = _bookings(traveler)

            if has_booking is not None and bool(has_booking) != bool(bookings):
                continue
            if min_bookings is not None:
                try:
                    if len(bookings) < int(min_bookings):
                        continue
                except (TypeError, ValueError):
                    pass
            if booking_status is not None and not _has_booking_status(
                traveler, booking_status
            ):
                continue

            if has_saved_payment_method is not None:
                if bool(has_saved_payment_method) != bool(
                    traveler.get("payment_methods")
                ):
                    continue
            if payment_method_source is not None and not _has_payment_method_source(
                traveler, payment_method_source
            ):
                continue

            if can_update_add_ons is not None:
                if bool(can_update_add_ons) != _can_update_add_ons(traveler, packages):
                    continue
            if can_change_departure_date is not None:
                if bool(can_change_departure_date) != _can_change_departure_date(
                    traveler, packages
                ):
                    continue
            if package_has_unavailable_departure is not None:
                if bool(
                    package_has_unavailable_departure
                ) != _has_unavailable_departure(traveler, packages):
                    continue

            if insurance_pricing is not None and not _has_insurance_pricing(
                traveler, str(insurance_pricing).strip().lower()
            ):
                continue

            if min_travelers_in_booking is not None:
                try:
                    if _max_booking_party_size(traveler) < int(
                        min_travelers_in_booking
                    ):
                        continue
                except (TypeError, ValueError):
                    pass
            if rooming_room_type is not None and not _has_rooming_room_type(
                traveler, rooming_room_type
            ):
                continue

            if min_saved_companions is not None:
                try:
                    if len(traveler.get("saved_companions") or []) < int(
                        min_saved_companions
                    ):
                        continue
                except (TypeError, ValueError):
                    pass

            if booking_agent_has_free_slot is not None:
                if bool(booking_agent_has_free_slot) != _has_free_agent_slot(
                    traveler, agents
                ):
                    continue

            if destination_country is not None and not _travels_to_country(
                traveler, packages, str(destination_country)
            ):
                continue

            name = traveler.get("name", {})
            display_name = (
                " ".join(
                    p for p in [name.get("first_name"), name.get("last_name")] if p
                ).strip()
                or "Unknown"
            )
            pair: Dict[str, Any] = {}
            want_pair = min_bookings is not None and int(min_bookings) >= 2
            if len(bookings) >= 2:
                live = sorted(
                    (b for b in bookings if b.get("status") != "cancelled"),
                    key=lambda b: b.get("booking_id", ""),
                )
                modify = next(
                    (
                        b
                        for b in live
                        if (_departure(packages, b) or {}).get("status") == "available"
                    ),
                    None,
                )
                cancel = next(
                    (b for b in live if modify is None or b is not modify), None
                )
                if (modify is None or cancel is None) and want_pair:
                    continue
                cpkg = (
                    {}
                    if (modify is None or cancel is None)
                    else packages.get(cancel.get("package_id")) or {}
                )
                pair = (
                    {}
                    if (modify is None or cancel is None)
                    else {
                        "modify_target": {
                            "booking_id": modify.get("booking_id"),
                            "departure_date": modify.get("departure_date"),
                            "departure_status": "available",
                            "why": "departure still available -> add-on / date changes accepted",
                        },
                        "cancel_target": {
                            "booking_id": cancel.get("booking_id"),
                            "status": cancel.get("status"),
                            "cancellation_policy": (cpkg.get("policies") or {}).get(
                                "cancellation_policy"
                            ),
                            "why_cancellable": "another non-cancelled booking of this traveler; check the attached policy text",
                        },
                    }
                )
            candidates.append(
                {
                    **pair,
                    "traveler_id": traveler_id,
                    "name": display_name,
                    "email": traveler.get("contact", {}).get("email", ""),
                    "num_bookings": len(bookings),
                    "booking_ids": [b.get("booking_id") for b in bookings],
                    "num_payment_methods": len(traveler.get("payment_methods") or {}),
                    "num_saved_companions": len(traveler.get("saved_companions") or []),
                    "memberships": traveler.get("memberships") or [],
                }
            )

        random.shuffle(candidates)
        total = len(candidates)
        if total == 0:
            return json.dumps(
                {"total_matching": 0, "returned_count": 0, "travelers": []}, indent=2
            )

        offset = (_call_counter * _MAX_TRAVELERS) % total
        _call_counter += 1
        doubled = candidates + candidates
        batch = doubled[offset : offset + _MAX_TRAVELERS]

        payload = {
            "total_matching": total,
            "returned_count": len(batch),
            "travelers": batch,
        }
        return json.dumps(payload, indent=2)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_traveler_candidates",
                "description": (
                    "Read-only roster of travelers matching zero or more filters, for finding a real traveler "
                    "whose data already satisfies a scenario precondition (e.g. a traveler whose booking can "
                    "actually be moved to another departure date, or one with no saved payment method at all). "
                    "All filter parameters are optional; when a filter is omitted, no constraint is applied for "
                    "that field. Filters combine with AND semantics — a traveler must satisfy every filter "
                    "provided to match. Returns concise summaries (traveler_id, name, email, booking_ids, and "
                    "counts of payment methods/companions), not full records — use get_traveler_details, "
                    "get_booking_details, get_package_details, etc. for full details once a candidate "
                    "traveler_id is chosen. The list is randomized; each call returns the next batch "
                    f"(up to {_MAX_TRAVELERS} travelers, different from previous calls)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "has_booking": {
                            "type": "boolean",
                            "description": (
                                "If set, only travelers that do (True) or do not (False) have at least one "
                                "booking on file. Use False to find a traveler with an empty history for a "
                                "fresh book_package scenario; use True for any modify/cancel scenario, which "
                                "needs an existing booking_id."
                            ),
                        },
                        "min_bookings": {
                            "type": "integer",
                            "description": (
                                "If set, only travelers with at least this many bookings. Use 2 to ground a "
                                "scenario where the user must disambiguate between trips ('the one to Japan, "
                                "not the other one'); such travelers are rare in the data."
                            ),
                        },
                        "booking_status": {
                            "type": "string",
                            "enum": ["confirmed", "pending", "cancelled"],
                            "description": (
                                "If set, only travelers with at least one booking in this status. Use "
                                "'confirmed' to ground a cancel_booking or modification scenario; "
                                "'cancelled' to ground a scenario about an already-cancelled trip (e.g. a "
                                "refund question) rather than one that can be cancelled again."
                            ),
                        },
                        "has_saved_payment_method": {
                            "type": "boolean",
                            "description": (
                                "If set, only travelers that do (True) or do not (False) have at least one "
                                "saved payment method. Every price-changing write tool "
                                "(book_package, update_booking_add_ons, update_booking_departure_date) hard-fails "
                                "with 'Payment method not found for traveler' unless the id is already saved on "
                                "the profile, so use True for any of those scenarios and False to ground a "
                                "scenario where the change legitimately cannot be paid for."
                            ),
                        },
                        "payment_method_source": {
                            "type": "string",
                            "enum": [
                                "credit_card",
                                "bank_transfer",
                                "paypal",
                                "mobile_wallet",
                                "wallet",
                            ],
                            "description": (
                                "If set, only travelers with at least one saved payment method of this source. "
                                "Refunds are recorded back to the same saved method, so this grounds a story "
                                "where the user refers to how they paid ('the card', 'my PayPal'). Most "
                                "travelers only have credit_card."
                            ),
                        },
                        "can_update_add_ons": {
                            "type": "boolean",
                            "description": (
                                "If set, only travelers for whom update_booking_add_ons would (True) or would "
                                "not (False) succeed on at least one booking. The tool re-validates the "
                                "booking's OWN departure and errors out if its status is no longer 'available', "
                                "so a booking on a departure that has since gone sold_out or limited cannot "
                                "have its add-ons replaced even though nothing about the slots changed. "
                                "Also requires a saved payment method for the price delta."
                            ),
                        },
                        "can_change_departure_date": {
                            "type": "boolean",
                            "description": (
                                "If set, only travelers for whom update_booking_departure_date would (True) or "
                                "would not (False) succeed on at least one booking. Per the policy you can only "
                                "move to a departure whose status is 'available' and that has enough slots for "
                                "every traveler on the booking, so True means the package genuinely offers an "
                                "alternative date with room; use False to ground a scenario where the agent must "
                                "tell the user no other date works."
                            ),
                        },
                        "package_has_unavailable_departure": {
                            "type": "boolean",
                            "description": (
                                "If set, only travelers whose booked package does (True) or does not (False) "
                                "list at least one departure whose status is not 'available' (i.e. 'sold_out' or "
                                "'limited'). Grounds a scenario where the user asks for a specific date that "
                                "cannot be booked. Note 'limited' is NOT bookable either — the write tools "
                                "require status exactly 'available'."
                            ),
                        },
                        "insurance_pricing": {
                            "type": "string",
                            "enum": ["priced", "unpriced"],
                            "description": (
                                "If set, only travelers with at least one booking whose insurance label is "
                                "'priced' (lowercases to exactly 'standard' or 'premium', so it adds $50 or "
                                "$100 per traveler when the total is recomputed) or 'unpriced' (any other "
                                "label, e.g. 'Comprehensive Plan A' or 'Basic', which adds $0.00). Most "
                                "bookings in the data carry unpriced labels, so use 'priced' when the story "
                                "needs the insurance to visibly affect a repriced total after a date or "
                                "add-on change."
                            ),
                        },
                        "min_travelers_in_booking": {
                            "type": "integer",
                            "description": (
                                "If set, only travelers with at least one booking covering this many people. "
                                "The party size is fixed (update_booking_travelers rejects a different count) "
                                "and it is also the number of slots a new departure must have free, so use 3 "
                                "for a group scenario or 1 for a solo traveler."
                            ),
                        },
                        "rooming_room_type": {
                            "type": "string",
                            "enum": [
                                "single",
                                "double",
                                "twin",
                                "suite",
                                "family_suite",
                            ],
                            "description": (
                                "If set, only travelers with at least one booking currently in this room type. "
                                "Grounds an update_booking_rooming scenario in the arrangement the user is "
                                "actually asking to change away from."
                            ),
                        },
                        "min_saved_companions": {
                            "type": "integer",
                            "description": (
                                "If set, only travelers with at least this many saved companions. Companions "
                                "carry real first_name/last_name/dob values, which is what "
                                "update_booking_travelers needs to write, so use 1 to avoid inventing a "
                                "co-traveler's details."
                            ),
                        },
                        "booking_agent_has_free_slot": {
                            "type": "boolean",
                            "description": (
                                "If set, only travelers whose booking's managing agent does (True) or does not "
                                "(False) still have an unreserved slot in their availability. "
                                "schedule_agent_meeting errors unless the date and the exact HH:MM-HH:MM "
                                "time_range are both present in that agent's availability, so use True for any "
                                "meeting-scheduling scenario."
                            ),
                        },
                        "destination_country": {
                            "type": "string",
                            "description": (
                                "If set, only travelers with at least one booking on a package that visits this "
                                "country (case-insensitive exact match on the destination country). Grounds a "
                                "story where the user refers to the trip by where it goes ('my Japan trip')."
                            ),
                        },
                    },
                    "required": [],
                },
            },
        }
