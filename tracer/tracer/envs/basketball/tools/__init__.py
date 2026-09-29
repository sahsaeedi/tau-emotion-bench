from tracer.envs.basketball.tools.calculate import CalculateTool
from tracer.envs.basketball.tools.find_player_id_by_email import FindPlayerIdByEmailTool
from tracer.envs.basketball.tools.find_player_id_by_name import FindPlayerIdByNameTool
from tracer.envs.basketball.tools.get_club_details import GetClubDetailsTool
from tracer.envs.basketball.tools.get_club_record import GetClubRecordTool
from tracer.envs.basketball.tools.get_club_schedule import GetClubScheduleTool
from tracer.envs.basketball.tools.get_game_box_score import GetGameBoxScoreTool
from tracer.envs.basketball.tools.get_game_details import GetGameDetailsTool
from tracer.envs.basketball.tools.get_game_score import GetGameScoreTool
from tracer.envs.basketball.tools.get_game_timeline import GetGameTimelineTool
from tracer.envs.basketball.tools.get_player_details import GetPlayerDetailsTool
from tracer.envs.basketball.tools.get_player_total_points import (
    GetPlayerTotalPointsTool,
)
from tracer.envs.basketball.tools.list_all_clubs import ListAllClubsTool
from tracer.envs.basketball.tools.list_club_roster_ids import ListClubRosterIdsTool
from tracer.envs.basketball.tools.list_clubs_by_league import ListClubsByLeagueTool
from tracer.envs.basketball.tools.modify_player_address import ModifyPlayerAddressTool
from tracer.envs.basketball.tools.record_scoring_event import RecordScoringEventTool
from tracer.envs.basketball.tools.think import ThinkTool
from tracer.envs.basketball.tools.transfer_to_human_agents import (
    TransferToHumanAgentsTool,
)
from tracer.envs.basketball.tools.update_game_status import UpdateGameStatusTool

ALL_TOOLS = [
    CalculateTool,
    TransferToHumanAgentsTool,
    GetClubDetailsTool,
    GetPlayerDetailsTool,
    GetGameDetailsTool,
    ListAllClubsTool,
    ListClubsByLeagueTool,
    FindPlayerIdByEmailTool,
    FindPlayerIdByNameTool,
    ListClubRosterIdsTool,
    GetGameBoxScoreTool,
    GetClubScheduleTool,
    GetGameScoreTool,
    GetGameTimelineTool,
    GetPlayerTotalPointsTool,
    GetClubRecordTool,
    ModifyPlayerAddressTool,
    UpdateGameStatusTool,
    RecordScoringEventTool,
    ThinkTool,
]
