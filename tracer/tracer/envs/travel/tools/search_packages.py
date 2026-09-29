import json
from typing import Any, Dict, Optional

from tracer.envs.tool import Tool


class SearchPackagesTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        destination_city: Optional[str] = None,
        destination_country: Optional[str] = None,
        category: Optional[str] = None,
        departure_date: Optional[str] = None,
    ) -> str:
        results = []
        for pkg in data["packages"].values():
            if destination_city or destination_country:
                dest_match = any(
                    (destination_city is None or loc["city"] == destination_city)
                    and (
                        destination_country is None
                        or loc["country"] == destination_country
                    )
                    for loc in pkg["destinations"]
                )
                if not dest_match:
                    continue
            if category and pkg["category"] != category:
                continue
            if departure_date and departure_date not in pkg["departures"]:
                continue
            if any(
                d["status"] == "available" and d["available_slots"] > 0
                for d in pkg["departures"].values()
            ):
                results.append(pkg)
        return json.dumps(results)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_packages",
                "description": "Search packages by destination/filter criteria.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "destination_city": {
                            "type": "string",
                            "description": "Filter by destination city name.",
                        },
                        "destination_country": {
                            "type": "string",
                            "description": "Filter by destination country name.",
                        },
                        "category": {
                            "type": "string",
                            "description": "Filter by package category.",
                        },
                        "departure_date": {
                            "type": "string",
                            "description": "Filter packages that depart on this date (YY-MM-DD).",
                        },
                    },
                    "required": [],
                },
            },
        }
