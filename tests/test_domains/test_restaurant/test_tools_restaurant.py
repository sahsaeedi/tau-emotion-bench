"""Tests for the restaurant domain, ported from TRACER\'s environment.

These run against the real data/tau_emotion/domains/restaurant/db.json rather
than a synthetic fixture, so they also assert that the shipped data validates
against the pydantic models. Each test gets its own freshly loaded db.
"""

import pytest

from tau_emotion.domains.restaurant.data_model import RestaurantDB
from tau_emotion.domains.restaurant.environment import get_environment
from tau_emotion.domains.restaurant.tools import RestaurantTools
from tau_emotion.domains.restaurant.utils import RESTAURANT_DB_PATH

# Known-good records from the shipped db.json.
PATRON_REF = "vuwpEI8"
PATRON_EMAIL = "sofie.nielsen.678@example.com"
PATRON_GIVEN = "Sofie"
PATRON_FAMILY = "Nielsen"
PATRON_ZIP = "68000"

DINE_IN_TICKET = "0k2qeUi"
DELIVERY_TICKET = "17xQa4E"
SWAP_FROM_PLATE = "mn1mEsg"
SWAP_TO_PLATE = "TvCGrmk"
DELIVERY_INSTRUMENT = "7Qck7AI"

EXPECTED_TOOLS = {
    "add_tip_to_ticket",
    "calculate",
    "cancel_placed_ticket",
    "find_patron_ref_by_email",
    "find_patron_ref_by_name_zip",
    "get_dish_details",
    "get_patron_details",
    "get_ticket_details",
    "list_all_dishes",
    "modify_placed_ticket_dropoff",
    "modify_placed_ticket_instrument",
    "modify_placed_ticket_items",
    "modify_placed_ticket_table",
    "think",
    "transfer_to_human_agents",
}


@pytest.fixture
def db() -> RestaurantDB:
    return RestaurantDB.load(RESTAURANT_DB_PATH)


@pytest.fixture
def tools(db: RestaurantDB) -> RestaurantTools:
    return RestaurantTools(db)


def test_shipped_db_validates(db: RestaurantDB):
    stats = db.get_statistics()
    assert stats["num_dishes"] > 0
    assert stats["num_patrons"] > 0
    assert stats["num_service_tickets"] > 0


def test_environment_exposes_expected_tools():
    env = get_environment()
    assert set(env.tools.get_tools()) == EXPECTED_TOOLS
    assert env.domain_name == "restaurant"
    assert env.policy.strip()


def test_every_tool_has_a_valid_openai_schema():
    env = get_environment()
    for name, tool in env.tools.get_tools().items():
        schema = tool.openai_schema
        assert schema["function"]["name"] == name
        assert schema["function"]["description"].strip(), f"{name} has no description"


def test_solo_mode_is_rejected():
    with pytest.raises(ValueError, match="solo mode"):
        get_environment(solo_mode=True)


# --- read / authentication -------------------------------------------------


def test_find_patron_ref_by_email_is_case_insensitive(tools: RestaurantTools):
    assert tools.find_patron_ref_by_email(PATRON_EMAIL) == PATRON_REF
    assert tools.find_patron_ref_by_email(PATRON_EMAIL.upper()) == PATRON_REF
    with pytest.raises(ValueError, match="Patron not found"):
        tools.find_patron_ref_by_email("nobody@example.com")


def test_find_patron_ref_by_name_zip(tools: RestaurantTools):
    assert (
        tools.find_patron_ref_by_name_zip(PATRON_GIVEN, PATRON_FAMILY, PATRON_ZIP)
        == PATRON_REF
    )
    # name matching is case-insensitive, postal code is exact
    assert (
        tools.find_patron_ref_by_name_zip(
            PATRON_GIVEN.lower(), PATRON_FAMILY.upper(), PATRON_ZIP
        )
        == PATRON_REF
    )
    with pytest.raises(ValueError, match="Patron not found"):
        tools.find_patron_ref_by_name_zip(PATRON_GIVEN, PATRON_FAMILY, "00000")


