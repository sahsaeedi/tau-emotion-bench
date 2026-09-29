import json
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool
from tracer.envs.travel.tools.book_package import _calc_total_price, _validate_departure

# Read-only price quote using book_package's own helpers, so total_price is exactly
# what the tool will demand. 14 of 24 failed travel tasks paid the wrong total (10 of
# them the per-person base_price); travel had no preview tool.


class PreviewBookingPrice(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        package_id: str,
        departure_date: str,
        num_travelers: int,
        add_ons: Optional[List[Dict[str, Any]]] = None,
        insurance: Optional[str] = None,
        traveler_id: Optional[str] = None,
    ) -> str:
        package = data["packages"].get(package_id)
        if package is None:
            return "Error: Package not found"
        n = int(num_travelers)
        departure, error = _validate_departure(
            package, departure_date, required_slots=n
        )
        if error:
            return f"Error: {error}"
        add_ons = add_ons or []
        total = _calc_total_price(departure["base_price"], n, add_ons, insurance)
        ins = (insurance or "").strip().lower()
        per_traveler_ins = (
            50.0 if ins == "standard" else 100.0 if ins == "premium" else 0.0
        )
        out: Dict[str, Any] = {
            "total_price": total,
            "base_price_per_traveler": departure["base_price"],
            "travelers": n,
            "base_subtotal": round(departure["base_price"] * n, 2),
            "add_ons_total": round(sum(a["price"] for a in add_ons), 2),
            "insurance_total": round(per_traveler_ins * n, 2),
            "insurance_label_priced": bool(per_traveler_ins),
            "currency": departure.get("currency"),
            "available_slots": departure["available_slots"],
            "default_agent_id": (package.get("managed_by_agents") or [None])[0],
            "note": "book_package requires payments summing EXACTLY to total_price; each payment_id must be a saved method of the traveler.",
        }
        if traveler_id is not None:
            traveler = data["travelers"].get(traveler_id)
            if traveler is None:
                return "Error: Traveler not found"
            out["traveler_payment_method_ids"] = sorted(
                traveler.get("payment_methods", {})
            )
        return json.dumps(out)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "preview_booking_price",
                "description": (
                    "Read-only quote of what book_package will charge: base_price x travelers + "
                    "add-ons + insurance (standard $50 / premium $100 per traveler, any other label $0), "
                    "after the same departure availability / slot checks. Returns total_price, its "
                    "components, available_slots and (with traveler_id) the traveler's payment method "
                    "ids. Call it before writing book_package or a date/add-on change and copy the total."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "package_id": {"type": "string"},
                        "departure_date": {
                            "type": "string",
                            "description": "YY-MM-DD, one of the package's departures.",
                        },
                        "num_travelers": {"type": "integer"},
                        "add_ons": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string"},
                                    "description": {"type": "string"},
                                    "price": {"type": "number"},
                                },
                                "required": ["type", "description", "price"],
                            },
                        },
                        "insurance": {
                            "type": "string",
                            "description": "Insurance label or null.",
                        },
                        "traveler_id": {"type": "string"},
                    },
                    "required": ["package_id", "departure_date", "num_travelers"],
                },
            },
        }
