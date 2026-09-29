"""Tests for the movie domain, ported from TRACER\'s environment.

These run against the real data/tau_emotion/domains/movie/db.json rather than
a synthetic fixture, so they also assert that the shipped data validates
against the pydantic models. Each test gets its own freshly loaded db.
"""

import pytest

from tau_emotion.domains.movie.data_model import MovieDB
from tau_emotion.domains.movie.environment import get_environment
from tau_emotion.domains.movie.tools import MovieTools
from tau_emotion.domains.movie.utils import MOVIE_DB_PATH

# Known-good records from the shipped db.json.
THEATER_ID = "UP6GE3P"
SHOW_ID = "SEV-241012-1800-HABL"
SHOW_DATE = "24-10-12"
BOOKING_ID = "00NKOV5-B2"  # confirmed, holds HELD_SEATS
HELD_SEATS = ["B9", "B6"]
FREE_SEAT = "A3"

CUSTOMER = {
    "name": {"first_name": "Ada", "last_name": "Lovelace"},
    "email": "ada@example.com",
    "phone": "555-0100",
}

EXPECTED_TOOLS = {
    "calculate",
    "cancel_booking",
    "create_booking",
    "get_booking_details",
    "get_movie_details",
    "get_seat_availability",
    "get_show_details",
    "get_show_status",
    "get_theater_details",
    "list_movies",
    "list_shows",
    "list_theaters",
    "price_preview",
    "think",
    "transfer_to_human_agents",
    "update_booking_seats",
}


@pytest.fixture
def db() -> MovieDB:
    return MovieDB.load(MOVIE_DB_PATH)


@pytest.fixture
def tools(db: MovieDB) -> MovieTools:
    return MovieTools(db)


def test_shipped_db_validates(db: MovieDB):
    stats = db.get_statistics()
    assert stats["num_theaters"] > 0
    assert stats["num_movies"] > 0
    assert stats["num_bookings"] > 0


def test_environment_exposes_expected_tools():
    env = get_environment()
    assert set(env.tools.get_tools()) == EXPECTED_TOOLS
    assert env.domain_name == "movie"
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


def test_list_and_get_details(tools: MovieTools):
    theaters = tools.list_theaters()
    assert {"theater_id", "name"} == set(theaters[0])
    assert THEATER_ID in {t["theater_id"] for t in theaters}

    movies = tools.list_movies()
    assert {"movie_id", "title"} == set(movies[0])

    assert tools.get_theater_details(THEATER_ID).theater_id == THEATER_ID
    movie_id = tools.get_show_details(THEATER_ID, SHOW_ID).movie_id
    assert tools.get_movie_details(movie_id).movie_id == movie_id
    assert tools.get_booking_details(BOOKING_ID).booking_id == BOOKING_ID


def test_missing_records_raise(tools: MovieTools):
    with pytest.raises(ValueError, match="Theater .* not found"):
        tools.get_theater_details("NOPE")
    with pytest.raises(ValueError, match="Movie .* not found"):
        tools.get_movie_details("NOPE")
    with pytest.raises(ValueError, match="Booking .* not found"):
        tools.get_booking_details("NOPE")
    with pytest.raises(ValueError, match="Show .* not found"):
        tools.get_show_details(THEATER_ID, "NOPE")


def test_list_shows(tools: MovieTools):
    shows = tools.list_shows(THEATER_ID, SHOW_DATE)
    assert SHOW_ID in {s.show_id for s in shows}
    # an unscheduled date yields an empty list rather than an error
    assert tools.list_shows(THEATER_ID, "99-01-01") == []

    movie_id = shows[0].movie_id
    filtered = tools.list_shows(THEATER_ID, SHOW_DATE, movie_id=movie_id)
    assert all(s.movie_id == movie_id for s in filtered)


def test_get_show_details_with_date(tools: MovieTools):
    assert tools.get_show_details(THEATER_ID, SHOW_ID, SHOW_DATE).show_id == SHOW_ID
    with pytest.raises(ValueError, match="No schedule for date"):
        tools.get_show_details(THEATER_ID, SHOW_ID, "99-01-01")


