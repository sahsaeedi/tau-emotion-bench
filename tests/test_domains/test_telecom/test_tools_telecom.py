"""Tests for the telecom domain, ported from TRACER\'s environment.

These run against the real data/tau_emotion/domains/telecom/db.json and pin the
places where the toolkit deliberately follows TRACER's tool logic.
Each test gets its own freshly loaded db.
"""

import json

import pytest

from tau_emotion.domains.telecom.data_model import TelecomDB
from tau_emotion.domains.telecom.environment import get_environment
from tau_emotion.domains.telecom.tools import TelecomTools
from tau_emotion.domains.telecom.utils import TELECOM_DB_PATH

# Known-good records from the shipped db.json.
CUSTOMER_ID = "alex_allen_3726"
TICKET_ID = "TICKET00001"

EXPECTED_TOOLS = {
    "add_device",
    "calculate",
    "create_support_ticket",
    "find_customer_by_email",
    "find_customer_by_phone",
    "get_billing_details",
    "get_customer_details",
    "get_device_details",
    "get_senior_discount",
    "get_service_details",
    "get_services",
    "get_support_ticket_details",
    "manage_billing",
    "manage_service",
    "modify_support_ticket",
    "record_payment",
    "think",
    "transfer_to_human_agents",
    "troubleshoot_device",
}


@pytest.fixture
def db() -> TelecomDB:
    return TelecomDB.load(TELECOM_DB_PATH)


@pytest.fixture
def tools(db: TelecomDB) -> TelecomTools:
    return TelecomTools(db)


def test_environment_exposes_tracer_tools():
    assert set(get_environment().tools.get_tools()) == EXPECTED_TOOLS


def test_manage_billing_writes_billing_record_only(tools: TelecomTools):
    prefs_before = tools.db.customers[CUSTOMER_ID].billing_preferences.model_dump()

    result = json.loads(
        tools.manage_billing(
            CUSTOMER_ID, paperless=False, auto_pay=True, billing_cycle="quarterly"
        )
    )

    billing = tools.db.billing[CUSTOMER_ID]
    assert (billing.paperless, billing.auto_pay, billing.billing_cycle) == (
        False,
        True,
        "quarterly",
    )
    assert result["customer_id"] == CUSTOMER_ID
    assert result["billing"]["billing_cycle"] == "quarterly"
    assert (
        tools.db.customers[CUSTOMER_ID].billing_preferences.model_dump() == prefs_before
    )
    with pytest.raises(ValueError, match="Invalid billing cycle"):
        tools.manage_billing(
            CUSTOMER_ID, paperless=False, auto_pay=True, billing_cycle="weekly"
        )


def test_modify_support_ticket_accepts_only_listed_values(tools: TelecomTools):
    tools.modify_support_ticket(TICKET_ID, status="pending", priority="urgent")
    ticket = tools.db.support_tickets[TICKET_ID]
    assert (ticket.status, ticket.priority) == ("pending", "urgent")
    with pytest.raises(ValueError, match="Invalid priority"):
        tools.modify_support_ticket(TICKET_ID, status="pending", priority="whenever")
    with pytest.raises(ValueError, match="Invalid status"):
        tools.modify_support_ticket(TICKET_ID, status="Closed", priority="low")


def test_record_payment_returns_tracer_summary(tools: TelecomTools):
    balance = tools.db.billing[CUSTOMER_ID].current_balance

    result = json.loads(
        tools.record_payment(CUSTOMER_ID, 10, "credit_card", "2025-09-18")
    )

    expected_balance = max(round(balance - 10, 2), 0.0)
    assert result == {
        "customer_id": CUSTOMER_ID,
        "amount": "10.00",
        "method": "credit_card",
        "date": "2025-09-18",
        "current_balance": f"{expected_balance:.2f}",
    }
    assert tools.db.billing[CUSTOMER_ID].payment_history[-1].amount == 10


def test_manage_service_add_keeps_devices_attached_before_a_bad_id(tools: TelecomTools):
    customer = tools.db.customers[CUSTOMER_ID]
    service_id = next(s for s in tools.db.services if s not in customer.services)

    with pytest.raises(ValueError, match="Device not found: 99"):
        tools.manage_service(CUSTOMER_ID, "add", service_id, devices_ids=["1", "99"])

    assert customer.devices[0].service == service_id
    assert service_id not in customer.services


def test_troubleshoot_device_follows_tracer(tools: TelecomTools):
    assert tools.troubleshoot_device("iPhone 13", "no_service").startswith(
        "\nTroubleshooting steps: \n1) Restart device \n"
    )
    assert (
        tools.troubleshoot_device("WiFi 6 Router", "battery_drain") == "Unknown issue"
    )
    with pytest.raises(ValueError, match="not a valid Issue"):
        tools.troubleshoot_device("No Such Device", "overheating")
    with pytest.raises(ValueError, match="No troubleshooting steps"):
        tools.troubleshoot_device("HD Cable Box", "slow_speeds")


def test_details_return_the_raw_record(tools: TelecomTools):
    """Reads return the stored record as-is: no invented fields, none dropped."""
    raw = json.loads(TELECOM_DB_PATH.read_text())
    assert (
        json.loads(tools.get_support_ticket_details(TICKET_ID))
        == (raw["support_tickets"][TICKET_ID])
    )
    assert (
        json.loads(tools.get_customer_details(CUSTOMER_ID))
        == raw["customers"][CUSTOMER_ID]
    )
    assert (
        json.loads(tools.get_billing_details(CUSTOMER_ID))
        == raw["billing"][CUSTOMER_ID]
    )
    # manage_billing adds it; it is not in the seed data.
    assert "billing_cycle" not in raw["billing"][CUSTOMER_ID]
