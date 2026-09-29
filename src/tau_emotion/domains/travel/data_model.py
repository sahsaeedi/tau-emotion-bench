"""Pydantic models for the travel domain.

Schema is reverse-engineered from TRACER's travel data files
(tracer/tracer/envs/travel/data/) merged into
db.json.

Bookings do not live in their own collection: each one is embedded in the
traveler who made it, which is why the tools locate a booking by scanning
travelers (see `TravelTools._find_booking`).
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from tau_emotion.domains.travel.utils import TRAVEL_DB_PATH
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


class Contact(BaseModel):
    email: str
    phone: str


class Place(BaseModel):
    """A city/country pair, used for destinations and departure points."""

    city: str
    country: str


class Passport(BaseModel):
    number: str
    nationality: str
    expiry: str


class Person(BaseModel):
    """A traveller on a booking."""

    first_name: str
    last_name: str
    dob: str


# ---------------------------------------------------------------------------
# Packages
# ---------------------------------------------------------------------------


class Accommodation(BaseModel):
    name: str
    type: str
    nights: int
    location: Place


class Activity(BaseModel):
    day: int
    name: str
    description: str


class ItineraryDay(BaseModel):
    day: int
    title: str
    description: str
    location: Place
    included_meals: List[str] = Field(default_factory=list)


class Departure(BaseModel):
    """One dated departure of a package, keyed by date in `Package.departures`."""

    status: str
    available_slots: int
    base_price: float
    currency: str
    early_bird_deadline: str


class Transportation(BaseModel):
    international: str
    domestic: str
    ground: str


class PackagePolicies(BaseModel):
    cancellation_policy: str
    change_policy: str
    refund_policy: str


class Package(BaseModel):
    package_id: str
    name: str
    category: str
    description: str
    destinations: List[Place]
    duration_days: int
    departure_points: List[Place]
    departures: Dict[str, Departure]
    accommodations: List[Accommodation]
    activities: List[Activity]
    itinerary: List[ItineraryDay]
    transportation: Transportation
    inclusions: List[str]
    exclusions: List[str]
    policies: PackagePolicies
    managed_by_agents: List[str]
    notes: str


# ---------------------------------------------------------------------------
# Travelers and their bookings
# ---------------------------------------------------------------------------


class PaymentMethodExtraInfo(BaseModel):
    brand: Optional[str] = None
    last_four: Optional[str] = None


class PaymentMethod(BaseModel):
    source: str
    payment_method_id: str
    extra_info: PaymentMethodExtraInfo = Field(default_factory=PaymentMethodExtraInfo)


class Payment(BaseModel):
    """An entry in a booking's payment history. Negative = refund."""

    payment_id: str
    amount: float


class AddOn(BaseModel):
    type: str
    description: str
    price: float


class Rooming(BaseModel):
    room_type: str
    occupancy: int


class Booking(BaseModel):
    booking_id: str
    package_id: str
    agent_id: str
    booking_date: str
    departure_date: str
    status: str
    travelers: List[Person]
    rooming: Rooming
    add_ons: List[AddOn] = Field(default_factory=list)
    insurance: Optional[str] = None
    payment_history: List[Payment] = Field(default_factory=list)
    total_price: float
    notes: Optional[str] = None


class Preferences(BaseModel):
    room_type: str
    bed_preference: str
    dietary: Optional[str] = None
    accessibility: Optional[str] = None
    other: Optional[str] = None


class Companion(BaseModel):
    first_name: str
    last_name: str
    dob: str
    passport: Passport


class Traveler(BaseModel):
    traveler_id: str
    name: Name
    address: Address
    contact: Contact
    dob: str
    passport: Passport
    preferences: Preferences
    payment_methods: Dict[str, PaymentMethod]
    memberships: List[str]
    saved_companions: List[Companion] = Field(default_factory=list)
    bookings: List[Booking] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


class Agency(BaseModel):
    name: str
    address: Address


class AgentAvailability(BaseModel):
    """Bookable slots for one date, keyed by date in `Agent.availability`."""

    slots: List[str]
    timezone: str


class Agent(BaseModel):
    agent_id: str
    name: Name
    contact: Contact
    agency: Agency
    certifications: List[str]
    languages: List[str]
    regions_of_expertise: List[str]
    commission_rate: float
    employment_status: str
    availability: Dict[str, AgentAvailability]
    managed_packages: List[str] = Field(default_factory=list)
    assigned_travelers: List[str] = Field(default_factory=list)
    bookings_handled: List[str] = Field(default_factory=list)
    notes: str


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------


class TravelDB(DB):
    """Database for the travel domain."""

    packages: Dict[str, Package]
    travelers: Dict[str, Traveler]
    agents: Dict[str, Agent]

    def get_statistics(self) -> dict[str, Any]:
        return {
            "num_packages": len(self.packages),
            "num_travelers": len(self.travelers),
            "num_agents": len(self.agents),
            "num_bookings": sum(len(t.bookings) for t in self.travelers.values()),
        }


def get_db() -> TravelDB:
    return TravelDB.load(TRAVEL_DB_PATH)


if __name__ == "__main__":
    db = get_db()
    print(db.get_statistics())
