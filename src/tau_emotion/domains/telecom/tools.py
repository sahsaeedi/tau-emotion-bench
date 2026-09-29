"""Toolkit for the telecom domain (account-management CRM ported from v1).

The 18 tools below mirror v1 tau-emotion-bench's telecom `ALL_TOOLS`, including
its validation rules and return values. Conversion rules from v1:

- v1 `data.get("customers", {})` → `self.db.customers` (typed pydantic).
- v1 `return json.dumps(record)` → `_record_json(record)`, which leaves out
  fields the record never had, as v1's raw dict would.
- v1 `return "Error: ..."` → `raise ValueError("...")`. Both frameworks show
  any exception to the agent as "Error: <message>".
- v1 free-function `invoke(data, ...)` → instance method with `@is_tool(...)`.
"""

import json
from typing import List, Optional

from pydantic import BaseModel

from tau_emotion.domains.telecom.data_model import (
    Billing,
    Customer,
    CustomerDevice,
    LastPayment,
    PaymentRecord,
    SupportTicket,
    TelecomDB,
)
from tau_emotion.environment.toolkit import ToolKitBase, ToolType, is_tool

# Lists, not sets: v1's error messages print them in this order.
VALID_TICKET_CATEGORIES = [
    "mobile",
    "internet",
    "tv",
    "billing",
    "account",
    "device",
    "security",
    "phone",
]
VALID_TICKET_PRIORITIES = ["low", "medium", "high", "urgent"]
VALID_ISSUES = ["no_service", "slow_speeds", "battery_drain"]

# v1's troubleshooting text, verbatim (including its trailing spaces).
PHONE_STEPS = {
    "battery_drain": (
        "\nTroubleshooting steps: \n"
        "1) Restart device \n"
        "2) Check brightness settings and reduce if needed\n"
        "3) Close background apps\n"
        "4) Contact support if issue persists\n"
    ),
    "no_service": (
        "\nTroubleshooting steps: \n"
        "1) Restart device \n"
        "2) Check signal coverage \n"
        "3) Reset network settings \n"
        "4) Contact support if issue persists\n"
    ),
    "slow_speeds": (
        "\nTroubleshooting steps: \n"
        "1) Restart device \n"
        "2) Check data usage and plan limits\n"
        "3) Reset network settings \n"
        "4) Contact support if issue persists\n"
    ),
}
NETWORKING_STEPS = {
    "no_service": (
        "\nTroubleshooting steps: \n"
        "1) Restart router by unplugging for 30 seconds\n"
        "2) Check all cable connections \n"
        "3) Update firmware if available\n"
        "4) Contact support if needed\n"
    ),
    "slow_speeds": (
        "\nTroubleshooting steps: \n"
        "1) Restart router by unplugging for 30 seconds\n"
        "2) Check cable connections \n"
        "3) Run speed test \n"
        "4) Contact support if needed\n"
    ),
}
TV_NO_SERVICE_STEPS = (
    "\nTroubleshooting steps: \n"
    "1) Check correct input/source \n"
    "2) Verify cable connections \n"
    "3) Restart cable box \n"
    "4) Contact support if needed\n"
)


def _record_dict(record: BaseModel) -> dict:
    return record.model_dump(exclude_unset=True)


def _record_json(record: BaseModel) -> str:
    return json.dumps(_record_dict(record))