def test_get_show_status(tools: MovieTools):
    assert tools.get_show_status(THEATER_ID, SHOW_ID) == "scheduled"


def test_get_seat_availability_reflects_confirmed_bookings(tools: MovieTools):
    availability = tools.get_seat_availability(THEATER_ID, SHOW_ID)
    assert set(HELD_SEATS) <= set(availability["booked"])
    assert FREE_SEAT in availability["available"]
    assert not set(availability["available"]) & set(availability["booked"])


# --- pricing ---------------------------------------------------------------


def test_price_preview_breakdown(tools: MovieTools):
    preview = tools.price_preview(
        THEATER_ID, SHOW_ID, [{"seat_id": FREE_SEAT, "ticket_type": "adult"}]
    )
    theater = tools.get_theater_details(THEATER_ID)
    show = tools.get_show_details(THEATER_ID, SHOW_ID)
    price = show.price_schema.adult
    fee = show.price_schema.fees.convenience_fee
    booking_fee = theater.pricing_rules.fees.booking_fee
    tax = round((price + fee) * theater.pricing_rules.tax_rate_percent / 100, 2)

    # one adult ticket: price + per-ticket fee, taxed, plus one booking fee
    assert preview["tickets_subtotal"] == round(price, 2)
    assert preview["fees_total"] == round(fee + booking_fee, 2)
    assert preview["tax_total"] == tax
    assert preview["grand_total"] == round(price + fee + booking_fee + tax, 2)
    assert preview["ticket_count"] == 1


def test_price_preview_rejects_taken_and_unknown_seats(tools: MovieTools):
    with pytest.raises(ValueError, match="Seats not available"):
        tools.price_preview(
            THEATER_ID, SHOW_ID, [{"seat_id": HELD_SEATS[0], "ticket_type": "adult"}]
        )
    with pytest.raises(ValueError, match="Unknown seat ids"):
        tools.price_preview(
            THEATER_ID, SHOW_ID, [{"seat_id": "Z9-99", "ticket_type": "adult"}]
        )


def test_price_preview_rejects_bad_ticket_type(tools: MovieTools):
    with pytest.raises(ValueError, match="Invalid ticket type"):
        tools.price_preview(
            THEATER_ID, SHOW_ID, [{"seat_id": FREE_SEAT, "ticket_type": "student"}]
        )


# --- create booking --------------------------------------------------------


def test_create_booking(tools: MovieTools):
    seats = [{"seat_id": FREE_SEAT, "ticket_type": "adult"}]
    total = tools.price_preview(THEATER_ID, SHOW_ID, seats)["grand_total"]

    booking = tools.create_booking(
        theater_id=THEATER_ID,
        show_id=SHOW_ID,
        customer=CUSTOMER,
        seats=seats,
        delivery_method="e-ticket",
        payments=[{"amount": total, "method": {"source": "card"}}],
    )

    assert booking.status == "confirmed"
    assert booking.totals.grand_total == total
    assert booking.totals.amount_due == 0.0
    assert [s.seat_id for s in booking.seats] == [FREE_SEAT]
    assert len(booking.delivery.tickets) == 1
    # ids and timestamps are assigned by the system, in TRACER's formats
    assert booking.booking_id == "BKG000001"
    assert [p.payment_id for p in booking.payment_history] == ["BKG000001-PAY-01"]
    assert booking.payment_history[0].method.source == "card"
    assert tools.db.bookings[booking.booking_id] is booking
    # the seat is now unavailable to others
    assert FREE_SEAT in tools.get_seat_availability(THEATER_ID, SHOW_ID)["booked"]


def test_create_booking_rejects_payment_mismatch(tools: MovieTools):
    with pytest.raises(ValueError, match="does not add up"):
        tools.create_booking(
            theater_id=THEATER_ID,
            show_id=SHOW_ID,
            customer=CUSTOMER,
            seats=[{"seat_id": FREE_SEAT, "ticket_type": "adult"}],
            delivery_method="e-ticket",
            payments=[{"amount": 1.0, "method": {"source": "card"}}],
        )


# --- update seats ----------------------------------------------------------


