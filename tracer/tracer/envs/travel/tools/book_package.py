import json
import uuid
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from tracer.envs.tool import Tool


def _find_booking(
    data: Dict[str, Any], booking_id: str
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    for traveler in data["travelers"].values():
        for booking in traveler["bookings"]:
            if booking["booking_id"] == booking_id:
                return traveler, booking
    return None, None


def _new_booking_id(data: Dict[str, Any]) -> str:
    while True:
        booking_id = "BKG" + uuid.uuid4().hex[:8].upper()
        _, existing = _find_booking(data, booking_id)
        if existing is None:
            return booking_id


def _get_today_date() -> str:
    """Get current date in YY-MM-DD format (simple stub)."""
    return "2024-05-15"


def _validate_departure(
    package: Dict[str, Any], departure_date: str, required_slots: int
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    departures = package["departures"]
    if departure_date not in departures:
        return None, f"Package {package['package_id']} not offered on {departure_date}"
    dep = departures[departure_date]
    if dep["status"] != "available":
        return (
            None,
            f"Departure on {departure_date} for package {package['package_id']} is not available",
        )
    if dep["available_slots"] < required_slots:
        return (
            None,
            f"Not enough slots on {departure_date}. Needed {required_slots}, available {dep['available_slots']}",
        )
    return dep, None


def _calc_total_price(
    base_price_per_person: float,
    num_travelers: int,
    add_ons: List[Dict[str, Any]],
    insurance: Optional[str],
) -> float:
    total = base_price_per_person * num_travelers
    total += sum(addon["price"] for addon in add_ons)
    if insurance:
        ins_lower = insurance.strip().lower()
        if ins_lower == "standard":
            total += 50.0 * num_travelers
        elif ins_lower == "premium":
            total += 100.0 * num_travelers
        else:
            total += 0.0
    return round(total, 2)


def _validate_payments(
    traveler: Dict[str, Any],
    payments: List[Dict[str, Any]],
    expected_total: float,
) -> Optional[str]:
    for p in payments:
        if p["payment_id"] not in traveler["payment_methods"]:
            return f"Payment method {p['payment_id']} not found for traveler"
    paid = round(sum(p["amount"] for p in payments), 2)
    if round(expected_total, 2) != paid:
        return f"Payment amount does not add up, total price is {expected_total}, but paid {paid}"
    return None


class BookPackageTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        traveler_id: str,
        package_id: str,
        departure_date: str,
        travelers: List[Dict[str, Any]],
        rooming: Dict[str, Any],
        add_ons: List[Dict[str, Any]],
        insurance: Optional[str],
        payment_methods: List[Dict[str, Any]],
        agent_id: Optional[str] = None,
    ) -> str:
        traveler = data["travelers"].get(traveler_id)
        if traveler is None:
            return "Error: Traveler not found"
        package = data["packages"].get(package_id)
        if package is None:
            return "Error: Package not found"

        if agent_id is None:
            if not package["managed_by_agents"]:
                return "Error: No managing agent available for this package"
            agent_id = package["managed_by_agents"][0]
        agent = data["agents"].get(agent_id)
        if agent is None:
            return "Error: Agent not found"

        num_travelers = len(travelers)
        departure, error = _validate_departure(
            package, departure_date, required_slots=num_travelers
        )
        if error:
            return f"Error: {error}"

        total_price = _calc_total_price(
            base_price_per_person=departure["base_price"],
            num_travelers=num_travelers,
            add_ons=add_ons,
            insurance=insurance,
        )

        payment_error = _validate_payments(traveler, payment_methods, total_price)
        if payment_error:
            return f"Error: {payment_error}"

        booking_id = _new_booking_id(data)
        booking = {
            "booking_id": booking_id,
            "package_id": package_id,
            "agent_id": agent_id,
            "booking_date": _get_today_date(),
            "departure_date": departure_date,
            "status": "confirmed",
            "travelers": deepcopy(travelers),
            "rooming": deepcopy(rooming),
            "add_ons": deepcopy(add_ons),
            "insurance": insurance,
            "payment_history": deepcopy(payment_methods),
            "total_price": total_price,
            "notes": None,
        }

        traveler["bookings"].append(booking)
        package["departures"][departure_date]["available_slots"] -= num_travelers
        if traveler_id not in agent["assigned_travelers"]:
            agent["assigned_travelers"].append(traveler_id)
        if booking_id not in agent["bookings_handled"]:
            agent["bookings_handled"].append(booking_id)

        return json.dumps(booking)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "book_package",
                "description": (
                    "Create a new booking for a traveler. The payment_ids used must exist in the "
                    "traveler's payment_methods, and the sum of payment amounts must equal the "
                    "computed total price. The agent needs to explain the details and ask for "
                    "explicit user confirmation (yes/no) before calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "traveler_id": {
                            "type": "string",
                            "description": "The traveler id.",
                        },
                        "package_id": {
                            "type": "string",
                            "description": "The package id to book.",
                        },
                        "departure_date": {
                            "type": "string",
                            "description": "Departure date in YY-MM-DD format.",
                        },
                        "travelers": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "List of travelers on this booking, each with first_name, last_name, and dob (YY-MM-DD).",
                        },
                        "rooming": {
                            "type": "object",
                            "description": "Rooming configuration with room_type and occupancy.",
                        },
                        "add_ons": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "List of add-ons, each with type, description, and price.",
                        },
                        "insurance": {
                            "type": "string",
                            "description": "Insurance selection label (e.g., 'standard', 'premium'), or null for none.",
                        },
                        "payment_methods": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "List of payments, each with payment_id and amount, summing to the total price.",
                        },
                        "agent_id": {
                            "type": "string",
                            "description": "Optional agent id to assign; defaults to the package's first managing agent.",
                        },
                    },
                    "required": [
                        "traveler_id",
                        "package_id",
                        "departure_date",
                        "travelers",
                        "rooming",
                        "add_ons",
                        "insurance",
                        "payment_methods",
                    ],
                },
            },
        }