class TelecomTools(ToolKitBase):
    """All telecom domain tools."""

    db: TelecomDB

    def __init__(self, db: TelecomDB) -> None:
        super().__init__(db)

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def _get_customer(self, customer_id: str) -> Customer:
        if customer_id not in self.db.customers:
            raise ValueError(f"Customer not found: {customer_id}")
        return self.db.customers[customer_id]

    def _get_billing(self, customer_id: str) -> Billing:
        if customer_id not in self.db.billing:
            raise ValueError(
                f"No billing information found for customer: {customer_id}"
            )
        return self.db.billing[customer_id]

    # ------------------------------------------------------------------
    # READ tools
    # ------------------------------------------------------------------

    @is_tool(ToolType.READ)
    def find_customer_by_email(self, email: str) -> str:
        """Find a customer by their email address.

        Args:
            email: The customer's email address, such as 'john.smith@email.com'.

        Returns:
            The matching customer id.

        Raises:
            ValueError: If no customer matches the email.
        """
        target = email.lower()
        for customer_id, customer in self.db.customers.items():
            if customer.demographics.email.lower() == target:
                return customer_id
        raise ValueError(f"No customer found with email address: {email}")

    @is_tool(ToolType.READ)
    def find_customer_by_phone(self, phone: str) -> str:
        """Find a customer by their phone number.

        Args:
            phone: The customer's phone number, such as '(555) 123-4567'.

        Returns:
            The matching customer id.

        Raises:
            ValueError: If no customer matches the phone number.
        """
        target = "".join(ch for ch in phone if ch.isdigit())
        for customer_id, customer in self.db.customers.items():
            normalized = "".join(ch for ch in customer.demographics.phone if ch.isdigit())
            if normalized == target:
                return customer_id
        raise ValueError(f"No customer found with phone number: {phone}")

    @is_tool(ToolType.READ)
    def get_customer_details(self, customer_id: str) -> str:
        """Get detailed information about a customer, including their account,
        services, and devices.

        Args:
            customer_id: The customer's unique identifier, such as
                'first_last_1234'.

        Returns:
            The customer record as JSON.

        Raises:
            ValueError: If the customer is not found.
        """
        return _record_json(self._get_customer(customer_id))

    @is_tool(ToolType.READ)
    def get_billing_details(self, customer_id: str) -> str:
        """Get billing information for a customer, including current balance,
        payment history, and monthly charges.

        Args:
            customer_id: The customer's unique identifier, such as
                'john_smith_1234'.

        Returns:
            The customer's billing record as JSON.

        Raises:
            ValueError: If no billing record exists for the customer.
        """
        return _record_json(self._get_billing(customer_id))

    @is_tool(ToolType.READ)
    def get_service_details(self, service_id: str) -> str:
        """Get detailed information about a telecom service.

        Args:
            service_id: The service identifier, such as 'mobile_unlimited' or
                'internet_fiber_1gb'.

        Returns:
            The service record as JSON.

        Raises:
            ValueError: If the service is not found.
        """
        if service_id not in self.db.services:
            raise ValueError(f"Service not found: {service_id}")
        return _record_json(self.db.services[service_id])

    @is_tool(ToolType.READ)
    def get_services(self) -> str:
        """Get detailed information about all telecom services.

        Returns:
            A JSON object mapping each service id to its record.
        """
        return json.dumps({sid: _record_dict(s) for sid, s in self.db.services.items()})

    @is_tool(ToolType.READ)
    def get_device_details(self, device_name: str) -> str:
        """Get detailed information about a device on the market

        Args:
            device_name: The name of the device to get details about. Options:
                iPhone 15 Pro, iPhone 14, iPhone 13, Samsung Galaxy S23,
                iPhone 12, iPhone 15, Google Pixel 8, Samsung Galaxy A54,
                iPhone SE (3rd gen), WiFi 6 Router, Standard WiFi Router,
                Enterprise Router, Basic WiFi Router, Samsung 65" Smart TV,
                HD Cable Box, 55" Smart TV, Conference Room TV,
                Conference Phone System, Home Security System.

        Returns:
            The device catalog entry as JSON.

        Raises:
            ValueError: If the device name is not in the catalog.
        """
        if device_name not in self.db.devices:
            raise ValueError(f"Device not found: {device_name}")
        return _record_json(self.db.devices[device_name])

    @is_tool(ToolType.READ)
    def get_support_ticket_details(self, ticket_id: str) -> str:
        """Get details of a support ticket.

        Args:
            ticket_id: The support ticket identifier, such as 'TICKET001'.

        Returns:
            The support ticket record as JSON.

        Raises:
            ValueError: If the ticket is not found.
        """
        if ticket_id not in self.db.support_tickets:
            raise ValueError(f"Support ticket not found: {ticket_id}")
        return _record_json(self.db.support_tickets[ticket_id])

    @is_tool(ToolType.READ)
    def troubleshoot_device(self, device_name: str, issue: str) -> str:
        """Provide troubleshooting steps for device issues.

        Args:
            device_name: The device name, such as 'iPhone 15 Pro' or
                'WiFi 6 Router'.
            issue: Description of the issue with the device. Options:
                no_service, slow_speeds, battery_drain.

        Returns:
            Troubleshooting steps, or 'Unknown issue' if the device category
            has none for this issue.

        Raises:
            ValueError: If the issue is not one of the options, the device is
                not in the catalog, or a TV issue other than no_service is
                given.
        """
        # v1 parses the issue before looking up the device.
        if issue not in VALID_ISSUES:
            raise ValueError(f"'{issue}' is not a valid Issue")
        if device_name not in self.db.devices:
            raise ValueError(f"Device not found: {device_name}")
        category = self.db.devices[device_name].category

        if category in ("mobile_phone", "phone"):
            return PHONE_STEPS[issue]
        if category == "networking":
            return NETWORKING_STEPS.get(issue, "Unknown issue")
        if category == "tv":
            if issue == "no_service":
                return TV_NO_SERVICE_STEPS
            # v1 compares against a missing Issue.NO_SIGNAL enum member here,
            # which raises for every other issue.
            raise ValueError("type object 'Issue' has no attribute 'NO_SIGNAL'")
        return "Unknown issue"

    # ------------------------------------------------------------------
    # WRITE tools
    # ------------------------------------------------------------------

    @is_tool(ToolType.WRITE)
    def add_device(self, customer_id: str, device_name: str) -> str:
        """Add a device to a customer.

        Args:
            customer_id: The customer's unique identifier, such as
                'john_smith_1234'.
            device_name: The name of the device to add. Options: iPhone 15 Pro,
                iPhone 14, iPhone 13, Samsung Galaxy S23, iPhone 12, iPhone 15,
                Google Pixel 8, Samsung Galaxy A54, iPhone SE (3rd gen),
                WiFi 6 Router, Standard WiFi Router, Enterprise Router,
                Basic WiFi Router, Samsung 65" Smart TV, HD Cable Box,
                55" Smart TV, Conference Room TV, Conference Phone System,
                Home Security System.

        Returns:
            A success message.

        Raises:
            ValueError: If the customer or device name is invalid.
        """
        customer = self._get_customer(customer_id)
        if device_name not in self.db.devices:
            raise ValueError(f"Invalid device name: {device_name}")

        new_device = CustomerDevice(
            device_id=str(len(customer.devices) + 1),
            name=device_name,
            service=None,
        )
        customer.devices.append(new_device)
        return f"Success: Added device '{device_name}' to customer {customer_id}"

    @is_tool(ToolType.WRITE)
    def manage_service(
        self,
        customer_id: str,
        action: str,
        service_id: Optional[str] = None,
        devices_ids: Optional[List[str]] = None,
    ) -> str:
        """Manage customer services: add, remove, suspend, activate, or list services.

        Args:
            customer_id: The customer's unique identifier, such as
                'john_smith_1234'.
            action: Action to perform: 'add', 'remove', or 'list'.
            service_id: Service identifier (required for
                add/remove/suspend/activate), such as 'mobile_unlimited'.
            devices_ids: The device ids. Should be a list of strings
                corresponding to the device ids in the customer's list of
                devices.

        Returns:
            For 'list', a JSON object with the customer's services. For
            'add'/'remove', a success message.

        Raises:
            ValueError: On invalid action, unknown service or device, or a
                service the customer already has (add) or lacks (remove).
        """
        customer = self._get_customer(customer_id)

        if action == "list":
            attached = [
                _record_dict(self.db.services[sid])
                for sid in customer.services
                if sid in self.db.services
            ]
            return json.dumps({"customer_id": customer_id, "services": attached})

        if not service_id:
            raise ValueError(f"Service ID is required for action: {action}")

        if action == "add":
            if service_id not in self.db.services:
                raise ValueError(f"Service not found: {service_id}")
            if service_id in customer.services:
                raise ValueError(
                    f"Customer {customer_id} already has service: {service_id}"
                )

            # Like v1, each device is checked and attached in turn, so devices
            # before an unknown id stay attached when the call fails.
            for did in devices_ids or []:
                device = next(
                    (d for d in customer.devices if d.device_id == did), None
                )
                if device is None:
                    raise ValueError(
                        f"Device not found: {did} in devices "
                        f"{[_record_dict(d) for d in customer.devices]}"
                    )
                device.service = service_id

            customer.services.append(service_id)
            service = self.db.services[service_id]
            billing = self.db.billing.get(customer_id)
            if billing is not None:
                billing.monthly_charges[service_id] = service.price
            return f"Success: Added service '{service.name}' to customer {customer_id}"

        if action == "remove":
            if service_id not in customer.services:
                raise ValueError(
                    f"Customer {customer_id} does not have service: {service_id}"
                )
            removed_devices = []
            for device in customer.devices:
                if device.service == service_id:
                    device.service = None
                    removed_devices.append(device.name)
            customer.services.remove(service_id)
            service = self.db.services.get(service_id)
            service_name = service.name if service else service_id
            billing = self.db.billing.get(customer_id)
            if billing is not None:
                if service_id not in billing.monthly_charges:
                    # v1's dict.pop raises KeyError after the removal above.
                    raise ValueError(repr(service_id))
                billing.monthly_charges.pop(service_id)
            return (
                f"Success: Removed service '{service_name}' from customer "
                f"{customer_id}. Devices {removed_devices} are now no longer "
                f"associated with the service."
            )

        raise ValueError(
            f"Invalid action: {action}. Valid actions are: add, remove, list"
        )

    @is_tool(ToolType.WRITE)
    def manage_billing(
        self,
        customer_id: str,
        paperless: bool,
        auto_pay: bool,
        billing_cycle: str,
    ) -> str:
        """Manage customer billing: paperless, auto_pay, or billing_cycle.

        Args:
            customer_id: The customer's unique identifier, such as
                'john_smith_1234'.
            paperless: Paperless billing.
            auto_pay: Auto pay.
            billing_cycle: The billing cycle. Should be a string. Options are:
                monthly, quarterly, annual.

        Returns:
            A JSON object with the customer id and the updated billing record.

        Raises:
            ValueError: If the customer or their billing record is not found.
        """
        self._get_customer(customer_id)
        billing = self._get_billing(customer_id)
        # v1 writes these to the billing record only, not to the customer's
        # billing_preferences, and does not validate the cycle.
        billing.paperless = paperless
        billing.auto_pay = auto_pay
        billing.billing_cycle = billing_cycle
        return json.dumps({"customer_id": customer_id, "billing": _record_dict(billing)})

    @is_tool(ToolType.WRITE)
    def create_support_ticket(
        self, customer_id: str, category: str, priority: str = "medium"
    ) -> str:
        """Create a new support ticket for a customer.

        Args:
            customer_id: The customer's unique identifier, such as
                'john_smith_1234'.
            category: Ticket category: 'mobile', 'internet', 'tv', 'billing',
                'account', 'device', 'security', or 'phone'.
            priority: Priority level: 'low', 'medium', 'high', or 'urgent'.
                Defaults to 'medium'. Low is non-urgent, medium is standard,
                high is important, and urgent is critical (within 24 hours)

        Returns:
            A success message including the new ticket id.

        Raises:
            ValueError: On unknown customer or invalid category/priority.
        """
        self._get_customer(customer_id)
        if category not in VALID_TICKET_CATEGORIES:
            raise ValueError(
                f"Invalid category: {category}. Valid categories: "
                f"{', '.join(VALID_TICKET_CATEGORIES)}"
            )
        if priority not in VALID_TICKET_PRIORITIES:
            raise ValueError(
                f"Invalid priority: {priority}. Valid priorities: "
                f"{', '.join(VALID_TICKET_PRIORITIES)}"
            )
        ticket_id = f"TICKET{len(self.db.support_tickets) + 1:03d}"
        self.db.support_tickets[ticket_id] = SupportTicket(
            ticket_id=ticket_id,
            customer_id=customer_id,
            status="open",
            priority=priority,
            category=category,
        )
        return (
            f"Success: Created support ticket {ticket_id} for customer "
            f"{customer_id}"
        )

    @is_tool(ToolType.WRITE)
    def modify_support_ticket(
        self, ticket_id: str, status: str, priority: str
    ) -> str:
        """Modify the status and priority of a support ticket.

        Args:
            ticket_id: The support ticket identifier, such as 'TICKET001'.
            status: The status of the support ticket, such as 'open' or
                'closed'.
            priority: The priority of the support ticket, such as 'low',
                'medium', 'high', or 'urgent'.

        Returns:
            A success message.

        Raises:
            ValueError: If the ticket is not found.
        """
        if ticket_id not in self.db.support_tickets:
            raise ValueError(f"Support ticket not found: {ticket_id}")
        # v1 stores any status and priority without validating them.
        ticket = self.db.support_tickets[ticket_id]
        ticket.status = status
        ticket.priority = priority
        return (
            f"Success: Modified support ticket {ticket_id} with status "
            f"{status} and priority {priority}"
        )

    @is_tool(ToolType.WRITE)
    def record_payment(
        self, customer_id: str, amount: float, method: str, date: str
    ) -> str:
        """Apply a payment to a customer account and update the remaining balance.

        Args:
            customer_id: Unique customer identifier, e.g. 'lisa_chen_3456'.
            amount: Payment amount to apply.
            method: Payment method used. Options: credit_card, bank_transfer.
            date: Payment date in ISO format, e.g. '2025-09-18'.

        Returns:
            A JSON object with the applied payment and the new current balance.

        Raises:
            ValueError: If the billing record is missing or amount is invalid.
        """
        billing = self._get_billing(customer_id)
        try:
            amount_value = round(float(amount), 2)
        except (TypeError, ValueError) as e:
            raise ValueError("amount must be a number") from e

        new_balance = max(round(billing.current_balance - amount_value, 2), 0.0)
        billing.current_balance = new_balance
        billing.payment_history.append(
            PaymentRecord(date=date, amount=amount_value, status="completed")
        )
        billing.last_payment = LastPayment(
            amount=amount_value, date=date, method=method, status="completed"
        )
        return json.dumps(
            {
                "customer_id": customer_id,
                "amount": f"{amount_value:.2f}",
                "method": method,
                "date": date,
                "current_balance": f"{new_balance:.2f}",
            }
        )

    # ------------------------------------------------------------------
    # GENERIC tools (utility / pure compute)
    # ------------------------------------------------------------------

    @is_tool(ToolType.GENERIC)
    def calculate(self, expression: str) -> str:
        """Calculate the result of a mathematical expression.

        Args:
            expression: The mathematical expression to calculate, such as
                '2 + 2'. The expression can contain numbers, operators (+, -,
                *, /), parentheses, and spaces.

        Returns:
            The numeric result rounded to two decimals, as a string.

        Raises:
            ValueError: If the expression contains disallowed characters or
                cannot be evaluated.
        """
        allowed = "0123456789+-*/(). "
        if not all(ch in allowed for ch in expression):
            raise ValueError("invalid characters in expression")
        try:
            value = eval(expression, {"__builtins__": None}, {})  # noqa: S307
            return str(round(float(value), 2))
        except Exception as e:
            raise ValueError(str(e)) from e

    @is_tool(ToolType.GENERIC)
    def get_senior_discount(self, original_price: str) -> str:
        """Apply a fixed $5 senior discount to the provided service price.

        Args:
            original_price: Original price before applying the senior discount,
                e.g. '95.00'.

        Returns:
            The discounted price as a string with two decimals.

        Raises:
            ValueError: If `original_price` is not numeric.
        """
        try:
            price = float(original_price)
        except (TypeError, ValueError) as e:
            raise ValueError("original_price must be a number") from e
        return f"{max(price - 5.0, 0.0):.2f}"

    # ------------------------------------------------------------------
    # THINK tool
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
