"""Toolkit for the restaurant domain, ported from TRACER's environment
(tracer/tracer/envs/restaurant/).

15 tools: one per tool module in tracer/tracer/envs/restaurant/tools/.
Conversion rules from TRACER's tools:

- `data["service_tickets"]` → `self.db.service_tickets`.
- `return json.dumps(x)` → return the pydantic record.
- `return "Error: ..."` → `raise ValueError("...")`.
- Free-function `invoke(data, ...)` → instance method with `@is_tool(...)`.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from tau_emotion.domains.restaurant.data_model import (
    Charge,
    Dish,
    Location,
    Patron,
    RestaurantDB,
    SavedInstrument,
    Selection,
    ServiceTicket,
    TableInfo,
)
from tau_emotion.environment.toolkit import ToolKitBase, ToolType, is_tool

PLACED = "placed"
CANCELLED = "cancelled"


class RestaurantTools(ToolKitBase):
    """All the tools for the restaurant domain."""

    db: RestaurantDB

    def __init__(self, db: RestaurantDB) -> None:
        super().__init__(db)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_patron(self, guest_ref: str) -> Patron:
        patron = self.db.patron_registry.get(guest_ref)
        if patron is None:
            raise ValueError("Patron not found")
        return patron

    def _get_dish(self, dish_ref: str) -> Dish:
        dish = self.db.menu_board.get(dish_ref)
        if dish is None:
            raise ValueError("Dish not found")
        return dish

    def _get_ticket(self, ticket_ref: str) -> ServiceTicket:
        ticket = self.db.service_tickets.get(ticket_ref)
        if ticket is None:
            raise ValueError("Ticket not found")
        return ticket

    def _get_instrument(self, guest_ref: str, instrument_ref: str) -> SavedInstrument:
        patron = self.db.patron_registry.get(guest_ref)
        instrument = (
            patron.saved_instruments.get(instrument_ref) if patron is not None else None
        )
        if instrument is None:
            raise ValueError("Payment instrument not found")
        return instrument

    def _get_placed_ticket(self, ticket_ref: str) -> ServiceTicket:
        ticket = self._get_ticket(ticket_ref)
        if ticket.state != PLACED:
            raise ValueError("Non-placed ticket cannot be modified")
        return ticket

    def _find_dish_by_plate(self, plate_ref: str) -> Optional[Dish]:
        for dish in self.db.menu_board.values():
            if plate_ref in dish.selections:
                return dish
        return None

    # ------------------------------------------------------------------
    # Read tools
    # ------------------------------------------------------------------

    @is_tool(ToolType.READ)
    def get_patron_details(self, guest_ref: str) -> Patron:
        """
        Get the details of a patron, including their saved instruments and ticket history.

        Args:
            guest_ref: The patron reference, such as 'g7Hk2Qm'.

        Returns:
            The patron record.

        Raises:
            ValueError: If the patron is not found.
        """
        return self._get_patron(guest_ref)

    @is_tool(ToolType.READ)
    def find_patron_ref_by_email(self, email: str) -> str:
        """
        Find a patron reference by contact email.

        Args:
            email: The email of the patron, such as 'guest@example.com'.

        Returns:
            The matching guest_ref.

        Raises:
            ValueError: If no patron has that email.
        """
        for guest_ref, patron in self.db.patron_registry.items():
            if patron.contact_email.lower() == email.lower():
                return guest_ref
        raise ValueError("Patron not found")

    @is_tool(ToolType.READ)
    def find_patron_ref_by_name_zip(
        self, given: str, family: str, postal_code: str
    ) -> str:
        """
        Find a patron reference by name and postal code.

        Use when the email is unknown or not found.

        Args:
            given: The given (first) name, such as 'John'.
            family: The family (last) name, such as 'Doe'.
            postal_code: The postal code, such as '12345'.

        Returns:
            The matching guest_ref.

        Raises:
            ValueError: If no patron matches.
        """
        for guest_ref, patron in self.db.patron_registry.items():
            if (
                patron.identity.given.lower() == given.lower()
                and patron.identity.family.lower() == family.lower()
                and patron.location.postal_code == postal_code
            ):
                return guest_ref
        raise ValueError("Patron not found")

    @is_tool(ToolType.READ)
    def get_dish_details(self, dish_ref: str) -> Dish:
        """
        Get the menu details of a dish.

        Args:
            dish_ref: The dish reference, such as 'd2Wq8Nc'.

        Returns:
            The dish, including all of its orderable selections.

        Raises:
            ValueError: If the dish is not found.
        """
        return self._get_dish(dish_ref)

    @is_tool(ToolType.READ)
    def list_all_dishes(self) -> Dict[str, str]:
        """
        List the title and dish_ref of all dishes.

        Returns:
            A mapping of dish title to dish_ref, sorted alphabetically by title.
        """
        mapping = {dish.title: dish.dish_ref for dish in self.db.menu_board.values()}
        return dict(sorted(mapping.items()))

    @is_tool(ToolType.READ)
    def get_ticket_details(self, ticket_ref: str) -> ServiceTicket:
        """
        Get the current state and details of a service ticket.

        Args:
            ticket_ref: The ticket reference, such as 't4Rx9Lb'.

        Returns:
            The service ticket.

        Raises:
            ValueError: If the ticket is not found.
        """
        return self._get_ticket(ticket_ref)

    # ------------------------------------------------------------------
    # Write tools
    # ------------------------------------------------------------------

    @is_tool(ToolType.WRITE)
    def cancel_placed_ticket(self, ticket_ref: str, reason: str) -> ServiceTicket:
        """
        Cancel a placed ticket.

        If the ticket has already started preparation or is delivered, it cannot
        be cancelled. Upon cancellation, refund entries are recorded for any
        prior payments. The agent must explain the cancellation details and ask
        for explicit user confirmation (yes/no) to proceed.

        Args:
            ticket_ref: The ticket reference, such as 't4Rx9Lb'.
            reason: The reason for cancellation, e.g. 'no longer needed'.

        Returns:
            The cancelled ticket.

        Raises:
            ValueError: If the ticket is not found or is not in 'placed' state.
        """
        ticket = self._get_ticket(ticket_ref)
        if ticket.state != PLACED:
            raise ValueError("Only tickets in 'placed' state can be cancelled")

        refunds = [
            Charge(kind="refund", total=ch.total, instrument_ref=ch.instrument_ref)
            for ch in ticket.charges
            if ch.kind == "payment"
        ]
        ticket.charges.extend(refunds)
        ticket.state = CANCELLED
        return ticket

    @is_tool(ToolType.WRITE)
    def add_tip_to_ticket(
        self, ticket_ref: str, tip_total: float, instrument_ref: str
    ) -> ServiceTicket:
        """
        Add a tip to a ticket.

        A tip can be added as long as the ticket is not cancelled; it is charged
        to the specified instrument. The agent must explain the tip addition and
        ask for explicit user confirmation (yes/no) to proceed.

        Args:
            ticket_ref: The ticket reference, such as 't4Rx9Lb'.
            tip_total: The tip amount to add. Must be non-negative.
            instrument_ref: The instrument reference to charge the tip to.

        Returns:
            The updated ticket.

        Raises:
            ValueError: If the ticket is not found, is cancelled, the tip is
                negative, or the instrument is not saved for the patron.
        """
        ticket = self._get_ticket(ticket_ref)
        if ticket.state == CANCELLED:
            raise ValueError("Cannot add tip to a cancelled ticket")
        if tip_total < 0:
            raise ValueError("Tip amount must be non-negative")
        self._get_instrument(ticket.guest_ref, instrument_ref)

        ticket.charges.append(
            Charge(
                kind="tip",
                total=round(float(tip_total), 2),
                instrument_ref=instrument_ref,
            )
        )
        return ticket

    @is_tool(ToolType.WRITE)
    def modify_placed_ticket_table(
        self, ticket_ref: str, zone: str, table_no: str, seat_count: int
    ) -> ServiceTicket:
        """
        Modify the table information for a placed dine-in ticket.

        The agent must explain the update and ask for explicit user confirmation
        (yes/no) to proceed.

        Args:
            ticket_ref: The ticket reference, such as 't4Rx9Lb'.
            zone: Dining area or zone identifier.
            table_no: Table number.
            seat_count: Number of seats at the table.

        Returns:
            The updated ticket.

        Raises:
            ValueError: If the ticket is not found, is not in 'placed' state,
                or is not a dine-in ticket.
        """
        ticket = self._get_placed_ticket(ticket_ref)
        if ticket.service_mode != "dine_in":
            raise ValueError("Only dine-in tickets have table information")
        ticket.table_info = TableInfo(
            zone=zone, table_no=table_no, seat_count=seat_count
        )
        return ticket

    @is_tool(ToolType.WRITE)
    def modify_placed_ticket_dropoff(
        self,
        ticket_ref: str,
        line_one: str,
        line_two: str,
        municipality: str,
        province: str,
        nation: str,
        postal_code: str,
    ) -> ServiceTicket:
        """
        Modify the dropoff address of a placed delivery ticket.

        The agent must explain the update and ask for explicit user confirmation
        (yes/no) to proceed.

        Args:
            ticket_ref: The ticket reference, such as 't4Rx9Lb'.
            line_one: Primary address line.
            line_two: Secondary address line.
            municipality: City or municipality.
            province: State or province.
            nation: Country name.
            postal_code: Postal or ZIP code.

        Returns:
            The updated ticket.

        Raises:
            ValueError: If the ticket is not found, is not in 'placed' state,
                or is not a delivery ticket.
        """
        ticket = self._get_placed_ticket(ticket_ref)
        if ticket.service_mode != "delivery":
            raise ValueError("Only delivery tickets have a dropoff address")
        ticket.dropoff = Location(
            line_one=line_one,
            line_two=line_two,
            municipality=municipality,
            province=province,
            nation=nation,
            postal_code=postal_code,
        )
        return ticket

    @is_tool(ToolType.WRITE)
    def modify_placed_ticket_instrument(
        self, ticket_ref: str, instrument_ref: str
    ) -> ServiceTicket:
        """
        Modify the payment instrument on a placed ticket.

        Only tickets in 'placed' state are eligible, there must be exactly one
        'payment' charge on the ticket, and the new instrument must differ from
        the current one. The agent needs to explain the change and ask for
        explicit user confirmation (yes/no) to proceed.

        Args:
            ticket_ref: The ticket reference, such as 't4Rx9Lb'.
            instrument_ref: The new instrument reference to use for the payment.

        Returns:
            The updated ticket, with a payment on the new instrument and a
            refund to the old one.

        Raises:
            ValueError: If the ticket is not found or not placed, the instrument
                is unknown, there is not exactly one payment charge, or the new
                instrument matches the current one.
        """
        ticket = self._get_placed_ticket(ticket_ref)
        self._get_instrument(ticket.guest_ref, instrument_ref)

        payment_charges = [ch for ch in ticket.charges if ch.kind == "payment"]
        if len(payment_charges) != 1:
            raise ValueError(
                "There should be exactly one payment charge for a placed ticket"
            )
        current_payment = payment_charges[0]
        if current_payment.instrument_ref == instrument_ref:
            raise ValueError(
                "The new instrument should be different from the current one"
            )

        amount = current_payment.total
        ticket.charges.extend(
            [
                Charge(kind="payment", total=amount, instrument_ref=instrument_ref),
                Charge(
                    kind="refund",
                    total=amount,
                    instrument_ref=current_payment.instrument_ref,
                ),
            ]
        )
        return ticket

    @is_tool(ToolType.WRITE)
    def modify_placed_ticket_items(
        self,
        ticket_ref: str,
        plate_refs: List[str],
        new_plate_refs: List[str],
        instrument_ref: str,
    ) -> ServiceTicket:
        """
        Modify plate selections in a placed ticket to new selections of the same dish.

        Only tickets in 'placed' state can be modified. The agent needs to explain
        the modification and ask for explicit user confirmation (yes/no) to proceed.

        Args:
            ticket_ref: The ticket reference, such as 't4Rx9Lb'.
            plate_refs: The current plate_refs to be modified; duplicates allowed.
            new_plate_refs: The new plate_refs to replace with. Must match the
                positional count of plate_refs and be from the same dish.
            instrument_ref: The payment instrument to charge or refund the
                price difference.

        Returns:
            The updated ticket.

        Raises:
            ValueError: If the ticket is not found or not placed, the instrument
                is unknown, the plate lists do not line up, a plate is not on the
                ticket, a new plate is unknown, belongs to a different dish, or
                is not served today.
        """
        ticket = self._get_placed_ticket(ticket_ref)
        self._get_instrument(ticket.guest_ref, instrument_ref)

        ticket_plate_refs = [entry.plate_ref for entry in ticket.line_entries]
        for plate_ref in plate_refs:
            if plate_refs.count(plate_ref) > ticket_plate_refs.count(plate_ref):
                raise ValueError(
                    f"Plate {plate_ref} not found in the ticket the requested "
                    f"number of times"
                )
        if len(plate_refs) != len(new_plate_refs):
            raise ValueError("The number of plates to be modified should match")

        diff_total = 0.0
        consumed: Dict[str, int] = {}
        modifications: List[tuple[int, Selection]] = []

        for old_ref, new_ref in zip(plate_refs, new_plate_refs):
            occurrence = consumed.get(old_ref, 0)
            target_idx = self._nth_line_entry_index(ticket, old_ref, occurrence)
            if target_idx is None:
                raise ValueError(f"Plate {old_ref} not found")
            consumed[old_ref] = occurrence + 1

            old_dish = self._find_dish_by_plate(old_ref)
            new_dish = self._find_dish_by_plate(new_ref)
            if new_dish is None:
                raise ValueError(f"New plate {new_ref} not found")
            if old_dish is None or old_dish.dish_ref != new_dish.dish_ref:
                raise ValueError("New plate must be from the same dish as the original")

            new_plate = new_dish.selections[new_ref]
            if not new_plate.served_today:
                raise ValueError(f"New plate {new_ref} is not available today")

            diff_total += new_plate.cost - ticket.line_entries[target_idx].cost
            modifications.append((target_idx, new_plate))

        diff_total = round(diff_total, 2)
        if diff_total != 0:
            ticket.charges.append(
                Charge(
                    kind="payment" if diff_total > 0 else "refund",
                    total=abs(diff_total),
                    instrument_ref=instrument_ref,
                )
            )

        for idx, plate in modifications:
            ticket.line_entries[idx].plate_ref = plate.plate_ref
            ticket.line_entries[idx].cost = plate.cost
        return ticket

    @staticmethod
    def _nth_line_entry_index(
        ticket: ServiceTicket, plate_ref: str, occurrence: int
    ) -> Optional[int]:
        """Index of the nth line entry carrying plate_ref, or None."""
        seen = 0
        for idx, entry in enumerate(ticket.line_entries):
            if entry.plate_ref == plate_ref:
                if seen == occurrence:
                    return idx
                seen += 1
        return None

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
            raise ValueError("invalid characters in expression")
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
