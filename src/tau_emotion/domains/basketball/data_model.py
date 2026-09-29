"""Pydantic models for the basketball domain.

Schema is reverse-engineered from TRACER's basketball data files
(tracer/tracer/envs/basketball/data/) merged into
db.json.

A club's `roster` and a player's `contracts` are keyed maps (by player id and
contract id) rather than fixed-field objects.
"""

from typing import Any, Dict, List, Union

from pydantic import BaseModel, Field

from tau_emotion.domains.basketball.utils import BASKETBALL_DB_PATH
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
# Clubs
# ---------------------------------------------------------------------------


class Arena(BaseModel):
    name: str
    address: Address


class PlayerProfile(BaseModel):
    """A player's listing on a club roster.

    Shirt numbers are int or str in TRACER's data.
    """

    position: str
    number: Union[int, str]
    height_cm: float
    weight_kg: float


class RosterEntry(BaseModel):
    player_id: str
    active: bool
    salary: float
    profile: PlayerProfile


class Club(BaseModel):
    club_id: str
    name: str
    league: str
    city: str
    arena: Arena
    roster: Dict[str, RosterEntry]
    games: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------


class ContractExtraInfo(BaseModel):
    salary: float
    years: int


class Contract(BaseModel):
    contract_id: str
    club_id: str
    source: str
    start_date: str
    end_date: str
    extra_info: ContractExtraInfo


class Player(BaseModel):
    player_id: str
    name: Name
    address: Address
    email: str
    contracts: Dict[str, Contract]
    games: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


class GameClub(BaseModel):
    club_id: str
    name: str
    score: int


class GameClubs(BaseModel):
    home: GameClub
    away: GameClub


class BoxScoreOptions(BaseModel):
    minutes: str
    rebounds: int
    assists: int


class BoxScoreEntry(BaseModel):
    player_id: str
    name: str
    club_id: str
    points: int
    options: BoxScoreOptions


class ScoringEvent(BaseModel):
    event_type: str
    points: int
    club_id: str
    player_id: str
    timestamp: str


class Period(BaseModel):
    period_number: int
    player_ids: List[str] = Field(default_factory=list)
    event_ids: List[str] = Field(default_factory=list)


class Game(BaseModel):
    game_id: str
    season: str
    date: str
    status: str
    venue: Address
    clubs: GameClubs
    box_score: List[BoxScoreEntry] = Field(default_factory=list)
    scoring_history: List[ScoringEvent] = Field(default_factory=list)
    periods: List[Period] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------


class BasketballDB(DB):
    """Database for the basketball domain."""

    clubs: Dict[str, Club]
    players: Dict[str, Player]
    games: Dict[str, Game]

    def get_statistics(self) -> dict[str, Any]:
        return {
            "num_clubs": len(self.clubs),
            "num_players": len(self.players),
            "num_games": len(self.games),
        }


def get_db() -> BasketballDB:
    return BasketballDB.load(BASKETBALL_DB_PATH)


if __name__ == "__main__":
    db = get_db()
    print(db.get_statistics())