def test_get_patron_details(tools: RestaurantTools):
    patron = tools.get_patron_details(PATRON_REF)
    assert patron.guest_ref == PATRON_REF
    assert patron.contact_email == PATRON_EMAIL
    with pytest.raises(ValueError, match="Patron not found"):
        tools.get_patron_details("NOPE")


def test_get_ticket_and_dish_details(tools: RestaurantTools):
    ticket = tools.get_ticket_details(DINE_IN_TICKET)
    assert ticket.ticket_ref == DINE_IN_TICKET
    assert ticket.state == "placed"

    dish = tools.get_dish_details(ticket.line_entries[0].dish_ref)
    assert dish.selections

    with pytest.raises(ValueError, match="Ticket not found"):
        tools.get_ticket_details("NOPE")
    with pytest.raises(ValueError, match="Dish not found"):
        tools.get_dish_details("NOPE")


def test_list_all_dishes_is_sorted_by_title(tools: RestaurantTools):
    listed = tools.list_all_dishes()
    assert list(listed) == sorted(listed)
    assert all(ref in tools.db.menu_board for ref in listed.values())


# --- cancellation ----------------------------------------------------------


def test_cancel_placed_ticket_refunds_payments(tools: RestaurantTools):
    ticket = tools.get_ticket_details(DELIVERY_TICKET)
    payments = [c for c in ticket.charges if c.kind == "payment"]
    refunds_before = len([c for c in ticket.charges if c.kind == "refund"])

    cancelled = tools.cancel_placed_ticket(DELIVERY_TICKET, "no longer needed")

    assert cancelled.state == "cancelled"
    refunds_after = [c for c in cancelled.charges if c.kind == "refund"]
    assert len(refunds_after) == refunds_before + len(payments)
    assert {c.total for c in refunds_after} >= {c.total for c in payments}


def test_cancel_rejects_non_placed_ticket(tools: RestaurantTools):
    non_placed = next(
        t for t in tools.db.service_tickets.values() if t.state != "placed"
    )
    with pytest.raises(ValueError, match="'placed' state"):
        tools.cancel_placed_ticket(non_placed.ticket_ref, "nope")


# --- tips ------------------------------------------------------------------


def test_add_tip_to_ticket(tools: RestaurantTools):
    before = len(tools.get_ticket_details(DELIVERY_TICKET).charges)
    ticket = tools.add_tip_to_ticket(DELIVERY_TICKET, 5.25, DELIVERY_INSTRUMENT)
    assert len(ticket.charges) == before + 1
    assert ticket.charges[-1].kind == "tip"
    assert ticket.charges[-1].total == 5.25


def test_add_tip_validates(tools: RestaurantTools):
    with pytest.raises(ValueError, match="non-negative"):
        tools.add_tip_to_ticket(DELIVERY_TICKET, -1, DELIVERY_INSTRUMENT)
    with pytest.raises(ValueError, match="Payment instrument not found"):
        tools.add_tip_to_ticket(DELIVERY_TICKET, 1, "not_an_instrument")

    tools.cancel_placed_ticket(DELIVERY_TICKET, "done")
    with pytest.raises(ValueError, match="cancelled ticket"):
        tools.add_tip_to_ticket(DELIVERY_TICKET, 1, DELIVERY_INSTRUMENT)


# --- ticket modification ---------------------------------------------------


def test_modify_table_requires_dine_in(tools: RestaurantTools):
    ticket = tools.modify_placed_ticket_table(DINE_IN_TICKET, "Patio", "12", 4)
    assert ticket.table_info.zone == "Patio"
    assert ticket.table_info.table_no == "12"
    assert ticket.table_info.seat_count == 4

    with pytest.raises(ValueError, match="dine-in"):
        tools.modify_placed_ticket_table(DELIVERY_TICKET, "Patio", "12", 4)


