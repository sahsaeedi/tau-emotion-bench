import json
import random
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool

# Conjunctive finder. The single-purpose lists (get_user_ids_with_n_reservations,
# get_users_with_cancelled_flights, get_users_with_delayed_flights) cannot be
# intersected by the generator; a trace that needs one user with, say, a credit card
# AND an upcoming economy reservation with 2+ passengers AND a cancelled flight
# otherwise costs it many steps of paging. User-level filters apply to the user;
# reservation-level filters must all hold on ONE reservation of that user, which is
# returned in matching_reservations.

_MAX_USERS = 5
_call_counter = 0
TODAY = "2024-05-15"  # the policy clock (get_todays_date)


def _flight_statuses(reservation: Dict[str, Any], flights: Dict[str, Any]) -> List[str]:
    out = []
    for leg in reservation.get("flights", []):
        info = (
            (flights.get(leg.get("flight_number")) or {})
            .get("dates", {})
            .get(leg.get("date"), {})
        )
        out.append(info.get("status", "unknown"))
    return out


def _reservation_state(reservation: Dict[str, Any], flights: Dict[str, Any]) -> str:
    """upcoming = every leg still 'available' (nothing flown, nothing cancelled);
    cancelled_flight / delayed_flight = at least one leg in that status;
    flown = at least one leg landed / flying."""
    statuses = _flight_statuses(reservation, flights)
    if "cancelled" in statuses:
        return "cancelled_flight"
    if "delayed" in statuses:
        return "delayed_flight"
    if any(s in ("landed", "flying") for s in statuses):
        return "flown"
    if statuses and all(s in ("available", "on time") for s in statuses):
        return "upcoming"
    return "mixed"


def _policy_cancellable(
    reservation: Dict[str, Any], flights: Dict[str, Any]
) -> Optional[str]:
    """wiki.md: cancellable iff booked within 24h, or an airline-cancelled leg, or business
    cabin, or insurance -- and never once a leg has flown. Returns the reason, or None.
    cancel_reservation (the tool) does not enforce this; the checker does."""
    statuses = _flight_statuses(reservation, flights)
    if any(s in ("landed", "flying") for s in statuses):
        return None
    if "cancelled" in statuses:
        return "a leg was cancelled by the airline"
    if reservation.get("cabin") == "business":
        return "business cabin"
    if reservation.get("insurance") == "yes":
        return "travel insurance purchased"
    created = str(reservation.get("created_at", ""))[:19]
    if created >= "2024-05-14T15:00:00":  # within 24h of the 2024-05-15 15:00 clock
        return "booked within the last 24 hours"
    return None


def _split_targets(
    res_ids: List[str],
    matching: List[Dict[str, Any]],
    reservations: Dict[str, Any],
    flights: Dict[str, Any],
) -> Dict[str, Any]:
    """Two DIFFERENT reservations of one user: the one that satisfies the caller's
    reservation filters goes to the write with the most preconditions (modify_target);
    any OTHER reservation the policy lets the user cancel is cancel_target."""
    modify = matching[0] if matching else None
    cancel = None
    for rid in sorted(res_ids):
        if modify and rid == modify["reservation_id"]:
            continue
        why = _policy_cancellable(reservations[rid], flights)
        if why:
            r = reservations[rid]
            cancel = {
                "reservation_id": rid,
                "state": _reservation_state(r, flights),
                "cabin": r.get("cabin"),
                "insurance": r.get("insurance"),
                "why_cancellable": why,
            }
            break
    out: Dict[str, Any] = {}
    if modify:
        r = reservations[modify["reservation_id"]]
        out["modify_target"] = {
            "reservation_id": modify["reservation_id"],
            "state": modify["state"],
            "cabin": r.get("cabin"),
            "modifiable_flights": modify["state"] == "upcoming"
            and r.get("cabin") != "basic_economy",
            "why": "matches your reservation filters",
        }
    out["cancel_target"] = cancel
    return out


