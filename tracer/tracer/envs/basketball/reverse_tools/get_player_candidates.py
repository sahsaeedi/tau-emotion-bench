import json
import random
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool

# Max number of players to return per call (paginated batch)
_MAX_PLAYERS = 5

# Call counter: each invoke returns the "next" batch so subsequent calls get different players
_call_counter = 0

# Statuses a game can still legally transition out of. Mirrors update_game_status:
# scheduled -> in_progress|postponed, postponed -> scheduled, in_progress -> final, final -> (none).
_UPDATABLE_STATUSES = {"scheduled", "postponed", "in_progress"}


def _player_games(
    player: Dict[str, Any], games: Dict[str, Any]
) -> List[Dict[str, Any]]:
    return [games[gid] for gid in player.get("games", []) if gid in games]


def _player_clubs(player_id: str, clubs: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [c for c in clubs.values() if player_id in (c.get("roster") or {})]


def _has_game_status(player_games: List[Dict[str, Any]], status: str) -> bool:
    return any(g.get("status") == status for g in player_games)


def _has_updatable_game(player_games: List[Dict[str, Any]]) -> bool:
    return any(g.get("status") in _UPDATABLE_STATUSES for g in player_games)


def _total_points(player_id: str, player_games: List[Dict[str, Any]]) -> int:
    return sum(
        entry.get("points", 0)
        for g in player_games
        for entry in g.get("box_score", [])
        if entry.get("player_id") == player_id
    )


def _scoring_event_count(player_id: str, player_games: List[Dict[str, Any]]) -> int:
    return sum(
        1
        for g in player_games
        for event in g.get("scoring_history", [])
        if event.get("player_id") == player_id
    )


def _has_contract_source(player: Dict[str, Any], source: str) -> bool:
    return any(
        c.get("source") == source for c in (player.get("contracts") or {}).values()
    )


def _positions(player_id: str, player_clubs: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for club in player_clubs:
        entry = (club.get("roster") or {}).get(player_id) or {}
        pos = (entry.get("profile") or {}).get("position")
        if pos and pos not in out:
            out.append(pos)
    return out


def _club_final_game_count(
    player_clubs: List[Dict[str, Any]], games: Dict[str, Any]
) -> int:
    best = 0
    for club in player_clubs:
        n = sum(
            1
            for gid in club.get("games", [])
            if games.get(gid, {}).get("status") == "final"
        )
        best = max(best, n)
    return best


class GetPlayerCandidates(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        game_status: Optional[str] = None,
        has_updatable_game: Optional[bool] = None,
        min_total_points: Optional[int] = None,
        min_scoring_events: Optional[int] = None,
        min_games: Optional[int] = None,
        contract_source: Optional[str] = None,
        min_contracts: Optional[int] = None,
        position: Optional[str] = None,
        address_state: Optional[str] = None,
        min_club_final_games: Optional[int] = None,
    ) -> str:
        global _call_counter

        players: Dict[str, Any] = data.get("players") or {}
        games: Dict[str, Any] = data.get("games") or {}
        clubs: Dict[str, Any] = data.get("clubs") or {}

        candidates: List[Dict[str, Any]] = []

        for player_id, player in players.items():
            player_games = _player_games(player, games)

            if game_status is not None and not _has_game_status(
                player_games, game_status
            ):
                continue
            if has_updatable_game is not None:
                if bool(has_updatable_game) != _has_updatable_game(player_games):
                    continue

            points = _total_points(player_id, player_games)
            if min_total_points is not None:
                try:
                    if points < int(min_total_points):
                        continue
                except (TypeError, ValueError):
                    pass

            events = _scoring_event_count(player_id, player_games)
            if min_scoring_events is not None:
                try:
                    if events < int(min_scoring_events):
                        continue
                except (TypeError, ValueError):
                    pass

            if min_games is not None:
                try:
                    if len(player_games) < int(min_games):
                        continue
                except (TypeError, ValueError):
                    pass

            if contract_source is not None and not _has_contract_source(
                player, contract_source
            ):
                continue
            if min_contracts is not None:
                try:
                    if len(player.get("contracts") or {}) < int(min_contracts):
                        continue
                except (TypeError, ValueError):
                    pass

            player_clubs = _player_clubs(player_id, clubs)
            positions = _positions(player_id, player_clubs)
            if position is not None and position not in positions:
                continue

            address = player.get("address") or {}
            if address_state is not None and address.get("state") != address_state:
                continue

            club_finals = _club_final_game_count(player_clubs, games)
            if min_club_final_games is not None:
                try:
                    if club_finals < int(min_club_final_games):
                        continue
                except (TypeError, ValueError):
                    pass

            name = player.get("name", {})
            display_name = (
                " ".join(
                    p for p in [name.get("first_name"), name.get("last_name")] if p
                ).strip()
                or "Unknown"
            )
            candidates.append(
                {
                    "player_id": player_id,
                    "name": display_name,
                    "email": player.get("email", ""),
                    "state": address.get("state", ""),
                    "zip": address.get("zip", ""),
                    "club_ids": [c.get("club_id") for c in player_clubs],
                    "positions": positions,
                    "num_games": len(player_games),
                    "games_by_status": {
                        s: sum(1 for g in player_games if g.get("status") == s)
                        for s in sorted(
                            {g.get("status") for g in player_games if g.get("status")}
                        )
                    },
                    "total_points": points,
                    "num_scoring_events": events,
                    "num_contracts": len(player.get("contracts") or {}),
                    "club_final_games": club_finals,
                }
            )

        random.shuffle(candidates)
        total = len(candidates)
        if total == 0:
            return json.dumps(
                {"total_matching": 0, "returned_count": 0, "players": []}, indent=2
            )

        offset = (_call_counter * _MAX_PLAYERS) % total
        _call_counter += 1
        doubled = candidates + candidates
        batch = doubled[offset : offset + _MAX_PLAYERS]

        payload = {
            "total_matching": total,
            "returned_count": len(batch),
            "players": batch,
        }
        return json.dumps(payload, indent=2)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_player_candidates",
                "description": (
                    "Read-only roster of players matching zero or more filters, for finding a real player whose "
                    "data already satisfies a scenario precondition (e.g. a player who is actually in an "
                    "in-progress game, or one whose game can still legally change status). All filter parameters "
                    "are optional; when a filter is omitted, no constraint is applied for that field. Filters "
                    "combine with AND semantics — a player must satisfy every filter provided to match. Returns "
                    "concise summaries (player_id, name, email, state/zip, club_ids, positions, per-status game "
                    "counts, total points, scoring-event count, contract count), not full records — use "
                    "get_player_details, get_club_details, get_game_details, get_game_box_score, etc. for full "
                    "details once a candidate player_id is chosen. The list is randomized; each call returns the "
                    f"next batch (up to {_MAX_PLAYERS} players, different from previous calls)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "game_status": {
                            "type": "string",
                            "enum": ["scheduled", "in_progress", "final", "postponed"],
                            "description": (
                                "If set, only players with at least one game in this status. This is the most "
                                "important grounding filter in this domain: record_scoring_event only works on a "
                                "game whose status is 'in_progress', and the data is heavily skewed toward "
                                "'final' games, so use 'in_progress' whenever the scenario involves recording a "
                                "basket or closing out a live game. Use 'scheduled' for tip-off/postponement "
                                "scenarios and 'postponed' for rescheduling ones (postponed games are extremely "
                                "rare in the data)."
                            ),
                        },
                        "has_updatable_game": {
                            "type": "boolean",
                            "description": (
                                "If True, only players with at least one game whose status can still legally "
                                "change (scheduled, postponed, or in_progress); if False, only players whose "
                                "games are all 'final'. update_game_status rejects any transition out of "
                                "'final', and most games in the data are already final, so set True to ground an "
                                "update_game_status task in a game that can actually be transitioned."
                            ),
                        },
                        "min_total_points": {
                            "type": "integer",
                            "description": (
                                "If set, only players whose total points across their games' box scores is at "
                                "least this value. Use it to ground a get_player_total_points scenario in a "
                                "player with a meaningful scoring total rather than one or two points."
                            ),
                        },
                        "min_scoring_events": {
                            "type": "integer",
                            "description": (
                                "If set, only players credited with at least this many entries in the "
                                "scoring_history of their games. Useful for grounding a get_game_timeline "
                                "scenario where the customer asks about their own baskets in the play-by-play."
                            ),
                        },
                        "min_games": {
                            "type": "integer",
                            "description": (
                                "If set, only players who appear in at least this many games. Use it when the "
                                "scenario compares performance across multiple games or needs a fuller schedule."
                            ),
                        },
                        "contract_source": {
                            "type": "string",
                            "enum": ["draft", "trade", "free agency"],
                            "description": (
                                "If set, only players with at least one contract acquired this way. Useful for "
                                "grounding a natural-language framing of how the player joined the club, e.g. "
                                "'since I was traded here' (trade) or 'since I was drafted' (draft)."
                            ),
                        },
                        "min_contracts": {
                            "type": "integer",
                            "description": (
                                "If set, only players with at least this many contracts on file. Use 2 or more "
                                "to find a player with a multi-club history, which supports scenarios about "
                                "moving between clubs; most players have exactly one contract."
                            ),
                        },
                        "position": {
                            "type": "string",
                            "enum": ["G", "F", "C", "G/F", "F/C", "C/F"],
                            "description": (
                                "If set, only players listed at this position on a club roster. Useful when the "
                                "scenario needs a specific role, e.g. a guard asking about assists or a center "
                                "asking about rebounds."
                            ),
                        },
                        "address_state": {
                            "type": "string",
                            "description": (
                                "If set, only players whose address.state matches exactly (e.g. 'CA', 'TX', "
                                "'ON'). Useful for a modify_player_address relocation scenario ('I'm moving out "
                                "of state') and for the policy's name + ZIP authentication path, which verifies "
                                "the caller against the address on file."
                            ),
                        },
                        "min_club_final_games": {
                            "type": "integer",
                            "description": (
                                "If set, only players on a club with at least this many games already in 'final' "
                                "status. get_club_record only counts final games, so a club with none returns a "
                                "0-0 record; use 1 or more to ground a win-loss record question in real results."
                            ),
                        },
                    },
                    "required": [],
                },
            },
        }
