"""Toolkit for the airline domain, ported from TRACER's environment
(tracer/tracer/envs/airline/).

14 tools mirroring TRACER's `ALL_TOOLS`, including its checks, database writes
and return values. Conversion rules from TRACER's tools:

- `data["reservations"]` → `self.db.reservations`.
- `return "Error: ..."`, and any exception TRACER's tool raises (e.g. a
  KeyError), → an exception with the same message. Both frameworks show
  exceptions to the agent as "Error: <message>".
- `return json.dumps(record)` → `_record_json(record)`, which leaves out
  fields the record never had, as TRACER's raw dict would.
- Free-function `invoke(data, ...)` → instance method with `@is_tool(...)`.

Unlike upstream tau2-bench, booking does not take seats off the flight, a
flight change keeps the reservation's original cabin, and one-stop search
reports the second flight's seats and prices for the first flight's date.
"""

import json
from copy import deepcopy
from typing import Any, List, Optional

from pydantic import BaseModel

from tau_emotion.domains.airline.data_model import (
    CabinClass,
    Certificate,
    Flight,
    FlightDB,
    FlightInfo,
    FlightType,
    Insurance,
    Passenger,
    Payment,
    Reservation,
    ReservationFlight,
)
from tau_emotion.environment.toolkit import ToolKitBase, ToolType, is_tool

CREATED_AT = "2024-05-15T15:00:00"
# TRACER assumes each task makes at most 3 reservations and sends at most 3
# certificates.
NEW_RESERVATION_IDS = ["HATHAT", "HATHAU", "HATHAV"]
NEW_CERTIFICATE_NUMBERS = [3221322, 3221323, 3221324]

AIRPORTS = {
    "SFO": "San Francisco",
    "JFK": "New York",
    "LAX": "Los Angeles",
    "ORD": "Chicago",
    "DFW": "Dallas",
    "DEN": "Denver",
    "SEA": "Seattle",
    "ATL": "Atlanta",
    "MIA": "Miami",
    "BOS": "Boston",
    "PHX": "Phoenix",
    "IAH": "Houston",
    "LAS": "Las Vegas",
    "MCO": "Orlando",
    "EWR": "Newark",
    "CLT": "Charlotte",
    "MSP": "Minneapolis",
    "DTW": "Detroit",
    "PHL": "Philadelphia",
    "LGA": "LaGuardia",
}


def _record_json(record: BaseModel, exclude: Optional[set[str]] = None) -> str:
    return json.dumps(record.model_dump(exclude_unset=True, exclude=exclude))


def _as_dicts(items: List[Any]) -> List[dict]:
    return [
        item.model_dump() if isinstance(item, BaseModel) else deepcopy(item)
        for item in items
    ]


def _flight_on_date(flight: Flight, date: str) -> dict:
    """TRACER's search row: the flight without `dates`, plus that date's status."""
    row = flight.model_dump(exclude={"dates"})
    row.update(flight.dates[date].model_dump())
    return row


