"""
Find all users that have at least one reservation where every flight in that
reservation was cancelled.
"""

import json
import random
from typing import Any, Dict

from tracer.envs.tool import Tool

# Max number of results to return per call (subset, not all)
_MAX_RESULTS = 5

# Call counter: each invoke returns the "next" batch so subsequent calls get different results
_call_counter = 0


class GetUsersWithCancelledFlights(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any]) -> str:
        """
        Find all users who had a reservation where all flights in that
        reservation were cancelled.
        """
        global _call_counter
        reservations = data["reservations"]
        flights_data = data["flights"]
        results = []

        for res_id, res in reservations.items():
            res_flights = res.get("flights", [])
            if not res_flights:
                continue
            all_cancelled = True
            flight_ids = []
            for flight in res_flights:
                flight_number = flight.get("flight_number")
                date = flight.get("date")
                if not flight_number or not date:
                    all_cancelled = False
                    break
                flight_info = flights_data.get(flight_number)
                if not flight_info:
                    all_cancelled = False
                    break
                dates = flight_info.get("dates", {})
                date_info = dates.get(date)
                if not date_info or date_info.get("status") != "cancelled":
                    all_cancelled = False
                    break
                flight_ids.append(flight_number)
            if all_cancelled:
                user_id = res.get("user_id")
                if user_id:
                    results.append(
                        {
                            "user_id": user_id,
                            "reservation_id": res_id,
                            "flight_ids": flight_ids,
                        }
                    )

        # Randomize the list, then return the offset-based batch
        random.shuffle(results)
        if not results:
            return json.dumps([])
        # Rotating offset: each call returns the next batch, wrapping when past the end
        offset = (_call_counter * _MAX_RESULTS) % len(results)
        _call_counter += 1
        results_doubled = results + results
        result = results_doubled[offset : offset + _MAX_RESULTS]
        return json.dumps(result)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_users_with_cancelled_flights",
                "description": (
                    "Get all users who have experienced cancelled flights in their reservations. "
                    "Returns a list of objects with user_id, reservation_id, and flight_ids. "
                    "This function can be used for getting compensation if cancelled. "
                    "Results are randomized; each call returns up to 5 results with a rotating offset (different batch on subsequent calls). "
                    "Takes no parameters; uses the loaded reservations and flights data."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