class GetUserCandidates(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        min_reservations: Optional[int] = None,
        has_credit_card: Optional[bool] = None,
        has_gift_card: Optional[bool] = None,
        has_certificate: Optional[bool] = None,
        membership: Optional[str] = None,
        min_saved_passengers: Optional[int] = None,
        reservation_cabin: Optional[str] = None,
        reservation_insurance: Optional[str] = None,
        reservation_flight_type: Optional[str] = None,
        min_passengers: Optional[int] = None,
        reservation_state: Optional[str] = None,
        min_baggages: Optional[int] = None,
    ) -> str:
        global _call_counter
        users = data["users"]
        reservations = data["reservations"]
        flights = data["flights"]

        res_filters_given = any(
            x is not None
            for x in (
                reservation_cabin,
                reservation_insurance,
                reservation_flight_type,
                min_passengers,
                reservation_state,
                min_baggages,
            )
        )

        candidates = []
        for uid, u in users.items():
            methods = u.get("payment_methods", {})
            sources = {m.get("source") for m in methods.values()}
            res_ids = [r for r in u.get("reservations", []) if r in reservations]

            if min_reservations is not None and len(res_ids) < int(min_reservations):
                continue
            if has_credit_card is not None and ("credit_card" in sources) != bool(
                has_credit_card
            ):
                continue
            if has_gift_card is not None and ("gift_card" in sources) != bool(
                has_gift_card
            ):
                continue
            if has_certificate is not None and ("certificate" in sources) != bool(
                has_certificate
            ):
                continue
            if membership is not None and u.get("membership") != membership:
                continue
            if min_saved_passengers is not None and len(
                u.get("saved_passengers", [])
            ) < int(min_saved_passengers):
                continue

            matching = []
            for rid in res_ids:
                r = reservations[rid]
                state = _reservation_state(r, flights)
                if (
                    reservation_cabin is not None
                    and r.get("cabin") != reservation_cabin
                ):
                    continue
                if (
                    reservation_insurance is not None
                    and r.get("insurance") != reservation_insurance
                ):
                    continue
                if (
                    reservation_flight_type is not None
                    and r.get("flight_type") != reservation_flight_type
                ):
                    continue
                if min_passengers is not None and len(r.get("passengers", [])) < int(
                    min_passengers
                ):
                    continue
                if reservation_state is not None and state != reservation_state:
                    continue
                if min_baggages is not None and int(r.get("total_baggages", 0)) < int(
                    min_baggages
                ):
                    continue
                matching.append(
                    {
                        "reservation_id": rid,
                        "state": state,
                        "cabin": r.get("cabin"),
                        "insurance": r.get("insurance"),
                        "flight_type": r.get("flight_type"),
                        "origin": r.get("origin"),
                        "destination": r.get("destination"),
                        "num_passengers": len(r.get("passengers", [])),
                        "total_baggages": r.get("total_baggages"),
                        "flights": [
                            {
                                "flight_number": f.get("flight_number"),
                                "date": f.get("date"),
                                "status": s,
                            }
                            for f, s in zip(
                                r.get("flights", []), _flight_statuses(r, flights)
                            )
                        ],
                    }
                )
            if res_filters_given and not matching:
                continue

            pair: Dict[str, Any] = {}
            want_pair = min_reservations is not None and int(min_reservations) >= 2
            if (
                len(res_ids) >= 2
            ):  # always offered when a pair exists; required only if asked
                pair = _split_targets(
                    res_ids,
                    matching
                    if res_filters_given
                    else [
                        {
                            "reservation_id": rid,
                            "state": _reservation_state(reservations[rid], flights),
                        }
                        for rid in sorted(res_ids)
                    ],
                    reservations,
                    flights,
                )
                if pair.get("cancel_target") is None:
                    if want_pair:
                        continue  # two reservations but nothing the policy lets them cancel
                    pair = {}

            candidates.append(
                {
                    **pair,
                    "user_id": uid,
                    "email": u.get("email", ""),
                    "membership": u.get("membership"),
                    "payment_methods": [
                        {
                            "id": mid,
                            "source": m.get("source"),
                            **({"amount": m["amount"]} if "amount" in m else {}),
                        }
                        for mid, m in methods.items()
                    ],
                    "num_saved_passengers": len(u.get("saved_passengers", [])),
                    "num_reservations": len(res_ids),
                    "matching_reservations": matching
                    if res_filters_given
                    else [
                        {
                            "reservation_id": rid,
                            "state": _reservation_state(reservations[rid], flights),
                        }
                        for rid in res_ids
                    ],
                }
            )

        random.shuffle(candidates)
        total = len(candidates)
        if total == 0:
            return json.dumps(
                {"total_matching": 0, "returned_count": 0, "users": []}, indent=2
            )
        offset = (_call_counter * _MAX_USERS) % total
        _call_counter += 1
        doubled = candidates + candidates
        batch = doubled[offset : offset + _MAX_USERS]
        return json.dumps(
            {"total_matching": total, "returned_count": len(batch), "users": batch},
            indent=2,
        )

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_user_candidates",
                "description": (
                    "Read-only finder: users matching ALL given filters at once. User-level filters "
                    "(reservations count, payment method kinds, membership, saved passengers) apply to "
                    "the user; reservation-level filters (cabin, insurance, flight type, passengers, "
                    "state, baggages) must all hold on ONE reservation of that user, returned in "
                    "matching_reservations with per-leg flight status. Returns up to 5 randomized users "
                    "per call with total_matching; call again for another batch. Use this instead of "
                    "intersecting get_user_ids_with_n_reservations / get_users_with_cancelled_flights / "
                    "get_users_with_delayed_flights by hand."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "min_reservations": {
                            "type": "integer",
                            "description": "User holds at least this many reservations. With 2 or more, each row also carries modify_target (the reservation matching your other filters -- use it for the update/read steps) and cancel_target (a DIFFERENT reservation that the policy allows cancelling, with why_cancellable) -- copy those two ids into the two writes.",
                        },
                        "has_credit_card": {
                            "type": "boolean",
                            "description": "User has a credit_card payment method (needed to pay any fare or baggage difference).",
                        },
                        "has_gift_card": {
                            "type": "boolean",
                            "description": "User has a gift_card payment method.",
                        },
                        "has_certificate": {
                            "type": "boolean",
                            "description": "User has a certificate payment method.",
                        },
                        "membership": {
                            "type": "string",
                            "enum": ["regular", "silver", "gold"],
                            "description": "Membership tier (drives free-baggage allowances).",
                        },
                        "min_saved_passengers": {
                            "type": "integer",
                            "description": "User has at least this many saved passengers.",
                        },
                        "reservation_cabin": {
                            "type": "string",
                            "enum": ["basic_economy", "economy", "business"],
                            "description": "A reservation in this cabin (basic_economy cannot change flights).",
                        },
                        "reservation_insurance": {
                            "type": "string",
                            "enum": ["yes", "no"],
                            "description": "That reservation has / lacks travel insurance (affects cancellation refunds).",
                        },
                        "reservation_flight_type": {
                            "type": "string",
                            "enum": ["one_way", "round_trip"],
                            "description": "That reservation's trip type.",
                        },
                        "min_passengers": {
                            "type": "integer",
                            "description": "That reservation has at least this many passengers.",
                        },
                        "reservation_state": {
                            "type": "string",
                            "enum": [
                                "upcoming",
                                "cancelled_flight",
                                "delayed_flight",
                                "flown",
                            ],
                            "description": (
                                "upcoming = every leg still available (modifiable / cancellable); "
                                "cancelled_flight = a leg was cancelled by the airline (compensation / refund); "
                                "delayed_flight = a leg is delayed; flown = a leg already landed."
                            ),
                        },
                        "min_baggages": {
                            "type": "integer",
                            "description": "That reservation has at least this many checked bags.",
                        },
                    },
                    "required": [],
                },
            },
        }
