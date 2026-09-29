"""Tests for the travel domain, ported from TRACER\'s environment.

These run against the real data/tau_emotion/domains/travel/db.json rather than
a synthetic fixture, so they also assert that the shipped data validates
against the pydantic models. Each test gets its own freshly loaded db.
"""

import pytest

from tau_emotion.domains.travel.data_model import TravelDB
from tau_emotion.domains.travel.environment import get_environment
from tau_emotion.domains.travel.tools import TravelTools
from tau_emotion.domains.travel.utils import TRAVEL_DB_PATH

# Known-good records from the shipped db.json.
TRAVELER_ID = "243TXC0"
BOOKING_ID = "BKG-V5VU3WK"
PACKAGE_ID = "Y9BR8CE"
DEPARTURE_DATE = "25-06-10"
OTHER_DEPARTURE = "25-05-20"
PAYMENT_METHOD = "O99FH7J"
AGENT_ID = "ZJJFS96"
AGENT_DATE = "25-05-03"
AGENT_SLOT = "08:30-11:30"

EXPECTED_TOOLS = {
    "book_package",
    "calculate",
    "cancel_booking",
    "get_agent_details",
    "get_booking_details",
    "get_package_details",
    "get_traveler_details",
    "list_all_destinations",
    "schedule_agent_meeting",
    "search_packages",
    "think",
    "transfer_to_human_agents",
    "update_booking_add_ons",
    "update_booking_departure_date",
    "update_booking_rooming",
    "update_booking_travelers",
}

PARTY = [
    {"first_name": "Ada", "last_name": "Lovelace", "dob": "1815-12-10"},
    {"first_name": "Alan", "last_name": "Turing", "dob": "1912-06-23"},
]


@pytest.fixture
def db() -> TravelDB:
    return TravelDB.load(TRAVEL_DB_PATH)


@pytest.fixture
def tools(db: TravelDB) -> TravelTools:
    return TravelTools(db)


def test_shipped_db_validates(db: TravelDB):
    stats = db.get_statistics()
    assert stats["num_packages"] > 0
    assert stats["num_travelers"] > 0
    assert stats["num_agents"] > 0
    assert stats["num_bookings"] > 0


def test_environment_exposes_expected_tools():
    env = get_environment()
    assert set(env.tools.get_tools()) == EXPECTED_TOOLS
    assert env.domain_name == "travel"
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


# --- read tools ------------------------------------------------------------


def test_get_details(tools: TravelTools):
    assert tools.get_traveler_details(TRAVELER_ID).traveler_id == TRAVELER_ID
    assert tools.get_package_details(PACKAGE_ID).package_id == PACKAGE_ID
    assert tools.get_agent_details(AGENT_ID).agent_id == AGENT_ID
    assert tools.get_booking_details(BOOKING_ID).booking_id == BOOKING_ID


def test_missing_records_raise(tools: TravelTools):
    with pytest.raises(ValueError, match="Traveler not found"):
        tools.get_traveler_details("NOPE")
    with pytest.raises(ValueError, match="Package not found"):
        tools.get_package_details("NOPE")
    with pytest.raises(ValueError, match="Agent not found"):
        tools.get_agent_details("NOPE")
    with pytest.raises(ValueError, match="Booking not found"):
        tools.get_booking_details("NOPE")


def test_booking_is_found_through_its_traveler(tools: TravelTools):
    """Bookings live on the traveler record, not in their own collection."""
    traveler, booking = tools._find_booking(BOOKING_ID)
    assert traveler.traveler_id == TRAVELER_ID
    assert booking in traveler.bookings


def test_list_all_destinations_is_deduplicated(tools: TravelTools):
    destinations = tools.list_all_destinations()
    keys = [(d.city, d.country) for d in destinations]
    assert len(keys) == len(set(keys))
    package = tools.get_package_details(PACKAGE_ID)
    assert (package.destinations[0].city, package.destinations[0].country) in keys


def test_search_packages_filters(tools: TravelTools):
    package = tools.get_package_details(PACKAGE_ID)
    city = package.destinations[0].city

    by_city = tools.search_packages(destination_city=city)
    assert PACKAGE_ID in {p.package_id for p in by_city}

    by_category = tools.search_packages(category=package.category)
    assert all(p.category == package.category for p in by_category)

    by_date = tools.search_packages(departure_date=DEPARTURE_DATE)
    assert all(DEPARTURE_DATE in p.departures for p in by_date)

    assert tools.search_packages(destination_city="Atlantis") == []


# --- booking ---------------------------------------------------------------


