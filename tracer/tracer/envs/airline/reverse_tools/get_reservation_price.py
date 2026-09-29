import json
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool

# Read-only dry run of book_reservation's pricing (tools/book_reservation.py:54-92).
# Walks the same flight-date records, applies the same checks, adds the same insurance
# and baggage fees, and never writes. The generator was summing fares by hand and
# paid e.g. 217 of a 1230 total in 6 of 11 failed airline bookings.

FREE_BAGS = {  # wiki.md:36 -- free checked bags per passenger by membership x cabin
    "regular": {"basic_economy": 0, "economy": 1, "business": 2},
    "silver": {"basic_economy": 1, "economy": 2, "business": 3},
    "gold": {"basic_economy": 2, "economy": 3, "business": 3},
}


class GetReservationPrice(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        flights: List[Dict[str, Any]],
        cabin: str,
        passengers: int,
        insurance: str = "no",
        total_baggages: int = 0,
        user_id: Optional[str] = None,
    ) -> str:
        n = int(passengers)
        legs = []
        subtotal = 0
        for leg in flights:
            fn, date = leg.get("flight_number"), leg.get("date")
            fdata = data["flights"].get(fn)
            if fdata is None:
                return f"Error: flight {fn} not found"
            day = fdata.get("dates", {}).get(date)
            if day is None:
                return f"Error: flight {fn} not found on date {date}"
            if day["status"] != "available":
                return f"Error: flight {fn} not available on date {date}"
            if cabin not in day["prices"]:
                return f"Error: unknown cabin {cabin}"
            if day["available_seats"][cabin] < n:
                return f"Error: not enough seats on flight {fn}"
            price = day["prices"][cabin]
            subtotal += price * n
            legs.append(
                {
                    "flight_number": fn,
                    "date": date,
                    "origin": fdata["origin"],
                    "destination": fdata["destination"],
                    "price_per_passenger": price,
                    "seats_left": day["available_seats"][cabin],
                }
            )

        insurance_fee = 30 * n if insurance == "yes" else 0

        membership = None
        payment_methods = []
        if user_id is not None:
            user = data["users"].get(user_id)
            if user is None:
                return f"Error: user {user_id} not found"
            membership = user.get("membership")
            payment_methods = [
                {
                    "payment_id": pid,
                    "source": m.get("source"),
                    **({"balance": m["amount"]} if "amount" in m else {}),
                }
                for pid, m in user.get("payment_methods", {}).items()
            ]
        free = FREE_BAGS.get(membership or "regular", FREE_BAGS["regular"])[cabin] * n
        nonfree = max(0, int(total_baggages) - free)
        baggage_fee = 50 * nonfree
        total = subtotal + insurance_fee + baggage_fee

        return json.dumps(
            {
                "total_price": total,
                "flights_subtotal": subtotal,
                "insurance_fee": insurance_fee,
                "baggage_fee": baggage_fee,
                "passengers": n,
                "cabin": cabin,
                "legs": legs,
                "membership": membership,
                "free_baggages": free,
                "nonfree_baggages": nonfree,
                "payment_methods": payment_methods,
                "note": (
                    "book_reservation requires payment amounts summing EXACTLY to total_price; "
                    "gift_card / certificate need balance >= their amount; pass nonfree_baggages "
                    "as computed here."
                ),
            }
        )

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_reservation_price",
                "description": (
                    "Read-only price quote for a booking: exactly what book_reservation will charge "
                    "for these flights, cabin, passenger count, insurance and bags (fare per leg x "
                    "passengers + $30/passenger insurance + $50 per non-free bag), with the same "
                    "availability/seat checks. Returns total_price, the breakdown, nonfree_baggages, "
                    "and (with user_id) the user's payment methods and balances. Always call it before "
                    "writing a book_reservation action and copy total_price into the payment amounts."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "flights": {
                            "type": "array",
                            "description": "Legs in order, as book_reservation takes them.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "flight_number": {"type": "string"},
                                    "date": {
                                        "type": "string",
                                        "description": "YYYY-MM-DD",
                                    },
                                },
                                "required": ["flight_number", "date"],
                            },
                        },
                        "cabin": {
                            "type": "string",
                            "enum": ["basic_economy", "economy", "business"],
                        },
                        "passengers": {
                            "type": "integer",
                            "description": "Number of passengers.",
                        },
                        "insurance": {"type": "string", "enum": ["yes", "no"]},
                        "total_baggages": {
                            "type": "integer",
                            "description": "Total checked bags (default 0).",
                        },
                        "user_id": {
                            "type": "string",
                            "description": "Booking user; sets membership for the free-bag allowance and returns payment methods.",
                        },
                    },
                    "required": ["flights", "cabin", "passengers"],
                },
            },
        }
