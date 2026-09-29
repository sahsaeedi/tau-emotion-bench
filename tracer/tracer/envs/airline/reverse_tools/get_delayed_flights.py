import json
import random
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetDelayedFlights(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        date: str,
    ) -> str:
        """
        Find flights that experienced a departure delay on a given date.
        """
        flights, reservations = data["flights"], data["reservations"]

        # Flights that appear in any reservation (flight_number, date)
        flights_with_reservations = set()
        for res in reservations.values():
            for seg in res.get("flights", []):
                fn, d = seg.get("flight_number"), seg.get("date")
                if fn and d:
                    flights_with_reservations.add((fn, d))

        result = []
        from datetime import datetime

        for flight_id, info in flights.items():
            day = info.get("dates", {}).get(date)
            if not day or day.get("status") != "landed":
                continue

            actual_iso = day.get("actual_departure_time_est")
            scheduled_time = info.get("scheduled_departure_time_est")
            if not actual_iso or not scheduled_time:
                continue

            try:
                scheduled_dt = datetime.strptime(
                    f"{date}T{scheduled_time}",
                    "%Y-%m-%dT%H:%M:%S",
                )
                actual_dt = datetime.fromisoformat(actual_iso)
            except Exception:
                continue

            if actual_dt <= scheduled_dt:
                continue

            # Skip flights that have any reservations
            flight_number = info.get("flight_number", flight_id)
            if (flight_number, date) in flights_with_reservations:
                continue

            delay_minutes = int((actual_dt - scheduled_dt).total_seconds() // 60)

            result.append(
                {
                    "flight_id": flight_id,
                    "flight_number": info.get("flight_number"),
                    "origin": info.get("origin"),
                    "destination": info.get("destination"),
                    "date": date,
                    "status": day.get("status"),
                    "delay_minutes": delay_minutes,
                    "details": day,
                }
            )

        random.shuffle(result)

        return json.dumps(result)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_delayed_flights",
                "description": (
                    "Find flights that experienced a departure delay on a given date.\n\n    A delayed flight is one whose actual departure time (if available)\n    occurs strictly after its scheduled departure time."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "The date to retrieve delayed flights for in ISO format (YYYY-MM-DD), such as '2024-04-27'.",
                        },
                    },
                    "required": ["date"],
                },
            },
        }