def test_update_booking_seats_refunds_when_cheaper(tools: MovieTools):
    booking = tools.get_booking_details(BOOKING_ID)
    assert len(booking.seats) == 2
    # the tool mutates the booking in place, so snapshot the scalars first
    grand_before = booking.totals.grand_total
    paid_before = booking.totals.amount_paid

    # drop to a single seat: strictly cheaper, so a refund is recorded
    updated = tools.update_booking_seats(
        BOOKING_ID, [{"seat_id": HELD_SEATS[0], "ticket_type": "adult"}]
    )

    assert [s.seat_id for s in updated.seats] == [HELD_SEATS[0]]
    assert updated.totals.grand_total < grand_before
    refund = updated.payment_history[-1]
    assert refund.amount < 0
    assert refund.method.payment_method_id == "refund"
    assert updated.totals.amount_paid == round(paid_before + refund.amount, 2)
    assert updated.totals.amount_due == round(
        updated.totals.grand_total - updated.totals.amount_paid, 2
    )


def test_update_booking_seats_requires_exact_top_up(tools: MovieTools):
    # add a third seat: more expensive, so a matching payment is required
    seats = [{"seat_id": s, "ticket_type": "adult"} for s in HELD_SEATS + [FREE_SEAT]]
    with pytest.raises(ValueError, match="Additional payment of"):
        tools.update_booking_seats(BOOKING_ID, seats)


def test_update_booking_seats_keeps_own_seats_available(tools: MovieTools):
    """Re-submitting the seats a booking already holds must not trip the
    seat-conflict check.

    The booking is still repriced from scratch, and a shipped booking's stored
    totals need not match the tools' pricing formula (see the module docstring
    on MovieTools), so the update may need a top-up. What matters here is that
    it never fails on availability.
    """
    seats = [{"seat_id": s, "ticket_type": "adult"} for s in HELD_SEATS]
    try:
        updated = tools.update_booking_seats(BOOKING_ID, seats)
    except ValueError as e:
        assert "Seats not available" not in str(e)
        assert "Additional payment" in str(e)
        top_up = float(str(e).split("Additional payment of ")[1].split()[0])
        updated = tools.update_booking_seats(
            BOOKING_ID,
            seats,
            payment={"amount": top_up, "method": {"source": "card"}},
        )
        top_up_entry = updated.payment_history[-1]
        assert top_up_entry.payment_id == f"{BOOKING_ID}-adj-pay-01"
        assert top_up_entry.amount == top_up
    assert {s.seat_id for s in updated.seats} == set(HELD_SEATS)


def test_update_booking_seats_rejects_cancelled_booking(tools: MovieTools):
    tools.cancel_booking(BOOKING_ID)
    with pytest.raises(ValueError, match="Only confirmed bookings"):
        tools.update_booking_seats(
            BOOKING_ID, [{"seat_id": HELD_SEATS[0], "ticket_type": "adult"}]
        )


# --- cancel ----------------------------------------------------------------


def test_cancel_booking_refunds_in_full(tools: MovieTools):
    before = tools.get_booking_details(BOOKING_ID)
    paid = before.totals.amount_paid
    assert paid > 0

    cancelled = tools.cancel_booking(BOOKING_ID)

    assert cancelled.status == "canceled"
    assert cancelled.canceled_at
    assert cancelled.totals.amount_paid == 0.0
    assert cancelled.payment_history[-1].amount == -paid
    # the seats are released
    availability = tools.get_seat_availability(THEATER_ID, SHOW_ID)
    assert set(HELD_SEATS) <= set(availability["available"])


def test_cancel_booking_is_idempotent(tools: MovieTools):
    first = tools.cancel_booking(BOOKING_ID)
    payments = len(first.payment_history)
    second = tools.cancel_booking(BOOKING_ID)
    assert len(second.payment_history) == payments


# --- utility ---------------------------------------------------------------


def test_calculate(tools: MovieTools):
    assert tools.calculate("10 * 2 + 3") == "23.0"
    with pytest.raises(ValueError, match="Invalid characters"):
        tools.calculate("open('x')")


def test_transfer_to_human_agents(tools: MovieTools):
    assert tools.transfer_to_human_agents("out of scope") == "Transfer successful"
