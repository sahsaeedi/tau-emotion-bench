"""Toolkit for the basketball domain, ported from TRACER's environment
(tracer/tracer/envs/basketball/).

19 tools mirroring TRACER's `ALL_TOOLS`. Conversion rules from TRACER's tools:

- `data["clubs"]` → `self.db.clubs`.
- `return json.dumps(x)` → return the pydantic record.
- `return "Error: ..."` → `raise ValueError("...")`.
- Free-function `invoke(data, ...)` → instance method with `@is_tool(...)`.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from tau_emotion.domains.basketball.data_model import (
    BasketballDB,
    BoxScoreEntry,
    Club,
    Game,
    Player,
    ScoringEvent,
)
from tau_emotion.environment.toolkit import ToolKitBase, ToolType, is_tool

# Points a scoring event must be worth, by event type.
POINTS_BY_EVENT_TYPE = {"2PT": 2, "3PT": 3, "FT": 1}
# Which status a game may move to from its current one.
ALLOWED_STATUS_TRANSITIONS: Dict[str, List[str]] = {
    "scheduled": ["in_progress", "postponed"],
    "postponed": ["scheduled"],
    "in_progress": ["final"],
    "final": [],
}


# TRACER declares these as enums in its tool schemas, so the agent is told the
# allowed values; the strings go into the database as given.
GameStatus = Literal["scheduled", "in_progress", "final", "postponed"]
ScoringEventType = Literal["2PT", "3PT", "FT"]


class BasketballTools(ToolKitBase):
    """All the tools for the basketball domain."""

    db: BasketballDB

    def __init__(self, db: BasketballDB) -> None:
        super().__init__(db)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_player(self, player_id: str) -> Player:
        player = self.db.players.get(player_id)
        if player is None:
            raise ValueError("Player not found")
        return player

    def _get_club(self, club_id: str) -> Club:
        club = self.db.clubs.get(club_id)
        if club is None:
            raise ValueError("Club not found")
        return club

    def _get_game(self, game_id: str) -> Game:
        game = self.db.games.get(game_id)
        if game is None:
            raise ValueError("Game not found")
        return game

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    @is_tool(ToolType.READ)
    def get_player_details(self, player_id: str) -> Player:
        """
        Get the details of a player.

        Args:
            player_id: The player id, such as 'P7K2M9Q'.

        Returns:
            The player record, including contracts and games played.

        Raises:
            ValueError: If the player is not found.
        """
        return self._get_player(player_id)

    @is_tool(ToolType.READ)
    def get_club_details(self, club_id: str) -> Club:
        """
        Get the details of a club.

        Args:
            club_id: The club id, such as 'C4N8T2W'.

        Returns:
            The club record, including its arena and roster.

        Raises:
            ValueError: If the club is not found.
        """
        return self._get_club(club_id)

    @is_tool(ToolType.READ)
    def get_game_details(self, game_id: str) -> Game:
        """
        Get the details of a game.

        Args:
            game_id: The game id, such as 'G3H6R1Z'.

        Returns:
            The game record, including box score and scoring history.

        Raises:
            ValueError: If the game is not found.
        """
        return self._get_game(game_id)

    @is_tool(ToolType.READ)
    def find_player_id_by_email(self, email: str) -> str:
        """
        Find a player id by email address.

        Args:
            email: The player's email address, such as 'player@example.com'.

        Returns:
            The matching player id.

        Raises:
            ValueError: If no player has that email.
        """
        email_lower = email.lower()
        for player_id, player in self.db.players.items():
            if player.email.lower() == email_lower:
                return player_id
        raise ValueError("Player not found")

    @is_tool(ToolType.READ)
    def find_player_id_by_name(self, first_name: str, last_name: str) -> str:
        """
        Find a player id by first and last name.

        Args:
            first_name: The player's first name.
            last_name: The player's last name.

        Returns:
            The matching player id.

        Raises:
            ValueError: If no player matches, or more than one does.
        """
        first, last = first_name.lower(), last_name.lower()
        matches = [
            player_id
            for player_id, player in self.db.players.items()
            if player.name.first_name.lower() == first
            and player.name.last_name.lower() == last
        ]
        if not matches:
            raise ValueError("Player not found")
        if len(matches) > 1:
            raise ValueError("Multiple players found, please provide more information")
        return matches[0]

    @is_tool(ToolType.READ)
    def list_all_clubs(self) -> Dict[str, str]:
        """
        List every club.

        Note: the mapping is keyed by club name, so clubs that share a name
        collapse into a single entry (the shipped data has 240 clubs across
        only 30 distinct names). This is TRACER's behaviour, kept as-is.

        Returns:
            A mapping of club name to club id, sorted by name.
        """
        clubs = {club.name: club.club_id for club in self.db.clubs.values()}
        return dict(sorted(clubs.items()))

    @is_tool(ToolType.READ)
    def list_clubs_by_league(self, league: str) -> Dict[str, str]:
        """
        List the clubs in a league.

        Args:
            league: The league name. Matching is case-insensitive.

        Returns:
            A mapping of club name to club id, sorted by name.

        Raises:
            ValueError: If no clubs belong to that league.
        """
        league_lower = league.lower()
        clubs = {
            club.name: club.club_id
            for club in self.db.clubs.values()
            if club.league.lower() == league_lower
        }
        if not clubs:
            raise ValueError("No clubs found for the specified league")
        return dict(sorted(clubs.items()))

    @is_tool(ToolType.READ)
    def list_club_roster_ids(self, club_id: str, active_only: bool = True) -> List[str]:
        """
        List the player ids on a club's roster.

        Args:
            club_id: The club id, such as 'C4N8T2W'.
            active_only: If True, only include currently active players.

        Returns:
            The sorted list of player ids.

        Raises:
            ValueError: If the club is not found.
        """
        club = self._get_club(club_id)
        return sorted(
            player_id
            for player_id, entry in club.roster.items()
            if entry.active or not active_only
        )

    # ------------------------------------------------------------------
    # Game data
    # ------------------------------------------------------------------

    @is_tool(ToolType.READ)
    def get_game_score(self, game_id: str) -> dict:
        """
        Get the current score of a game.

        Args:
            game_id: The game id, such as 'G3H6R1Z'.

        Returns:
            The game status plus the home and away club ids, names and scores.

        Raises:
            ValueError: If the game is not found.
        """
        game = self._get_game(game_id)
        return {
            "status": game.status,
            "home": game.clubs.home.model_dump(),
            "away": game.clubs.away.model_dump(),
        }

    @is_tool(ToolType.READ)
    def get_game_box_score(self, game_id: str) -> List[BoxScoreEntry]:
        """
        Get the per-player box score for a game.

        Args:
            game_id: The game id, such as 'G3H6R1Z'.

        Returns:
            The box score entries.

        Raises:
            ValueError: If the game is not found.
        """
        return self._get_game(game_id).box_score

    @is_tool(ToolType.READ)
    def get_game_timeline(self, game_id: str) -> List[ScoringEvent]:
        """
        Get the scoring timeline for a game.

        Args:
            game_id: The game id, such as 'G3H6R1Z'.

        Returns:
            The scoring events in the order they were recorded.

        Raises:
            ValueError: If the game is not found.
        """
        return self._get_game(game_id).scoring_history

    @is_tool(ToolType.READ)
    def get_club_record(self, club_id: str, season: Optional[str] = None) -> dict:
        """
        Get a club's win/loss record.

        Only games with status 'final' are counted; a tie counts as neither a
        win nor a loss.

        Args:
            club_id: The club id, such as 'C4N8T2W'.
            season: Optional season to restrict the record to.

        Returns:
            The counts, as {wins, losses}.

        Raises:
            ValueError: If the club is not found.
        """
        club = self._get_club(club_id)
        wins = losses = 0
        for game_id in club.games:
            game = self.db.games.get(game_id)
            if game is None or game.status != "final":
                continue
            if season is not None and game.season != season:
                continue

            home, away = game.clubs.home, game.clubs.away
            if home.club_id == club_id:
                own, other = home.score, away.score
            elif away.club_id == club_id:
                own, other = away.score, home.score
            else:
                continue
            if own > other:
                wins += 1
            elif own < other:
                losses += 1
        return {"wins": wins, "losses": losses}

    @is_tool(ToolType.READ)
    def get_club_schedule(
        self,
        club_id: str,
        season: Optional[str] = None,
        status: Optional[GameStatus] = None,
    ) -> List[str]:
        """
        List the ids of a club's games.

        Args:
            club_id: The club id, such as 'C4N8T2W'.
            season: Optional season filter.
            status: Optional game status filter, e.g. 'final'.

        Returns:
            The matching game ids, in the club's own order.

        Raises:
            ValueError: If the club is not found.
        """
        club = self._get_club(club_id)
        schedule = []
        for game_id in club.games:
            game = self.db.games.get(game_id)
            if game is None:
                continue
            if season is not None and game.season != season:
                continue
            if status is not None and game.status != status:
                continue
            schedule.append(game_id)
        return schedule

    @is_tool(ToolType.READ)
    def get_player_total_points(
        self, player_id: str, season: Optional[str] = None
    ) -> str:
        """
        Total the points a player has scored, from the box scores of their games.

        Args:
            player_id: The player id, such as 'P7K2M9Q'.
            season: Optional season to restrict the total to.

        Returns:
            The total points, as a string.

        Raises:
            ValueError: If the player is not found.
        """
        player = self._get_player(player_id)
        total = 0
        for game_id in player.games:
            game = self.db.games.get(game_id)
            if game is None:
                continue
            if season is not None and game.season != season:
                continue
            total += sum(
                entry.points for entry in game.box_score if entry.player_id == player_id
            )
        return str(total)

    # ------------------------------------------------------------------
    # Write tools
    # ------------------------------------------------------------------

    @is_tool(ToolType.WRITE)
    def record_scoring_event(
        self,
        game_id: str,
        event_type: ScoringEventType,
        points: int,
        club_id: str,
        player_id: str,
        timestamp: str,
    ) -> Game:
        """
        Record a scoring event in a game that is in progress, updating the score.

        The agent needs to explain the details and ask for explicit user
        confirmation (yes/no) before calling.

        Args:
            game_id: The game id, such as 'G3H6R1Z'.
            event_type: The type of score, one of '2PT', '3PT', 'FT'.
            points: The points scored. Must match the event type.
            club_id: The club that scored. Must be one of the two clubs playing.
            player_id: The player who scored.
            timestamp: When the event occurred.

        Returns:
            The updated game.

        Raises:
            ValueError: If the game is not found or is not in progress, the
                event type is unknown, the points do not match it, the club is
                not in this game, or the player is not found.
        """
        game = self._get_game(game_id)
        if game.status != "in_progress":
            raise ValueError("Scoring can only be recorded for games in progress")

        expected_points = POINTS_BY_EVENT_TYPE.get(event_type)
        if expected_points is None:
            raise ValueError("Invalid event type")
        if points != expected_points:
            raise ValueError("Points do not match the event type")

        home_id = game.clubs.home.club_id
        away_id = game.clubs.away.club_id
        if club_id not in (home_id, away_id):
            raise ValueError("Club is not part of this game")
        self._get_player(player_id)

        game.scoring_history.append(
            ScoringEvent(
                event_type=event_type,
                points=points,
                club_id=club_id,
                player_id=player_id,
                timestamp=timestamp,
            )
        )
        if club_id == home_id:
            game.clubs.home.score += points
        else:
            game.clubs.away.score += points
        return game

    @is_tool(ToolType.WRITE)
    def update_game_status(self, game_id: str, new_status: GameStatus) -> Game:
        """
        Move a game to a new status.

        Permitted transitions are scheduled -> in_progress or postponed,
        postponed -> scheduled, and in_progress -> final. A game that is already
        final cannot change. Setting the status it already has does nothing. The
        agent needs to explain the change and ask for explicit user confirmation
        (yes/no) before calling.

        Args:
            game_id: The game id, such as 'G3H6R1Z'.
            new_status: The status to move to.

        Returns:
            The updated game.

        Raises:
            ValueError: If the game is not found, or the transition is not allowed.
        """
        game = self._get_game(game_id)
        if new_status == game.status:
            return game
        if new_status not in ALLOWED_STATUS_TRANSITIONS.get(game.status, []):
            raise ValueError("Invalid status transition")
        game.status = new_status
        return game

    @is_tool(ToolType.WRITE)
    def modify_player_address(
        self,
        player_id: str,
        street: str,
        city: str,
        state: str,
        country: str,
        zip: str,
    ) -> Player:
        """
        Update a player's address.

        The whole address is replaced. The agent needs to list the new address
        and ask for explicit user confirmation (yes/no) before calling.

        Args:
            player_id: The player id, such as 'P7K2M9Q'.
            street: The street address.
            city: The city.
            state: The state or province.
            country: The country.
            zip: The postal or ZIP code.

        Returns:
            The updated player.

        Raises:
            ValueError: If the player is not found.
        """
        player = self._get_player(player_id)
        player.address.street = street
        player.address.city = city
        player.address.state = state
        player.address.country = country
        player.address.zip = zip
        return player

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @is_tool(ToolType.THINK)
    def think(self, thought: str) -> str:
        """Use the tool to think about something. It will not obtain new
        information or change the database, but just append the thought to
        the log. Use it when complex reasoning or some cache memory is needed.

        Args:
            thought: A thought to think about.

        Returns:
            An empty string.
        """
        return ""

    @is_tool(ToolType.GENERIC)
    def calculate(self, expression: str) -> str:
        """
        Calculate the result of a mathematical expression.

        Args:
            expression: The mathematical expression to calculate, such as '2 + 2'. The expression can contain numbers, operators (+, -, *, /), parentheses, and spaces.

        Returns:
            The result of the mathematical expression.

        Raises:
            ValueError: If the expression is invalid.
        """
        if not all(char in "0123456789+-*/(). " for char in expression):
            raise ValueError("Invalid characters in expression")
        return str(round(float(eval(expression, {"__builtins__": None}, {})), 2))

    @is_tool(ToolType.GENERIC)
    def transfer_to_human_agents(self, summary: str) -> str:
        """
        Transfer the user to a human agent, with a summary of the user's issue.
        Only transfer if
         -  the user explicitly asks for a human agent
         -  given the policy and the available tools, you cannot solve the user's issue.

        Args:
            summary: A summary of the user's issue.

        Returns:
            A message indicating the user has been transferred to a human agent.
        """
        return "Transfer successful"
