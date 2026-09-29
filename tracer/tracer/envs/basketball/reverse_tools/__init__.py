from tracer.envs.airline.reverse_tools.think import Think  # no-op scratchpad, shared
from tracer.envs.basketball.reverse_tools.get_club_details import GetClubDetailsTool
from tracer.envs.basketball.reverse_tools.get_club_record import GetClubRecordTool
from tracer.envs.basketball.reverse_tools.get_club_schedule import GetClubScheduleTool
from tracer.envs.basketball.reverse_tools.get_game_box_score import GetGameBoxScoreTool
from tracer.envs.basketball.reverse_tools.get_game_details import GetGameDetailsTool
from tracer.envs.basketball.reverse_tools.get_game_score import GetGameScoreTool
from tracer.envs.basketball.reverse_tools.get_game_timeline import GetGameTimelineTool
from tracer.envs.basketball.reverse_tools.get_player_candidates import (
    GetPlayerCandidates,
)
from tracer.envs.basketball.reverse_tools.get_player_details import GetPlayerDetailsTool
from tracer.envs.basketball.reverse_tools.get_player_total_points import (
    GetPlayerTotalPointsTool,
)
from tracer.envs.basketball.reverse_tools.list_all_clubs import ListAllClubsTool
from tracer.envs.basketball.reverse_tools.list_club_roster_ids import (
    ListClubRosterIdsTool,
)
from tracer.envs.basketball.reverse_tools.list_clubs_by_league import (
    ListClubsByLeagueTool,
)

ALL_TOOLS = [
    GetPlayerDetailsTool,
    GetClubDetailsTool,
    GetGameDetailsTool,
    ListAllClubsTool,
    ListClubsByLeagueTool,
    ListClubRosterIdsTool,
    GetGameBoxScoreTool,
    GetClubScheduleTool,
    GetGameScoreTool,
    GetGameTimelineTool,
    GetPlayerTotalPointsTool,
    GetClubRecordTool,
    GetPlayerCandidates,
    Think,
]
