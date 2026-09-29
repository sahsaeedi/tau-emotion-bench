# Copyright Sierra

import json
import random
from typing import Any, Dict

from tracer.envs.tool import Tool

# Max number of options to return per call
_MAX_FLIGHTS = 5

# Call counter: each invoke returns the "next" batch so subsequent calls get different results
_call_counter = 0


class GetFlightsFromOrigin(Tool):
    """Return all flights from an origin on a date. stops=0: direct only; stops=1: one-stop (origin→B→C, C≠origin)."""

    @staticmethod
    def invoke(data: Dict[str, Any], origin: str, date: str, stops: int) -> str:
        global _call_counter
        flights = data["flights"]

        if stops == 0:
            results = []
            for flight in flights.values():
                if (
                    flight["origin"] == origin
                    and date in flight["dates"]
                    and flight["dates"][date]["status"] == "available"
                ):
                    item = {k: v for k, v in flight.items() if k != "dates"}
                    item.update(flight["dates"][date])
                    results.append(item)
            random.shuffle(results)
            if not results:
                return json.dumps([])
            offset = (_call_counter * _MAX_FLIGHTS) % len(results)
            _call_counter += 1
            results_doubled = results + results
            result = results_doubled[offset : offset + _MAX_FLIGHTS]
            return json.dumps(result)

        if stops == 1:
            results = []
            for flight1 in flights.values():
                if flight1["origin"] != origin:
                    continue
                for flight2 in flights.values():
                    if flight1["destination"] != flight2["origin"]:
                        continue
                    # Second leg must go to an airport other than origin (no return-to-origin)
                    if flight2["destination"] == origin:
                        continue
                    date2 = (
                        f"2024-05-{int(date[-2:]) + 1}"
                        if "+1" in flight1["scheduled_arrival_time_est"]
                        else date
                    )
                    # Connecting flight must depart after the first flight lands
                    if (
                        flight1["scheduled_arrival_time_est"]
                        >= flight2["scheduled_departure_time_est"]
                    ):
                        continue
                    if date not in flight1["dates"] or date2 not in flight2["dates"]:
                        continue
                    if (
                        flight1["dates"][date]["status"] != "available"
                        or flight2["dates"][date2]["status"] != "available"
                    ):
                        continue
                    result1 = {k: v for k, v in flight1.items() if k != "dates"}
                    result1.update(flight1["dates"][date])
                    result1["date"] = date
                    result2 = {k: v for k, v in flight2.items() if k != "dates"}
                    result2.update(flight2["dates"][date2])
                    result2["date"] = date2
                    results.append([result1, result2])
            random.shuffle(results)
            if not results:
                return json.dumps([])
            offset = (_call_counter * _MAX_FLIGHTS) % len(results)
            _call_counter += 1
            results_doubled = results + results
            result = results_doubled[offset : offset + _MAX_FLIGHTS]
            return json.dumps(result)

        return json.dumps({"error": "stops must be 0 or 1"})

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_flights_from_origin",
                "description": "Get all flights from an origin on a given date. If stops=0, returns all direct flights from origin on that date. If stops=1, returns all one-stop options: a flight from origin to airport B on that date, then a connecting flight from B to any other airport (excluding origin) that departs after the first flight lands.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "The origin airport code (e.g. 'JFK').",
                        },
                        "date": {
                            "type": "string",
                            "description": "The date in 'YYYY-MM-DD' format (e.g. '2024-05-20').",
                        },
                        "stops": {
                            "type": "integer",
                            "description": "0 for direct flights only; 1 for one-stop flights (origin → B → C, where C ≠ origin).",
                            "enum": [0, 1],
                        },
                    },
                    "required": ["origin", "date", "stops"],
                },
            },
        }
