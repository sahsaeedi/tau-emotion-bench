"""Pydantic models for the movie domain.

Schema is reverse-engineered from TRACER's movie data files
(tracer/tracer/envs/movie/data/) merged into
db.json.

A theater's `auditoriums`, its `dates` schedule, and each seat map's `rows`
are keyed maps rather than fixed-field objects.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from tau_emotion.domains.movie.utils import MOVIE_DB_PATH
from tau_emotion.environment.db import DB

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class Name(BaseModel):
    first_name: str
    last_name: str


class Address(BaseModel):
    street: str
    city: str
    state: str
    zip: str
    country: str


# ---------------------------------------------------------------------------
# Theaters
# ---------------------------------------------------------------------------


class Contact(BaseModel):
    phone: str
    email: str
    website: str


class Seat(BaseModel):
    seat_id: str
    type: str
    wheelchair_accessible: bool


class SeatMap(BaseModel):
    """Seats keyed by row label."""

    rows: Dict[str, List[Seat]]


class Auditorium(BaseModel):
    auditorium_id: str
    name: str
    capacity: int
    features: List[str]
    seat_map: SeatMap


class ShowFees(BaseModel):
    convenience_fee: float


class PriceSchema(BaseModel):
    adult: float
    child: float
    senior: float
    fees: ShowFees


class Show(BaseModel):
    show_id: str
    movie_id: str
    auditorium_id: str
    start_time_local: str
    end_time_local: str
    format: str
    language: str
    subtitles: str
    status: str
    price_schema: PriceSchema


class ScheduleDay(BaseModel):
    shows: List[Show]


class BasePricing(BaseModel):
    adult: float
    child: float
    senior: float


class TheaterFees(BaseModel):
    booking_fee: float
    convenience_fee: float


class FormatSurcharges(BaseModel):
    IMAX: float
    Dolby: float
    # Field name cannot start with a digit, so the JSON key is aliased.
    three_d: float = Field(alias="3D")

    # Serialize as "3D" so tool output and saved DBs keep TRACER's key.
    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class TimeBasedPricing(BaseModel):
    matinee_discount: float
    peak_surcharge: float


class PricingRules(BaseModel):
    base: BasePricing
    fees: TheaterFees
    format_surcharges: FormatSurcharges
    time_based: TimeBasedPricing
    tax_rate_percent: float


class Theater(BaseModel):
    theater_id: str
    name: str
    address: Address
    contact: Contact
    amenities: List[str]
    auditoriums: Dict[str, Auditorium]
    pricing_rules: PricingRules
    dates: Dict[str, ScheduleDay]


# ---------------------------------------------------------------------------
# Movies
# ---------------------------------------------------------------------------


class CastMember(BaseModel):
    name: str
    role: str


class Crew(BaseModel):
    director: str
    writer: str
    producer: str
    music: str


class Movie(BaseModel):
    movie_id: str
    title: str
    genres: List[str]
    runtime_minutes: int
    mpaa_rating: str
    languages_audio: List[str]
    subtitles: List[str]
    formats: List[str]
    release_date: str
    end_of_run_est: str
    synopsis: str
    cast: List[CastMember]
    crew: Crew


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------


class Customer(BaseModel):
    name: Name
    email: str
    phone: str
    loyalty_id: Optional[str] = None


class BookedSeat(BaseModel):
    seat_id: str
    ticket_type: str
    price: float
    convenience_fee: float
    tax: float


class ConcessionLine(BaseModel):
    item_id: str
    name: str
    size: str
    quantity: int
    price_each: float
    tax_each: float
    total: float


class PaymentExtraInfo(BaseModel):
    brand: Optional[str] = None
    last_four: Optional[str] = None


class PaymentMethod(BaseModel):
    source: str
    # Payments recorded by create_booking / update_booking_seats carry only the
    # source; refunds carry a placeholder id and no extra info.
    payment_method_id: Optional[str] = None
    extra_info: Optional[PaymentExtraInfo] = None


class Payment(BaseModel):
    payment_id: str
    amount: float
    method: PaymentMethod
    created_at: str


class Promotion(BaseModel):
    code: str
    description: str
    discount_amount: float


class DeliveryTicket(BaseModel):
    ticket_id: str
    barcode: str


class Delivery(BaseModel):
    method: str
    tickets: List[DeliveryTicket] = Field(default_factory=list)


class BookingTotals(BaseModel):
    tickets_subtotal: float
    concessions_subtotal: float
    fees_total: float
    tax_total: float
    grand_total: float
    amount_paid: float
    amount_due: float


class Booking(BaseModel):
    booking_id: str
    theater_id: str
    movie_id: str
    show_id: str
    date: str
    start_time_local: str
    status: str
    created_at: str
    customer: Customer
    seats: List[BookedSeat]
    concessions: List[ConcessionLine] = Field(default_factory=list)
    promotions_applied: List[Promotion] = Field(default_factory=list)
    payment_history: List[Payment] = Field(default_factory=list)
    totals: BookingTotals
    delivery: Delivery
    canceled_at: Optional[str] = None
    special_requests: Optional[str] = None


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------


class MovieDB(DB):
    """Database for the movie domain."""

    theaters: Dict[str, Theater]
    movies: Dict[str, Movie]
    bookings: Dict[str, Booking]

    def get_statistics(self) -> dict[str, Any]:
        return {
            "num_theaters": len(self.theaters),
            "num_movies": len(self.movies),
            "num_bookings": len(self.bookings),
        }


def get_db() -> MovieDB:
    return MovieDB.load(MOVIE_DB_PATH)


if __name__ == "__main__":
    db = get_db()
    print(db.get_statistics())
