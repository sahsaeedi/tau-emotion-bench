"""Tests for the basketball domain, ported from TRACER\'s environment.

These run against the real data/tau_emotion/domains/basketball/db.json rather
than a synthetic fixture, so they also assert that the shipped data validates
against the pydantic models. Each test gets its own freshly loaded db.
"""

import pytest

from tau_emotion.domains.basketball.data_model import BasketballDB
from tau_emotion.domains.basketball.environment import get_environment
from tau_emotion.domains.basketball.tools import BasketballTools
from tau_emotion.domains.basketball.utils import BASKETBALL_DB_PATH

# Known-good records from the shipped db.json.
PLAYER_ID = "002OH84"
PLAYER_EMAIL = "stephen.markkanen@celtics.example.com"
PLAYER_FIRST = "Stephen"
PLAYER_LAST = "Markkanen"
CLUB_ID = "LP6PEUN"
CLUB_NAME = "Cleveland Cavaliers"
LEAGUE = "NBA"
FINAL_GAME = "00T55RR"
IN_PROGRESS_GAME = "00HF0T1"
IN_PROGRESS_HOME = "HFPQ361"
IN_PROGRESS_AWAY = "MI6WED0-C3"

EXPECTED_TOOLS = {
    "calculate",
    "find_player_id_by_email",
    "find_player_id_by_name",
    "get_club_details",
    "get_club_record",
    "get_club_schedule",
    "get_game_box_score",
    "get_game_details",
    "get_game_score",
    "get_game_timeline",
    "get_player_details",
    "get_player_total_points",
    "list_all_clubs",
    "list_club_roster_ids",
    "list_clubs_by_league",
    "modify_player_address",
    "record_scoring_event",
    "think",
    "transfer_to_human_agents",
    "update_game_status",
}


@pytest.fixture
def db() -> BasketballDB:
    return BasketballDB.load(BASKETBALL_DB_PATH)


@pytest.fixture
def tools(db: BasketballDB) -> BasketballTools:
    return BasketballTools(db)


def test_shipped_db_validates(db: BasketballDB):
    stats = db.get_statistics()
    assert stats["num_clubs"] > 0
    assert stats["num_players"] > 0
    assert stats["num_games"] > 0


def test_environment_exposes_expected_tools():
    env = get_environment()
    assert set(env.tools.get_tools()) == EXPECTED_TOOLS
    assert env.domain_name == "basketball"
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


# --- lookups ---------------------------------------------------------------


def test_get_details(tools: BasketballTools):
    assert tools.get_player_details(PLAYER_ID).player_id == PLAYER_ID
    assert tools.get_club_details(CLUB_ID).club_id == CLUB_ID
    assert tools.get_game_details(FINAL_GAME).game_id == FINAL_GAME


def test_missing_records_raise(tools: BasketballTools):
    with pytest.raises(ValueError, match="Player not found"):
        tools.get_player_details("NOPE")
    with pytest.raises(ValueError, match="Club not found"):
        tools.get_club_details("NOPE")
    with pytest.raises(ValueError, match="Game not found"):
        tools.get_game_details("NOPE")


def test_find_player_id_by_email_is_case_insensitive(tools: BasketballTools):
    assert tools.find_player_id_by_email(PLAYER_EMAIL) == PLAYER_ID
    assert tools.find_player_id_by_email(PLAYER_EMAIL.upper()) == PLAYER_ID
    with pytest.raises(ValueError, match="Player not found"):
        tools.find_player_id_by_email("nobody@example.com")


def test_find_player_id_by_name(tools: BasketballTools):
    """Names are matched case-insensitively and must be unique.

    The shipped data reuses real NBA names across generated records, so most
    names are ambiguous. Build an unambiguous one to exercise the happy path.
    """
    original = tools.get_player_details(PLAYER_ID)
    unique = original.model_copy(deep=True, update={"player_id": "UNIQUE01"})
    unique.name.first_name = "Zzz"
    unique.name.last_name = "Unique"
    tools.db.players["UNIQUE01"] = unique

    assert tools.find_player_id_by_name("Zzz", "Unique") == "UNIQUE01"
    assert tools.find_player_id_by_name("zzz", "UNIQUE") == "UNIQUE01"
    with pytest.raises(ValueError, match="Player not found"):
        tools.find_player_id_by_name("No", "Body")


