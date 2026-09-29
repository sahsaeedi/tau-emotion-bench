# Copyright Sierra

import json
import random
from typing import Any, Dict

from tracer.envs.tool import Tool


class GenerateNewAddress(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any]) -> str:
        # Generate a new random address
        streets = [
            "Main Street",
            "Oak Avenue",
            "Park Drive",
            "Maple Lane",
            "Elm Street",
            "Cedar Road",
            "Pine Avenue",
            "Washington Boulevard",
            "Lincoln Street",
            "Jefferson Avenue",
            "Madison Drive",
            "Adams Road",
            "Jackson Street",
        ]
        suite_types = ["Suite", "Apt", "Unit", "Floor"]

        # City to state mapping to ensure correct matches
        city_state_map = {
            "New York": "NY",
            "Los Angeles": "CA",
            "Chicago": "IL",
            "Houston": "TX",
            "Phoenix": "AZ",
            "Philadelphia": "PA",
            "San Antonio": "TX",
            "San Diego": "CA",
            "Dallas": "TX",
            "San Jose": "CA",
            "Austin": "TX",
            "Jacksonville": "FL",
            "San Francisco": "CA",
            "Columbus": "OH",
            "Fort Worth": "TX",
            "Charlotte": "NC",
            "Seattle": "WA",
            "Denver": "CO",
            "Boston": "MA",
            "Nashville": "TN",
            "Detroit": "MI",
            "Portland": "OR",
            "Oklahoma City": "OK",
            "Las Vegas": "NV",
        }

        address1 = f"{random.randint(100, 9999)} {random.choice(streets)}"
        address2 = f"{random.choice(suite_types)} {random.randint(1, 999)}"
        city = random.choice(list(city_state_map.keys()))
        state = city_state_map[city]
        country = "USA"
        zip_code = str(random.randint(10000, 99999))

        address = {
            "address1": address1,
            "address2": address2,
            "city": city,
            "state": state,
            "country": country,
            "zip": zip_code,
        }

        return json.dumps(address)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "generate_new_address",
                "description": "Generate a new random address with all address fields.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
