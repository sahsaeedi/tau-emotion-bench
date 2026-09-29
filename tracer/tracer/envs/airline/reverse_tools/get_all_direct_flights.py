# Copyright Sierra

import json
import random
from typing import Any, Dict

from tracer.envs.tool import Tool

# Max number of flights to return per call
_MAX_FLIGHTS = 5

# Call counter: each invoke returns the "next" batch so subsequent calls get different results
_call_counter = 0


class GetAllDirectFlights(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], origin: str, date: str) -> str:
        global _call_counter
        flights = data["flights"]
        results = []
        for flight in flights.values():
            if (
                flight["origin"] == origin
                and date in flight["dates"]
                and flight["dates"][date]["status"] == "available"
            ):
                results.append({k: v for k, v in flight.items() if k != "dates"})
                results[-1].update(flight["dates"][date])
        # Randomize the list, then return the offset-based batch
        random.shuffle(results)
        if not results:
            return json.dumps([])
        # Rotating offset: each call returns the next batch, wrapping when past the end
        offset = (_call_counter * _MAX_FLIGHTS) % len(results)
        _call_counter += 1
        results_doubled = results + results
        result = results_doubled[offset : offset + _MAX_FLIGHTS]
        if not result:
            return "No direct flights found on the given date. Flights are only available from 2024-05-16 to 2024-05-30."
        return json.dumps(result)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_all_direct_flights",
                "description": "Get all direct flights on a specific date from a given origin. Results are randomized; each call returns up to 5 flights with a rotating offset (different batch on subsequent calls).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "The origin city airport in three letters, such as 'JFK'.",
                        },
                        "date": {
                            "type": "string",
                            "description": "The date of the flight in the format 'YYYY-MM-DD', such as '2024-05-01'.",
                        },
                    },
                    "required": ["origin", "date"],
                },
            },
        }
