"""Pydantic models for the restaurant domain.

Schema is reverse-engineered from TRACER's restaurant data files
(tracer/tracer/envs/restaurant/data/) merged into db.json.

Note the two distinct modifier vocabularies: a menu selection carries
`modifiers` (portion/preparation/protein/spice_level) while a ticket line
entry carries `mods` (heat/sauce/side). TRACER's tools never copy one onto
the other, so they stay separate models here.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from tau_emotion.domains.restaurant.utils import RESTAURANT_DB_PATH
from tau_emotion.environment.db import DB

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class Identity(BaseModel):
    given: str
    family: str


class Location(BaseModel):
    line_one: str
    line_two: str
    municipality: str
    province: str
    nation: str
    postal_code: str


# ---------------------------------------------------------------------------
# Menu board
# ---------------------------------------------------------------------------


class SelectionModifiers(BaseModel):
    """How a plate is prepared, as advertised on the menu."""

    portion: str
    preparation: str
    protein: Optional[str] = None
    spice_level: Optional[str] = None


class Selection(BaseModel):
    """One orderable variant ("plate") of a dish."""

    plate_ref: str
    cost: float
    served_today: bool
    modifiers: SelectionModifiers


class Dish(BaseModel):
    dish_ref: str
    title: str
    selections: Dict[str, Selection]


# ---------------------------------------------------------------------------
# Patron registry
# ---------------------------------------------------------------------------


class InstrumentMetadata(BaseModel):
    issuer: str
    tail_digits: str


class SavedInstrument(BaseModel):
    """A saved payment instrument: a card or a mobile-money account."""

    instrument_ref: str
    origin: str
    metadata: InstrumentMetadata


class Patron(BaseModel):
    guest_ref: str
    identity: Identity
    location: Location
    contact_email: str
    saved_instruments: Dict[str, SavedInstrument]
    ticket_log: List[str]


# ---------------------------------------------------------------------------
# Service tickets
# ---------------------------------------------------------------------------


class LineEntryMods(BaseModel):
    """Per-line customisations chosen at order time."""

    sauce: str
    side: str
    heat: Optional[str] = None


class LineEntry(BaseModel):
    dish_ref: str
    plate_ref: str
    label: str
    cost: float
    mods: LineEntryMods


class Charge(BaseModel):
    """A money movement on a ticket: payment, refund, tip, tax or delivery fee."""

    kind: str
    total: float
    instrument_ref: str


class TableInfo(BaseModel):
    zone: str
    table_no: str
    seat_count: int


class PrepBatch(BaseModel):
    plate_refs: List[str]
    parcel_tags: List[str] = Field(default_factory=list)


class ServiceTicket(BaseModel):
    ticket_ref: str
    guest_ref: str
    service_mode: str
    state: str
    line_entries: List[LineEntry]
    charges: List[Charge]
    prep_batches: List[PrepBatch]
    # Only dine-in tickets carry table info; only delivery tickets a dropoff.
    table_info: Optional[TableInfo] = None
    dropoff: Optional[Location] = None


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------


class RestaurantDB(DB):
    """Database for the restaurant domain."""

    menu_board: Dict[str, Dish]
    patron_registry: Dict[str, Patron]
    service_tickets: Dict[str, ServiceTicket]

    def get_statistics(self) -> dict[str, Any]:
        return {
            "num_dishes": len(self.menu_board),
            "num_patrons": len(self.patron_registry),
            "num_service_tickets": len(self.service_tickets),
        }


def get_db() -> RestaurantDB:
    return RestaurantDB.load(RESTAURANT_DB_PATH)


if __name__ == "__main__":
    db = get_db()
    print(db.get_statistics())