def test_find_player_id_by_name_rejects_ambiguity(tools: BasketballTools):
    """A duplicate name must be reported, not silently resolved.

    PLAYER_ID's name is shared by several shipped records, so this is the
    normal case for this dataset rather than a constructed one.
    """
    duplicates = [
        p
        for p in tools.db.players.values()
        if p.name.first_name == PLAYER_FIRST and p.name.last_name == PLAYER_LAST
    ]
    assert len(duplicates) > 1

    with pytest.raises(ValueError, match="Multiple players found"):
        tools.find_player_id_by_name(PLAYER_FIRST, PLAYER_LAST)


def test_list_all_clubs_is_sorted_by_name(tools: BasketballTools):
    """Keyed by club NAME, so clubs sharing a name collapse to one entry.

    The shipped data has 240 clubs across only 30 distinct names, so this
    listing surfaces 30 of them — the last id seen for each name wins. That is
    TRACER's behaviour, kept as-is.
    """
    clubs = tools.list_all_clubs()
    assert list(clubs) == sorted(clubs)
    assert CLUB_NAME in clubs
    assert len(clubs) == len({c.name for c in tools.db.clubs.values()})
    assert clubs[CLUB_NAME] in {
        c.club_id for c in tools.db.clubs.values() if c.name == CLUB_NAME
    }


def test_list_clubs_by_league(tools: BasketballTools):
    clubs = tools.list_clubs_by_league(LEAGUE)
    assert CLUB_NAME in clubs
    # matching is case-insensitive
    assert tools.list_clubs_by_league(LEAGUE.lower()) == clubs
    with pytest.raises(ValueError, match="No clubs found"):
        tools.list_clubs_by_league("NOT_A_LEAGUE")


def test_list_club_roster_ids_respects_active_only(tools: BasketballTools):
    club = tools.get_club_details(CLUB_ID)
    everyone = tools.list_club_roster_ids(CLUB_ID, active_only=False)
    active = tools.list_club_roster_ids(CLUB_ID)

    assert everyone == sorted(club.roster)
    assert set(active) <= set(everyone)
    assert all(club.roster[pid].active for pid in active)


# --- game data -------------------------------------------------------------


def test_get_game_score(tools: BasketballTools):
    game = tools.get_game_details(FINAL_GAME)
    score = tools.get_game_score(FINAL_GAME)
    assert score["status"] == game.status
    assert score["home"]["club_id"] == game.clubs.home.club_id
    assert score["away"]["score"] == game.clubs.away.score


def test_get_game_box_score_and_timeline(tools: BasketballTools):
    box = tools.get_game_box_score(FINAL_GAME)
    assert box
    assert all(entry.player_id for entry in box)
    assert (
        tools.get_game_timeline(FINAL_GAME)
        == tools.get_game_details(FINAL_GAME).scoring_history
    )


def test_get_club_record_counts_only_final_games(tools: BasketballTools):
    record = tools.get_club_record(CLUB_ID)
    assert set(record) == {"wins", "losses"}

    club = tools.get_club_details(CLUB_ID)
    finals = [
        g
        for g in (tools.db.games.get(gid) for gid in club.games)
        if g is not None and g.status == "final"
    ]
    assert record["wins"] + record["losses"] <= len(finals)


def test_get_club_schedule_filters(tools: BasketballTools):
    everything = tools.get_club_schedule(CLUB_ID)
    assert everything

    finals = tools.get_club_schedule(CLUB_ID, status="final")
    assert set(finals) <= set(everything)
    assert all(tools.db.games[gid].status == "final" for gid in finals)

    assert tools.get_club_schedule(CLUB_ID, season="1899-00") == []


def test_get_player_total_points(tools: BasketballTools):
    total = tools.get_player_total_points(PLAYER_ID)
    expected = sum(
        entry.points
        for gid in tools.get_player_details(PLAYER_ID).games
        if (game := tools.db.games.get(gid)) is not None
        for entry in game.box_score
        if entry.player_id == PLAYER_ID
    )
    assert total == str(expected)
    assert tools.get_player_total_points(PLAYER_ID, season="1899-00") == "0"


# --- scoring ---------------------------------------------------------------


