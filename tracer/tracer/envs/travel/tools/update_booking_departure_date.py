import json
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


class UpdateBookingDepartureDateTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        booking_id: str,
        new_departure_date: str,
        payment_method_id: str,
    ) -> str:
        traveler, booking = _find_booking(data, booking_id)
        if booking is None:
            return "Error: Booking not found"
        package = data["packages"].get(booking["package_id"])
        if package is None:
            return "Error: Package not found for this booking"

        if payment_method_id not in traveler["payment_methods"]:
            return "Error: Payment method not found for traveler"

        num_travelers = len(booking["travelers"])

        new_dep, error = _validate_departure(
            package, new_departure_date, required_slots=num_travelers
        )
        if error:
            return f"Error: {error}"

        old_total_price = booking["total_price"]
        new_total_price = _calc_total_price(
            base_price_per_person=new_dep["base_price"],
            num_travelers=num_travelers,
            add_ons=booking["add_ons"],
            insurance=booking["insurance"],
        )
        delta = round(new_total_price - old_total_price, 2)

        old_departure = package["departures"].get(booking["departure_date"])
        if old_departure is not None:
            old_departure["available_slots"] += num_travelers
        package["departures"][new_departure_date]["available_slots"] -= num_travelers

        if delta != 0:
            booking["payment_history"].append(
                {"payment_id": payment_method_id, "amount": delta}
            )

        booking["departure_date"] = new_departure_date
        booking["total_price"] = new_total_price
        return json.dumps(booking)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "update_booking_departure_date",
                "description": (
                    "Change the departure date for a booking and charge/refund the base price "
                    "difference. Updates departure slots on both the old and new dates accordingly. "
                    "The agent needs to explain the details and ask for explicit user confirmation "
                    "(yes/no) before calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "booking_id": {
                            "type": "string",
                            "description": "The booking id.",
                        },
                        "new_departure_date": {
                            "type": "string",
                            "description": "The new departure date in YY-MM-DD format.",
                        },
                        "payment_method_id": {
                            "type": "string",
                            "description": "Traveler's saved payment method ID to use for the delta.",
                        },
                    },
                    "required": [
                        "booking_id",
                        "new_departure_date",
                        "payment_method_id",
                    ],
                },
            },
        }