def test_book_package(tools: TravelTools):
    package = tools.get_package_details(PACKAGE_ID)
    slots_before = package.departures[DEPARTURE_DATE].available_slots
    base = package.departures[DEPARTURE_DATE].base_price
    # 2 travellers, one 1200 add-on, standard insurance at 50/head
    total = base * 2 + 1200.0 + 50.0 * 2

    booking = tools.book_package(
        traveler_id=TRAVELER_ID,
        package_id=PACKAGE_ID,
        departure_date=DEPARTURE_DATE,
        travelers=PARTY,
        rooming={"room_type": "double", "occupancy": 2},
        add_ons=[{"type": "excursion", "description": "Tour", "price": 1200.0}],
        insurance="standard",
        payment_methods=[{"payment_id": PAYMENT_METHOD, "amount": total}],
    )

    assert booking.status == "confirmed"
    assert booking.total_price == total
    assert len(booking.travelers) == 2
    assert booking.booking_id.startswith("BKG")  # deterministic, not uuid4
    assert package.departures[DEPARTURE_DATE].available_slots == slots_before - 2

    agent = tools.get_agent_details(booking.agent_id)
    assert TRAVELER_ID in agent.assigned_travelers
    assert booking.booking_id in agent.bookings_handled
    # it is reachable through the traveler it was attached to
    assert tools.get_booking_details(booking.booking_id) is booking


def test_book_package_defaults_to_first_managing_agent(tools: TravelTools):
    package = tools.get_package_details(PACKAGE_ID)
    base = package.departures[DEPARTURE_DATE].base_price
    booking = tools.book_package(
        traveler_id=TRAVELER_ID,
        package_id=PACKAGE_ID,
        departure_date=DEPARTURE_DATE,
        travelers=PARTY[:1],
        rooming={"room_type": "single", "occupancy": 1},
        add_ons=[],
        insurance=None,
        payment_methods=[{"payment_id": PAYMENT_METHOD, "amount": base}],
    )
    assert booking.agent_id == package.managed_by_agents[0]


def test_book_package_validates_payments(tools: TravelTools):
    with pytest.raises(ValueError, match="does not add up"):
        tools.book_package(
            traveler_id=TRAVELER_ID,
            package_id=PACKAGE_ID,
            departure_date=DEPARTURE_DATE,
            travelers=PARTY[:1],
            rooming={"room_type": "single", "occupancy": 1},
            add_ons=[],
            insurance=None,
            payment_methods=[{"payment_id": PAYMENT_METHOD, "amount": 1.0}],
        )
    with pytest.raises(ValueError, match="Payment method .* not found"):
        tools.book_package(
            traveler_id=TRAVELER_ID,
            package_id=PACKAGE_ID,
            departure_date=DEPARTURE_DATE,
            travelers=PARTY[:1],
            rooming={"room_type": "single", "occupancy": 1},
            add_ons=[],
            insurance=None,
            payment_methods=[{"payment_id": "nope", "amount": 1.0}],
        )


def test_book_package_validates_departure(tools: TravelTools):
    with pytest.raises(ValueError, match="not offered on"):
        tools.book_package(
            traveler_id=TRAVELER_ID,
            package_id=PACKAGE_ID,
            departure_date="99-01-01",
            travelers=PARTY[:1],
            rooming={"room_type": "single", "occupancy": 1},
            add_ons=[],
            insurance=None,
            payment_methods=[],
        )

    package = tools.get_package_details(PACKAGE_ID)
    huge_party = PARTY * 20
    with pytest.raises(ValueError, match="Not enough slots"):
        tools.book_package(
            traveler_id=TRAVELER_ID,
            package_id=PACKAGE_ID,
            departure_date=DEPARTURE_DATE,
            travelers=huge_party,
            rooming={"room_type": "double", "occupancy": 2},
            add_ons=[],
            insurance=None,
            payment_methods=[
                {
                    "payment_id": PAYMENT_METHOD,
                    "amount": package.departures[DEPARTURE_DATE].base_price
                    * len(huge_party),
                }
            ],
        )


# --- modification ----------------------------------------------------------


def test_update_booking_travelers_requires_same_count(tools: TravelTools):
    updated = tools.update_booking_travelers(BOOKING_ID, PARTY)
    assert [t.first_name for t in updated.travelers] == ["Ada", "Alan"]

    with pytest.raises(ValueError, match="Number of travelers does not match"):
        tools.update_booking_travelers(BOOKING_ID, PARTY[:1])


def test_update_booking_rooming(tools: TravelTools):
    updated = tools.update_booking_rooming(
        BOOKING_ID, {"room_type": "suite", "occupancy": 2}
    )
    assert updated.rooming.room_type == "suite"
    assert updated.rooming.occupancy == 2


def test_update_booking_rooming_normalizes_room_type(tools: TravelTools):
    # "family suite" and "family_suite" must store the same label.
    updated = tools.update_booking_rooming(
        BOOKING_ID, {"room_type": " Family  Suite ", "occupancy": 3}
    )
    assert updated.rooming.room_type == "family_suite"


def test_book_package_normalizes_room_type(tools: TravelTools):
    package = tools.get_package_details(PACKAGE_ID)
    base = package.departures[DEPARTURE_DATE].base_price
    booking = tools.book_package(
        traveler_id=TRAVELER_ID,
        package_id=PACKAGE_ID,
        departure_date=DEPARTURE_DATE,
        travelers=PARTY,
        rooming={"room_type": "family suite", "occupancy": 2},
        add_ons=[],
        insurance=None,
        payment_methods=[{"payment_id": PAYMENT_METHOD, "amount": base * 2}],
    )
    assert booking.rooming.room_type == "family_suite"


