from tracer.envs.school.tools.calculate import CalculateTool
from tracer.envs.school.tools.cancel_registration import CancelRegistrationTool
from tracer.envs.school.tools.get_course_details import GetCourseDetailsTool
from tracer.envs.school.tools.get_course_meeting_status import (
    GetCourseMeetingStatusTool,
)
from tracer.envs.school.tools.get_registration_details import GetRegistrationDetailsTool
from tracer.envs.school.tools.get_student_details import GetStudentDetailsTool
from tracer.envs.school.tools.list_courses_by_term import ListCoursesByTermTool
from tracer.envs.school.tools.list_departments import ListDepartmentsTool
from tracer.envs.school.tools.pay_registration import PayRegistrationTool
from tracer.envs.school.tools.register_courses import RegisterCoursesTool
from tracer.envs.school.tools.search_courses import SearchCoursesTool
from tracer.envs.school.tools.think import ThinkTool
from tracer.envs.school.tools.transfer_to_human_agents import TransferToHumanAgents
from tracer.envs.school.tools.update_registration_courses import (
    UpdateRegistrationCoursesTool,
)

ALL_TOOLS = [
    TransferToHumanAgents,
    GetStudentDetailsTool,
    GetCourseDetailsTool,
    GetRegistrationDetailsTool,
    ListDepartmentsTool,
    ListCoursesByTermTool,
    SearchCoursesTool,
    GetCourseMeetingStatusTool,
    RegisterCoursesTool,
    UpdateRegistrationCoursesTool,
    CancelRegistrationTool,
    PayRegistrationTool,
    CalculateTool,
    ThinkTool,
]