class AirlineTools(ToolKitBase):
    """All the tools for the airline domain."""

    db: FlightDB

    def __init__(self, db: FlightDB) -> None:
        super().__init__(db)

    def _price_flight(self, flight: dict, cabin: str, num_passengers: int) -> int:
        """Check a new flight segment and fill in its price, origin and
        destination, as TRACER's tool does. Returns the segment's total price."""
        flight_number = flight["flight_number"]
        if flight_number not in self.db.flights:
            raise ValueError(f"flight {flight_number} not found")
        flight_data = self.db.flights[flight_number]
        if flight["date"] not in flight_data.dates:
            raise ValueError(
                f"flight {flight_number} not found on date {flight['date']}"
            )
        flight_date_data = flight_data.dates[flight["date"]]
        if flight_date_data.status != "available":
            raise ValueError(
                f"flight {flight_number} not available on date {flight['date']}"
            )
        if flight_date_data.available_seats[cabin] < num_passengers:
            raise ValueError(f"not enough seats on flight {flight_number}")
        flight["price"] = flight_date_data.prices[cabin]
        flight["origin"] = flight_data.origin
        flight["destination"] = flight_data.destination
        return flight["price"] * num_passengers

    def _update_payment_method(
        self, user_id: str, payment_id: str, total_price: int
    ) -> Any:
        """TRACER's payment checks for reservation updates."""
        payment_methods = self.db.users[user_id].payment_methods
        if payment_id not in payment_methods:
            raise ValueError("payment method not found")
        payment_method = payment_methods[payment_id]
        if payment_method.source == "certificate":
            raise ValueError("certificate cannot be used to update reservation")
        elif (
            payment_method.source == "gift_card" and payment_method.amount < total_price
        ):
            raise ValueError("gift card balance is not enough")
        return payment_method

    @is_tool(ToolType.WRITE)
    def book_reservation(
        self,
        user_id: str,
        origin: str,
        destination: str,
        flight_type: FlightType,
        cabin: CabinClass,
        flights: List[FlightInfo | dict],
        passengers: List[Passenger | dict],
        payment_methods: List[Payment | dict],
        total_baggages: int,
        nonfree_baggages: int,
        insurance: Insurance,
    ) -> str:
        """Book a reservation.

        Args:
            user_id: The ID of the user to book the reservation, such as 'sara_doe_496'.
            origin: The IATA code for the origin city, such as 'SFO'.
            destination: The IATA code for the destination city, such as 'JFK'.
            flight_type: The type of flight, 'one_way' or 'round_trip'.
            cabin: The cabin class, 'basic_economy', 'economy', or 'business'.
            flights: An array of objects containing details about each piece of flight.
            passengers: An array of objects containing details about each passenger.
            payment_methods: An array of objects containing details about each payment method.
            total_baggages: The total number of baggage items included in the reservation.
            nonfree_baggages: The number of non-free baggage items included in the reservation.
            insurance: Whether the reservation has insurance, 'yes' or 'no'.

        Returns:
            The new reservation as JSON.
        """
        if user_id not in self.db.users:
            raise ValueError("user not found")
        user = self.db.users[user_id]

        # A fourth booking in one task overwrites HATHAV, as in TRACER's tool.
        reservation_id = next(
            (
                rid
                for rid in NEW_RESERVATION_IDS[:-1]
                if rid not in self.db.reservations
            ),
            NEW_RESERVATION_IDS[-1],
        )

        flights = _as_dicts(flights)
        passengers = _as_dicts(passengers)
        payment_methods = _as_dicts(payment_methods)
        total_price = 0
        for flight in flights:
            total_price += self._price_flight(flight, cabin, len(passengers))

        if insurance == "yes":
            total_price += 30 * len(passengers)
        total_price += 50 * nonfree_baggages

        for payment_method in payment_methods:
            payment_id = payment_method["payment_id"]
            amount = payment_method["amount"]
            if payment_id not in user.payment_methods:
                raise ValueError(f"payment method {payment_id} not found")
            if user.payment_methods[payment_id].source in ["gift_card", "certificate"]:
                if user.payment_methods[payment_id].amount < amount:
                    raise ValueError(
                        f"not enough balance in payment method {payment_id}"
                    )
        paid = sum(payment["amount"] for payment in payment_methods)
        if paid != total_price:
            raise ValueError(
                f"payment amount does not add up, total price is {total_price}, but paid {paid}"
            )

        reservation = Reservation(
            reservation_id=reservation_id,
            user_id=user_id,
            origin=origin,
            destination=destination,
            flight_type=flight_type,
            cabin=cabin,
            flights=[ReservationFlight(**flight) for flight in flights],
            passengers=[Passenger(**passenger) for passenger in passengers],
            payment_history=[Payment(**payment) for payment in payment_methods],
            created_at=CREATED_AT,
            total_baggages=total_baggages,
            nonfree_baggages=nonfree_baggages,
            insurance=insurance,
        )

        # TRACER's tool deducts payments but leaves the flights' available seats alone.
        for payment_method in payment_methods:
            payment_id = payment_method["payment_id"]
            user_payment_method = user.payment_methods[payment_id]
            if user_payment_method.source == "gift_card":
                user_payment_method.amount -= payment_method["amount"]
            elif user_payment_method.source == "certificate":
                del user.payment_methods[payment_id]

        self.db.reservations[reservation_id] = reservation
        user.reservations.append(reservation_id)
        return _record_json(reservation)

    @is_tool(ToolType.GENERIC)
    def calculate(self, expression: str) -> str:
        """Calculate the result of a mathematical expression.

        Args:
            expression: The mathematical expression to calculate, such as '2 + 2'. The expression can contain numbers, operators (+, -, *, /), parentheses, and spaces.

        Returns:
            The result rounded to two decimals, as a string.
        """
        if not all(char in "0123456789+-*/(). " for char in expression):
            raise ValueError("invalid characters in expression")
        return str(round(float(eval(expression, {"__builtins__": None}, {})), 2))  # noqa: S307

    @is_tool(ToolType.WRITE)
    def cancel_reservation(self, reservation_id: str) -> str:
        """Cancel the whole reservation.

        Args:
            reservation_id: The reservation ID, such as 'ZFA04Y'.

        Returns:
            The cancelled reservation as JSON.
        """
        if reservation_id not in self.db.reservations:
            raise ValueError("reservation not found")
        reservation = self.db.reservations[reservation_id]
        refunds = [
            Payment(payment_id=payment.payment_id, amount=-payment.amount)
            for payment in reservation.payment_history
        ]
        reservation.payment_history.extend(refunds)
        reservation.status = "cancelled"
        return _record_json(reservation)

    @is_tool(ToolType.READ)
    def get_reservation_details(self, reservation_id: str) -> str:
        """Get the details of a reservation.

        Args:
            reservation_id: The reservation id, such as '8JX2WO'.

        Returns:
            The reservation as JSON.
        """
        if reservation_id in self.db.reservations:
            return _record_json(self.db.reservations[reservation_id])
        # TRACER's message for a missing reservation.
        raise ValueError("user not found")

    @is_tool(ToolType.READ)
    def get_user_details(self, user_id: str) -> str:
        """Get the details of an user, including their reservations.

        Args:
            user_id: The user id, such as 'sara_doe_496'.

        Returns:
            The user as JSON.
        """
        if user_id in self.db.users:
            # TRACER's user records have no user_id field.
            return _record_json(self.db.users[user_id], exclude={"user_id"})
        raise ValueError("user not found")

    @is_tool(ToolType.READ)
    def list_all_airports(self) -> str:
        """List all airports and their cities.

        Returns:
            A JSON object mapping each IATA code to its city.
        """
        return json.dumps(AIRPORTS)

    @is_tool(ToolType.READ)
    def search_direct_flight(self, origin: str, destination: str, date: str) -> str:
        """Search direct flights between two cities on a specific date.

        Args:
            origin: The origin city airport in three letters, such as 'JFK'.
            destination: The destination city airport in three letters, such as 'LAX'.
            date: The date of the flight in the format 'YYYY-MM-DD', such as '2024-01-01'.

        Returns:
            A JSON list of the available flights.
        """
        results = [
            _flight_on_date(flight, date)
            for flight in self.db.flights.values()
            if flight.origin == origin
            and flight.destination == destination
            and date in flight.dates
            and flight.dates[date].status == "available"
        ]
        return json.dumps(results)

    @is_tool(ToolType.READ)
    def search_onestop_flight(self, origin: str, destination: str, date: str) -> str:
        """Search direct flights between two cities on a specific date.

        Args:
            origin: The origin city airport in three letters, such as 'JFK'.
            destination: The destination city airport in three letters, such as 'LAX'.
            date: The date of the flight in the format 'YYYY-MM-DD', such as '2024-05-01'.

        Returns:
            A JSON list of [first flight, second flight] pairs.
        """
        results = []
        for flight1 in self.db.flights.values():
            if flight1.origin != origin:
                continue
            for flight2 in self.db.flights.values():
                if not (
                    flight2.destination == destination
                    and flight1.destination == flight2.origin
                ):
                    continue
                date2 = (
                    f"2024-05-{int(date[-2:]) + 1}"
                    if "+1" in flight1.scheduled_arrival_time_est
                    else date
                )
                if (
                    flight1.scheduled_arrival_time_est
                    > flight2.scheduled_departure_time_est
                ):
                    continue
                if date in flight1.dates and date2 in flight2.dates:
                    if (
                        flight1.dates[date].status == "available"
                        and flight2.dates[date2].status == "available"
                    ):
                        result1 = _flight_on_date(flight1, date)
                        result1["date"] = date
                        # TRACER's tool reads the second flight's status, seats
                        # and prices for `date`, not `date2`.
                        result2 = _flight_on_date(flight2, date)
                        result2["date"] = date2
                        results.append([result1, result2])
        return json.dumps(results)

    @is_tool(ToolType.WRITE)
    def send_certificate(self, user_id: str, amount: float) -> Optional[str]:
        """Send a certificate to a user. Be careful!

        Args:
            user_id: The ID of the user to book the reservation, such as 'sara_doe_496'.
            amount: Certificate amount to send.

        Returns:
            A confirmation message, or nothing if the user already has all
            three certificates a task can add.
        """
        if user_id not in self.db.users:
            raise ValueError("user not found")
        user = self.db.users[user_id]
        for number in NEW_CERTIFICATE_NUMBERS:
            payment_id = f"certificate_{number}"
            if payment_id not in user.payment_methods:
                user.payment_methods[payment_id] = Certificate(
                    source="certificate", amount=amount, id=payment_id
                )
                return f"Certificate {payment_id} added to user {user_id} with amount {amount}."
        return None

    @is_tool(ToolType.THINK)
    def think(self, thought: str) -> str:
        """Use the tool to think about something. It will not obtain new information or change the database, but just append the thought to the log. Use it when complex reasoning is needed.

        Args:
            thought: A thought to think about.

        Returns:
            An empty string.
        """
        return ""

    @is_tool(ToolType.GENERIC)
    def transfer_to_human_agents(self, summary: str) -> str:
        """Transfer the user to a human agent, with a summary of the user's issue. Only transfer if the user explicitly asks for a human agent, or if the user's issue cannot be resolved by the agent with the available tools.

        Args:
            summary: A summary of the user's issue.

        Returns:
            A confirmation message.
        """
        return "Transfer successful"

    @is_tool(ToolType.WRITE)
    def update_reservation_baggages(
        self,
        reservation_id: str,
        total_baggages: int,
        nonfree_baggages: int,
        payment_id: str,
    ) -> str:
        """Update the baggage information of a reservation.

        Args:
            reservation_id: The reservation ID, such as 'ZFA04Y'.
            total_baggages: The updated total number of baggage items included in the reservation.
            nonfree_baggages: The updated number of non-free baggage items included in the reservation.
            payment_id: The payment id stored in user profile, such as 'credit_card_7815826', 'gift_card_7815826', 'certificate_7815826'.

        Returns:
            The updated reservation as JSON.
        """
        if reservation_id not in self.db.reservations:
            raise ValueError("reservation not found")
        reservation = self.db.reservations[reservation_id]

        total_price = 50 * max(0, nonfree_baggages - reservation.nonfree_baggages)
        payment_method = self._update_payment_method(
            reservation.user_id, payment_id, total_price
        )

        reservation.total_baggages = total_baggages
        reservation.nonfree_baggages = nonfree_baggages
        if payment_method.source == "gift_card":
            payment_method.amount -= total_price
        if total_price != 0:
            reservation.payment_history.append(
                Payment(payment_id=payment_id, amount=total_price)
            )
        return _record_json(reservation)

    @is_tool(ToolType.WRITE)
    def update_reservation_flights(
        self,
        reservation_id: str,
        cabin: CabinClass,
        flights: List[FlightInfo | dict],
        payment_id: str,
    ) -> str:
        """Update the flight information of a reservation.

        Args:
            reservation_id: The reservation ID, such as 'ZFA04Y'.
            cabin: The cabin class, 'basic_economy', 'economy', or 'business'.
            flights: An array of objects containing details about each piece of flight in the ENTIRE new reservation. Even if the a flight segment is not changed, it should still be included in the array.
            payment_id: The payment id stored in user profile, such as 'credit_card_7815826', 'gift_card_7815826', 'certificate_7815826'.

        Returns:
            The updated reservation as JSON.
        """
        if reservation_id not in self.db.reservations:
            raise ValueError("reservation not found")
        reservation = self.db.reservations[reservation_id]
        num_passengers = len(reservation.passengers)

        total_price = 0
        flights = _as_dicts(flights)
        for flight in flights:
            # An unchanged segment in the same cabin keeps its booked price.
            existing = [
                f
                for f in reservation.flights
                if f.flight_number == flight["flight_number"]
                and f.date == flight["date"]
                and cabin == reservation.cabin
            ]
            if existing:
                total_price += existing[0].price * num_passengers
                flight["price"] = existing[0].price
                flight["origin"] = existing[0].origin
                flight["destination"] = existing[0].destination
                continue
            total_price += self._price_flight(flight, cabin, num_passengers)

        total_price -= sum(f.price for f in reservation.flights) * num_passengers

        payment_method = self._update_payment_method(
            reservation.user_id, payment_id, total_price
        )
        new_flights = [ReservationFlight(**flight) for flight in flights]

        if payment_method.source == "gift_card":
            payment_method.amount -= total_price
        # TRACER's tool keeps the reservation's original cabin and leaves flight
        # seats alone.
        reservation.flights = new_flights
        if total_price != 0:
            reservation.payment_history.append(
                Payment(payment_id=payment_id, amount=total_price)
            )
        return _record_json(reservation)

    @is_tool(ToolType.WRITE)
    def update_reservation_passengers(
        self, reservation_id: str, passengers: List[Passenger | dict]
    ) -> str:
        """Update the passenger information of a reservation.

        Args:
            reservation_id: The reservation ID, such as 'ZFA04Y'.
            passengers: An array of objects containing details about each passenger.

        Returns:
            The updated reservation as JSON.
        """
        if reservation_id not in self.db.reservations:
            raise ValueError("reservation not found")
        reservation = self.db.reservations[reservation_id]
        if len(passengers) != len(reservation.passengers):
            raise ValueError("number of passengers does not match")
        reservation.passengers = [Passenger(**p) for p in _as_dicts(passengers)]
        return _record_json(reservation)


if __name__ == "__main__":
    from tau_emotion.domains.airline.utils import AIRLINE_DB_PATH

    airline = AirlineTools(FlightDB.load(AIRLINE_DB_PATH))
    print(airline.get_statistics())