def test_modify_dropoff_requires_delivery(tools: RestaurantTools):
    ticket = tools.modify_placed_ticket_dropoff(
        DELIVERY_TICKET, "1 New St", "Apt 2", "Springfield", "IL", "USA", "62704"
    )
    assert ticket.dropoff.line_one == "1 New St"
    assert ticket.dropoff.postal_code == "62704"

    with pytest.raises(ValueError, match="delivery"):
        tools.modify_placed_ticket_dropoff(
            DINE_IN_TICKET, "1 New St", "", "Springfield", "IL", "USA", "62704"
        )


def test_modify_instrument_swaps_payment(tools: RestaurantTools):
    # give the patron a second instrument to switch to
    patron = tools.get_patron_details(
        tools.get_ticket_details(DINE_IN_TICKET).guest_ref
    )
    original = next(iter(patron.saved_instruments.values()))
    second = original.model_copy(update={"instrument_ref": "SECOND01"})
    patron.saved_instruments["SECOND01"] = second

    ticket = tools.modify_placed_ticket_instrument(DINE_IN_TICKET, "SECOND01")

    assert ticket.charges[-2].kind == "payment"
    assert ticket.charges[-2].instrument_ref == "SECOND01"
    assert ticket.charges[-1].kind == "refund"
    assert ticket.charges[-1].instrument_ref == original.instrument_ref
    assert ticket.charges[-1].total == ticket.charges[-2].total


def test_modify_instrument_rejects_same_instrument(tools: RestaurantTools):
    ticket = tools.get_ticket_details(DINE_IN_TICKET)
    current = next(c for c in ticket.charges if c.kind == "payment").instrument_ref
    with pytest.raises(ValueError, match="different from the current one"):
        tools.modify_placed_ticket_instrument(DINE_IN_TICKET, current)


def test_modify_items_swaps_plate_and_charges_difference(tools: RestaurantTools):
    before = tools.get_ticket_details(DELIVERY_TICKET)
    old_cost = next(
        e.cost for e in before.line_entries if e.plate_ref == SWAP_FROM_PLATE
    )

    ticket = tools.modify_placed_ticket_items(
        DELIVERY_TICKET, [SWAP_FROM_PLATE], [SWAP_TO_PLATE], DELIVERY_INSTRUMENT
    )

    swapped = next(e for e in ticket.line_entries if e.plate_ref == SWAP_TO_PLATE)
    assert swapped.cost != old_cost
    assert ticket.charges[-1].kind == "payment"  # the replacement costs more
    assert ticket.charges[-1].total == round(swapped.cost - old_cost, 2)


def test_modify_items_validates(tools: RestaurantTools):
    with pytest.raises(ValueError, match="number of plates"):
        tools.modify_placed_ticket_items(
            DELIVERY_TICKET, [SWAP_FROM_PLATE], [], DELIVERY_INSTRUMENT
        )
    with pytest.raises(ValueError, match="not found in the ticket"):
        tools.modify_placed_ticket_items(
            DELIVERY_TICKET, ["not_on_ticket"], [SWAP_TO_PLATE], DELIVERY_INSTRUMENT
        )
    with pytest.raises(ValueError, match="Payment instrument not found"):
        tools.modify_placed_ticket_items(
            DELIVERY_TICKET, [SWAP_FROM_PLATE], [SWAP_TO_PLATE], "nope"
        )


# --- utility ---------------------------------------------------------------


def test_calculate(tools: RestaurantTools):
    assert tools.calculate("9.5 + 0.5") == "10.0"
    with pytest.raises(ValueError, match="invalid characters"):
        tools.calculate("import os")


def test_transfer_to_human_agents(tools: RestaurantTools):
    assert tools.transfer_to_human_agents("out of scope") == "Transfer successful"
