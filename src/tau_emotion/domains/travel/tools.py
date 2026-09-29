"""Toolkit for the travel domain, ported from TRACER's environment
(tracer/tracer/envs/travel/).

15 tools mirroring TRACER's `ALL_TOOLS`. Conversion rules from TRACER's tools:

- `data["packages"]` → `self.db.packages`.
- `return json.dumps(x)` → return the pydantic record.
- `return "Error: ..."` → `raise ValueError("...")`.
- Free-function `invoke(data, ...)` → instance method with `@is_tool(...)`.

Bookings live inside travelers rather than in their own collection, so
`_find_booking` scans travelers, exactly as TRACER's tools do.

New booking ids are the first free `BKG000001`-style id, matching TRACER. Test
tasks can reference ids created earlier in the same task, so the format must
match TRACER's exactly.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from tau_emotion.domains.travel.data_model import (
    AddOn,
    Agent,
    Booking,
    Departure,
    Package,
    Payment,
    Person,
    Place,
    Rooming,
    TravelDB,
    Traveler,
)
from tau_emotion.environment.toolkit import ToolKitBase, ToolType, is_tool

# Insurance is priced per traveller.
INSURANCE_PRICES = {"standard": 50.0, "premium": 100.0}
# TRACER keeps this static so behaviour stays deterministic across runs.
BOOKING_DATE = "2024-05-15"


def _normalize_rooming(rooming: dict) -> dict:
    """ "family suite" -> "family_suite": the stored label must not depend on spacing/case."""
    if isinstance(rooming, dict) and isinstance(rooming.get("room_type"), str):
        room_type = "_".join(rooming["room_type"].strip().lower().split())
        rooming = {**rooming, "room_type": room_type}
    return rooming


class TravelTools(ToolKitBase):
    """All the tools for the travel domain."""

    db: TravelDB

    def __init__(self, db: TravelDB) -> None:
        super().__init__(db)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_traveler(self, traveler_id: str) -> Traveler:
        traveler = self.db.travelers.get(traveler_id)
        if traveler is None:
            raise ValueError("Traveler not found")
        return traveler

    def _get_package(self, package_id: str) -> Package:
        package = self.db.packages.get(package_id)
        if package is None:
            raise ValueError("Package not found")
        return package

    def _get_agent(self, agent_id: str) -> Agent:
        agent = self.db.agents.get(agent_id)
        if agent is None:
            raise ValueError("Agent not found")
        return agent

    def _find_booking(self, booking_id: str) -> Tuple[Traveler, Booking]:
        """Locate a booking and its owning traveler.

        Raises:
            ValueError: If no traveler holds a booking with that id.
        """
        for traveler in self.db.travelers.values():
            for booking in traveler.bookings:
                if booking.booking_id == booking_id:
                    return traveler, booking
        raise ValueError("Booking not found")

    def _booking_package(self, booking: Booking) -> Package:
        package = self.db.packages.get(booking.package_id)
        if package is None:
            raise ValueError("Package not found for this booking")
        return package

    def _new_booking_id(self) -> str:
        """First free id of the form BKG000001, as TRACER assigns it."""
        existing = {
            b.booking_id for t in self.db.travelers.values() for b in t.bookings
        }
        n = 1
        while f"BKG{n:06d}" in existing:
            n += 1
        return f"BKG{n:06d}"

    @staticmethod
    def _validate_departure(
        package: Package, departure_date: str, required_slots: int
    ) -> Departure:
        """Check a package runs on a date with room for `required_slots`.

        Raises:
            ValueError: If the date is not offered, is not available, or is full.
        """
        departure = package.departures.get(departure_date)
        if departure is None:
            raise ValueError(
                f"Package {package.package_id} not offered on {departure_date}"
            )
        if departure.status != "available":
            raise ValueError(
                f"Departure on {departure_date} for package "
                f"{package.package_id} is not available"
            )
        if departure.available_slots < required_slots:
            raise ValueError(
                f"Not enough slots on {departure_date}. Needed {required_slots}, "
                f"available {departure.available_slots}"
            )
        return departure

    @staticmethod
    def _calc_total_price(
        base_price_per_person: float,
        num_travelers: int,
        add_ons: List[dict] | List[AddOn],
        insurance: Optional[str],
    ) -> float:
        """Package price per head, plus add-ons, plus per-head insurance."""
        total = base_price_per_person * num_travelers
        for addon in add_ons:
            total += addon["price"] if isinstance(addon, dict) else addon.price
        if insurance:
            total += (
                INSURANCE_PRICES.get(insurance.strip().lower(), 0.0) * num_travelers
            )
        return round(total, 2)

    @staticmethod
    def _validate_payments(
        traveler: Traveler, payments: List[dict], expected_total: float
    ) -> None:
        """Check every payment uses a saved method and they sum to the total.

        Raises:
            ValueError: If a method is unknown or the amounts do not add up.
        """
        for payment in payments:
            if payment["payment_id"] not in traveler.payment_methods:
                raise ValueError(
                    f"Payment method {payment['payment_id']} not found for traveler"
                )
        paid = round(sum(p["amount"] for p in payments), 2)
        if round(expected_total, 2) != paid:
            raise ValueError(
                f"Payment amount does not add up, total price is "
                f"{expected_total}, but paid {paid}"
            )

    def _require_payment_method(
        self, traveler: Traveler, payment_method_id: str
    ) -> None:
        if payment_method_id not in traveler.payment_methods:
            raise ValueError("Payment method not found for traveler")

    # ------------------------------------------------------------------
    # Read tools
    # ------------------------------------------------------------------

    @is_tool(ToolType.READ)
    def get_traveler_details(self, traveler_id: str) -> Traveler:
        """
        Get the details of a traveler, including their profile and bookings.

        Args:
            traveler_id: The traveler id.

        Returns:
            The traveler record.

        Raises:
            ValueError: If the traveler is not found.
        """
        return self._get_traveler(traveler_id)

    @is_tool(ToolType.READ)
    def get_package_details(self, package_id: str) -> Package:
        """
        Get the details of a travel package.

        Args:
            package_id: The package id.

        Returns:
            The package record, including its itinerary and dated departures.

        Raises:
            ValueError: If the package is not found.
        """
        return self._get_package(package_id)

    @is_tool(ToolType.READ)
    def get_agent_details(self, agent_id: str) -> Agent:
        """
        Get the details of a travel agent.

        Args:
            agent_id: The agent id.

        Returns:
            The agent record, including their availability.

        Raises:
            ValueError: If the agent is not found.
        """
        return self._get_agent(agent_id)

    @is_tool(ToolType.READ)
    def get_booking_details(self, booking_id: str) -> Booking:
        """
        Get the details of a booking.

        Args:
            booking_id: The booking id.

        Returns:
            The booking record.

        Raises:
            ValueError: If the booking is not found.
        """
        _, booking = self._find_booking(booking_id)
        return booking

    @is_tool(ToolType.READ)
    def list_all_destinations(self) -> List[Place]:
        """
        List every distinct destination covered by the available packages.

        Returns:
            The list of unique city/country destinations, in the order first seen.
        """
        seen: set[tuple[str, str]] = set()
        destinations: List[Place] = []
        for package in self.db.packages.values():
            for place in package.destinations:
                key = (place.city, place.country)
                if key not in seen:
                    seen.add(key)
                    destinations.append(place)
        return destinations

    @is_tool(ToolType.READ)
    def search_packages(
        self,
        destination_city: Optional[str] = None,
        destination_country: Optional[str] = None,
        category: Optional[str] = None,
        departure_date: Optional[str] = None,
    ) -> List[Package]:
        """
        Search packages by destination, category and departure date.

        Only packages with at least one available departure that still has
        slots are returned.

        Args:
            destination_city: Optional destination city to filter by.
            destination_country: Optional destination country to filter by.
            category: Optional package category to filter by.
            departure_date: Optional departure date the package must offer.

        Returns:
            The matching packages.
        """
        results: List[Package] = []
        for package in self.db.packages.values():
            if destination_city or destination_country:
                if not any(
                    (destination_city is None or place.city == destination_city)
                    and (
                        destination_country is None
                        or place.country == destination_country
                    )
                    for place in package.destinations
                ):
                    continue
            if category and package.category != category:
                continue
            if departure_date and departure_date not in package.departures:
                continue
            if any(
                d.status == "available" and d.available_slots > 0
                for d in package.departures.values()
            ):
                results.append(package)
        return results

    # ------------------------------------------------------------------
    # Write tools
    # ------------------------------------------------------------------

    @is_tool(ToolType.WRITE)
    def book_package(
        self,
        traveler_id: str,
        package_id: str,
        departure_date: str,
        travelers: List[dict],
        rooming: dict,
        add_ons: List[dict],
        insurance: Optional[str],
        payment_methods: List[dict],
        agent_id: Optional[str] = None,
    ) -> Booking:
        """
        Book a package for a traveler on a given departure date.

        Validates the departure has enough slots, prices the booking, and checks
        the payments cover it exactly. The agent needs to list the booking
        details and obtain explicit user confirmation (yes/no) before calling.

        Args:
            traveler_id: The id of the traveler making the booking.
            package_id: The package to book.
            departure_date: The departure date, which the package must offer.
            travelers: The people travelling, each {first_name, last_name, dob}.
            rooming: Rooming choice, {room_type, occupancy}.
            add_ons: Optional extras, each {type, description, price}.
            insurance: Insurance level, 'standard' or 'premium', or None.
            payment_methods: Payments covering the total, each {payment_id, amount}.
            agent_id: Optional managing agent. Defaults to the package's first
                managing agent.

        Returns:
            The newly created booking.

        Raises:
            ValueError: If the traveler, package or agent is not found, the
                package has no managing agent, the departure is unavailable or
                full, or the payments do not match the total price.
        """
        # The schema says "null for none"; the string "null"/"none" means no insurance too.
        if isinstance(insurance, str) and insurance.strip().lower() in (
            "null",
            "none",
            "",
        ):
            insurance = None
        traveler = self._get_traveler(traveler_id)
        package = self._get_package(package_id)

        if agent_id is None:
            if not package.managed_by_agents:
                raise ValueError("No managing agent available for this package")
            agent_id = package.managed_by_agents[0]
        agent = self._get_agent(agent_id)

        num_travelers = len(travelers)
        departure = self._validate_departure(
            package, departure_date, required_slots=num_travelers
        )
        total_price = self._calc_total_price(
            base_price_per_person=departure.base_price,
            num_travelers=num_travelers,
            add_ons=add_ons,
            insurance=insurance,
        )
        self._validate_payments(traveler, payment_methods, total_price)

        booking_id = self._new_booking_id()
        booking = Booking(
            booking_id=booking_id,
            package_id=package_id,
            agent_id=agent_id,
            booking_date=BOOKING_DATE,
            departure_date=departure_date,
            status="confirmed",
            travelers=[Person.model_validate(t) for t in travelers],
            rooming=Rooming.model_validate(_normalize_rooming(rooming)),
            add_ons=[AddOn.model_validate(a) for a in add_ons],
            insurance=insurance,
            payment_history=[Payment.model_validate(p) for p in payment_methods],
            total_price=total_price,
            notes=None,
        )

        traveler.bookings.append(booking)
        departure.available_slots -= num_travelers
        if traveler_id not in agent.assigned_travelers:
            agent.assigned_travelers.append(traveler_id)
        if booking_id not in agent.bookings_handled:
            agent.bookings_handled.append(booking_id)
        return booking

    @is_tool(ToolType.WRITE)
    def cancel_booking(self, booking_id: str) -> Booking:
        """
        Cancel a booking, refunding every recorded payment and releasing its slots.

        The agent needs to present the cancellation effects and obtain explicit
        user confirmation (yes/no) before calling.

        Args:
            booking_id: The booking id to cancel.

        Returns:
            The cancelled booking.

        Raises:
            ValueError: If the booking or its package is not found.
        """
        _, booking = self._find_booking(booking_id)
        package = self._booking_package(booking)

        refunds = [
            Payment(payment_id=p.payment_id, amount=-p.amount)
            for p in booking.payment_history
        ]
        booking.payment_history.extend(refunds)
        booking.status = "cancelled"

        departure = package.departures.get(booking.departure_date)
        if departure is not None:
            departure.available_slots += len(booking.travelers)
        return booking

    @is_tool(ToolType.WRITE)
    def update_booking_travelers(
        self, booking_id: str, travelers: List[dict]
    ) -> Booking:
        """
        Replace the people travelling on a booking.

        The number of travellers cannot change, since that would reprice the
        booking and alter the slots held. The agent needs to list the change and
        obtain explicit user confirmation (yes/no) before calling.

        Args:
            booking_id: The booking id.
            travelers: The full replacement list, each {first_name, last_name, dob}.

        Returns:
            The updated booking.

        Raises:
            ValueError: If the booking is not found, or the number of travellers
                does not match the booking.
        """
        _, booking = self._find_booking(booking_id)
        if len(travelers) != len(booking.travelers):
            raise ValueError("Number of travelers does not match current booking")
        booking.travelers = [Person.model_validate(t) for t in travelers]
        return booking

    @is_tool(ToolType.WRITE)
    def update_booking_rooming(self, booking_id: str, rooming: dict) -> Booking:
        """
        Change the rooming choice on a booking.

        The agent needs to list the change and obtain explicit user confirmation
        (yes/no) before calling.

        Args:
            booking_id: The booking id.
            rooming: The new rooming, {room_type, occupancy}.

        Returns:
            The updated booking.

        Raises:
            ValueError: If the booking is not found.
        """
        _, booking = self._find_booking(booking_id)
        booking.rooming = Rooming.model_validate(_normalize_rooming(rooming))
        return booking

    @is_tool(ToolType.WRITE)
    def update_booking_add_ons(
        self, booking_id: str, add_ons: List[dict], payment_method_id: str
    ) -> Booking:
        """
        Replace the add-ons on a booking, charging or refunding the difference.

        The agent needs to list the change and the resulting price difference,
        and obtain explicit user confirmation (yes/no) before calling.

        Args:
            booking_id: The booking id.
            add_ons: The full replacement list, each {type, description, price}.
            payment_method_id: A saved payment method to settle the difference.

        Returns:
            The updated booking.

        Raises:
            ValueError: If the booking or its package is not found, the payment
                method is unknown, or the booking's departure is no longer available.
        """
        traveler, booking = self._find_booking(booking_id)
        package = self._booking_package(booking)
        self._require_payment_method(traveler, payment_method_id)

        departure = self._validate_departure(
            package, booking.departure_date, required_slots=0
        )
        new_total = self._calc_total_price(
            base_price_per_person=departure.base_price,
            num_travelers=len(booking.travelers),
            add_ons=add_ons,
            insurance=booking.insurance,
        )
        delta = round(new_total - booking.total_price, 2)
        if delta != 0:
            booking.payment_history.append(
                Payment(payment_id=payment_method_id, amount=delta)
            )

        booking.add_ons = [AddOn.model_validate(a) for a in add_ons]
        booking.total_price = new_total
        return booking

    @is_tool(ToolType.WRITE)
    def update_booking_departure_date(
        self, booking_id: str, new_departure_date: str, payment_method_id: str
    ) -> Booking:
        """
        Move a booking to a different departure date, repricing it.

        Slots are released on the old date and taken on the new one, and any
        price difference is charged or refunded. The agent needs to list the
        change and obtain explicit user confirmation (yes/no) before calling.

        Args:
            booking_id: The booking id.
            new_departure_date: The new departure date, which the package must offer.
            payment_method_id: A saved payment method to settle the difference.

        Returns:
            The updated booking.

        Raises:
            ValueError: If the booking or its package is not found, the payment
                method is unknown, or the new departure is unavailable or full.
        """
        traveler, booking = self._find_booking(booking_id)
        package = self._booking_package(booking)
        self._require_payment_method(traveler, payment_method_id)

        num_travelers = len(booking.travelers)
        new_departure = self._validate_departure(
            package, new_departure_date, required_slots=num_travelers
        )
        new_total = self._calc_total_price(
            base_price_per_person=new_departure.base_price,
            num_travelers=num_travelers,
            add_ons=booking.add_ons,
            insurance=booking.insurance,
        )
        delta = round(new_total - booking.total_price, 2)

        old_departure = package.departures.get(booking.departure_date)
        if old_departure is not None:
            old_departure.available_slots += num_travelers
        new_departure.available_slots -= num_travelers

        if delta != 0:
            booking.payment_history.append(
                Payment(payment_id=payment_method_id, amount=delta)
            )
        booking.departure_date = new_departure_date
        booking.total_price = new_total
        return booking

    @is_tool(ToolType.WRITE)
    def schedule_agent_meeting(
        self, agent_id: str, date: str, time_range: str, traveler_id: str
    ) -> str:
        """
        Book one of an agent's free time slots for a traveler.

        The slot is removed from the agent's availability. The agent needs to
        confirm the date and time with the user before calling.

        Args:
            agent_id: The agent to meet.
            date: The meeting date, which must appear in the agent's availability.
            time_range: The slot to take, which must be free on that date.
            traveler_id: The traveler the meeting is for.

        Returns:
            A confirmation message.

        Raises:
            ValueError: If the agent or traveler is not found, the agent is not
                available on that date, or the slot is not free.
        """
        agent = self._get_agent(agent_id)
        self._get_traveler(traveler_id)

        availability = agent.availability.get(date)
        if availability is None:
            raise ValueError(f"Agent is not available on {date}")
        if time_range not in availability.slots:
            raise ValueError(f"Time slot {time_range} not available on {date}")

        availability.slots.remove(time_range)
        return f"Meeting scheduled with agent {agent_id} on {date} at {time_range}"

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @is_tool(ToolType.THINK)
    def think(self, thought: str) -> str:
        """Use the tool to think about something. It will not obtain new
        information or change the database, but just append the thought to
        the log. Use it when complex reasoning or some cache memory is needed.

        Args:
            thought: A thought to think about.

        Returns:
            An empty string.
        """
        return ""

    @is_tool(ToolType.GENERIC)
    def calculate(self, expression: str) -> str:
        """
        Calculate the result of a mathematical expression.

        Args:
            expression: The mathematical expression to calculate, such as '2 + 2'. The expression can contain numbers, operators (+, -, *, /), parentheses, and spaces.

        Returns:
            The result of the mathematical expression.

        Raises:
            ValueError: If the expression is invalid.
        """
        if not all(char in "0123456789+-*/(). " for char in expression):
            raise ValueError("Invalid characters in expression")
        return str(round(float(eval(expression, {"__builtins__": None}, {})), 2))

    @is_tool(ToolType.GENERIC)
    def transfer_to_human_agents(self, summary: str) -> str:
        """
        Transfer the user to a human agent, with a summary of the user's issue.
        Only transfer if
         -  the user explicitly asks for a human agent
         -  given the policy and the available tools, you cannot solve the user's issue.

        Args:
            summary: A summary of the user's issue.

        Returns:
            A message indicating the user has been transferred to a human agent.
        """
        return "Transfer successful"