def test_book_package_null_string_insurance_is_none(tools: TravelTools):
    # The insurance schema says "null for none"; the string "null" must store None.
    package = tools.get_package_details(PACKAGE_ID)
    base = package.departures[DEPARTURE_DATE].base_price
    booking = tools.book_package(
        traveler_id=TRAVELER_ID,
        package_id=PACKAGE_ID,
        departure_date=DEPARTURE_DATE,
        travelers=PARTY[:1],
        rooming={"room_type": "single", "occupancy": 1},
        add_ons=[],
        insurance="null",
        payment_methods=[{"payment_id": PAYMENT_METHOD, "amount": base}],
    )
    assert booking.insurance is None


def test_update_booking_add_ons_charges_difference(tools: TravelTools):
    booking = tools.get_booking_details(BOOKING_ID)
    total_before = booking.total_price
    payments_before = len(booking.payment_history)

    updated = tools.update_booking_add_ons(
        BOOKING_ID,
        [{"type": "excursion", "description": "Bigger tour", "price": 2400.0}],
        PAYMENT_METHOD,
    )

    assert [a.price for a in updated.add_ons] == [2400.0]
    assert updated.total_price != total_before
    assert len(updated.payment_history) == payments_before + 1
    assert updated.payment_history[-1].amount == round(
        updated.total_price - total_before, 2
    )


def test_update_booking_add_ons_validates_payment_method(tools: TravelTools):
    with pytest.raises(ValueError, match="Payment method not found"):
        tools.update_booking_add_ons(BOOKING_ID, [], "nope")


def test_update_booking_departure_date_moves_slots(tools: TravelTools):
    package = tools.get_package_details(PACKAGE_ID)
    booking = tools.get_booking_details(BOOKING_ID)
    party_size = len(booking.travelers)
    old_slots = package.departures[DEPARTURE_DATE].available_slots
    new_slots = package.departures[OTHER_DEPARTURE].available_slots
    total_before = booking.total_price

    updated = tools.update_booking_departure_date(
        BOOKING_ID, OTHER_DEPARTURE, PAYMENT_METHOD
    )

    assert updated.departure_date == OTHER_DEPARTURE
    assert package.departures[DEPARTURE_DATE].available_slots == old_slots + party_size
    assert package.departures[OTHER_DEPARTURE].available_slots == new_slots - party_size
    # the new departure is cheaper, so the difference is refunded
    assert updated.total_price < total_before
    assert updated.payment_history[-1].amount < 0


def test_update_booking_departure_date_validates(tools: TravelTools):
    with pytest.raises(ValueError, match="not offered on"):
        tools.update_booking_departure_date(BOOKING_ID, "99-01-01", PAYMENT_METHOD)


# --- cancellation ----------------------------------------------------------


def test_cancel_booking_refunds_and_releases_slots(tools: TravelTools):
    package = tools.get_package_details(PACKAGE_ID)
    booking = tools.get_booking_details(BOOKING_ID)
    party_size = len(booking.travelers)
    slots_before = package.departures[DEPARTURE_DATE].available_slots

    cancelled = tools.cancel_booking(BOOKING_ID)

    assert cancelled.status == "cancelled"
    assert sum(p.amount for p in cancelled.payment_history) == 0
    assert (
        package.departures[DEPARTURE_DATE].available_slots == slots_before + party_size
    )


# --- agent meetings --------------------------------------------------------


def test_schedule_agent_meeting_consumes_the_slot(tools: TravelTools):
    agent = tools.get_agent_details(AGENT_ID)
    assert AGENT_SLOT in agent.availability[AGENT_DATE].slots

    message = tools.schedule_agent_meeting(
        AGENT_ID, AGENT_DATE, AGENT_SLOT, TRAVELER_ID
    )

    assert AGENT_ID in message and AGENT_SLOT in message
    assert AGENT_SLOT not in agent.availability[AGENT_DATE].slots
    # the same slot cannot be taken twice
    with pytest.raises(ValueError, match="not available on"):
        tools.schedule_agent_meeting(AGENT_ID, AGENT_DATE, AGENT_SLOT, TRAVELER_ID)


def test_schedule_agent_meeting_validates(tools: TravelTools):
    with pytest.raises(ValueError, match="not available on"):
        tools.schedule_agent_meeting(AGENT_ID, "99-01-01", AGENT_SLOT, TRAVELER_ID)
    with pytest.raises(ValueError, match="Traveler not found"):
        tools.schedule_agent_meeting(AGENT_ID, AGENT_DATE, AGENT_SLOT, "NOPE")


# --- utility ---------------------------------------------------------------


def test_calculate(tools: TravelTools):
    assert tools.calculate("18500 * 2") == "37000.0"
    with pytest.raises(ValueError, match="Invalid characters"):
        tools.calculate("__import__")


def test_transfer_to_human_agents(tools: TravelTools):
    assert tools.transfer_to_human_agents("out of scope") == "Transfer successful"