def test_record_scoring_event_updates_the_score(tools: BasketballTools):
    game = tools.get_game_details(IN_PROGRESS_GAME)
    home_before = game.clubs.home.score
    events_before = len(game.scoring_history)

    updated = tools.record_scoring_event(
        game_id=IN_PROGRESS_GAME,
        event_type="3PT",
        points=3,
        club_id=IN_PROGRESS_HOME,
        player_id=PLAYER_ID,
        timestamp="Q3 05:12",
    )

    assert updated.clubs.home.score == home_before + 3
    assert len(updated.scoring_history) == events_before + 1
    assert updated.scoring_history[-1].event_type == "3PT"


def test_record_scoring_event_updates_away_club(tools: BasketballTools):
    game = tools.get_game_details(IN_PROGRESS_GAME)
    away_before = game.clubs.away.score
    updated = tools.record_scoring_event(
        game_id=IN_PROGRESS_GAME,
        event_type="FT",
        points=1,
        club_id=IN_PROGRESS_AWAY,
        player_id=PLAYER_ID,
        timestamp="Q3 06:00",
    )
    assert updated.clubs.away.score == away_before + 1


def test_record_scoring_event_validates(tools: BasketballTools):
    with pytest.raises(ValueError, match="games in progress"):
        tools.record_scoring_event(
            FINAL_GAME, "2PT", 2, IN_PROGRESS_HOME, PLAYER_ID, "Q1 01:00"
        )
    with pytest.raises(ValueError, match="Invalid event type"):
        tools.record_scoring_event(
            IN_PROGRESS_GAME, "4PT", 4, IN_PROGRESS_HOME, PLAYER_ID, "Q1 01:00"
        )
    with pytest.raises(ValueError, match="Points do not match"):
        tools.record_scoring_event(
            IN_PROGRESS_GAME, "2PT", 3, IN_PROGRESS_HOME, PLAYER_ID, "Q1 01:00"
        )
    with pytest.raises(ValueError, match="not part of this game"):
        tools.record_scoring_event(
            IN_PROGRESS_GAME, "2PT", 2, CLUB_ID, PLAYER_ID, "Q1 01:00"
        )
    with pytest.raises(ValueError, match="Player not found"):
        tools.record_scoring_event(
            IN_PROGRESS_GAME, "2PT", 2, IN_PROGRESS_HOME, "NOPE", "Q1 01:00"
        )


# --- status ----------------------------------------------------------------


def test_update_game_status_allows_valid_transition(tools: BasketballTools):
    updated = tools.update_game_status(IN_PROGRESS_GAME, "final")
    assert updated.status == "final"


def test_update_game_status_is_a_noop_for_same_status(tools: BasketballTools):
    game = tools.get_game_details(FINAL_GAME)
    assert tools.update_game_status(FINAL_GAME, game.status).status == game.status


def test_update_game_status_rejects_invalid_transitions(tools: BasketballTools):
    # a final game is terminal
    with pytest.raises(ValueError, match="Invalid status transition"):
        tools.update_game_status(FINAL_GAME, "in_progress")
    # in_progress may only go to final
    with pytest.raises(ValueError, match="Invalid status transition"):
        tools.update_game_status(IN_PROGRESS_GAME, "scheduled")


# --- player address --------------------------------------------------------


def test_modify_player_address_replaces_every_field(tools: BasketballTools):
    updated = tools.modify_player_address(
        player_id=PLAYER_ID,
        street="1 Rocket Ct",
        city="Cleveland",
        state="OH",
        country="USA",
        zip="44115",
    )
    assert updated.address.street == "1 Rocket Ct"
    assert updated.address.city == "Cleveland"
    assert updated.address.state == "OH"
    assert updated.address.country == "USA"
    assert updated.address.zip == "44115"

    with pytest.raises(ValueError, match="Player not found"):
        tools.modify_player_address("NOPE", "a", "b", "c", "d", "e")


# --- utility ---------------------------------------------------------------


def test_calculate(tools: BasketballTools):
    assert tools.calculate("57 + 3") == "60.0"
    with pytest.raises(ValueError, match="Invalid characters"):
        tools.calculate("__builtins__")


def test_transfer_to_human_agents(tools: BasketballTools):
    assert tools.transfer_to_human_agents("out of scope") == "Transfer successful"
