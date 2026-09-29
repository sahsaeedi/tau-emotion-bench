from tracer.envs.airline.reverse_tools.think import Think  # no-op scratchpad, shared
from tracer.envs.school.reverse_tools.get_course_details import GetCourseDetailsTool
from tracer.envs.school.reverse_tools.get_course_meeting_status import (
    GetCourseMeetingStatusTool,
)
from tracer.envs.school.reverse_tools.get_registration_details import (
    GetRegistrationDetailsTool,
)
from tracer.envs.school.reverse_tools.get_student_candidates import GetStudentCandidates
from tracer.envs.school.reverse_tools.get_student_details import GetStudentDetailsTool
from tracer.envs.school.reverse_tools.list_courses_by_term import ListCoursesByTermTool
from tracer.envs.school.reverse_tools.list_departments import ListDepartmentsTool
from tracer.envs.school.reverse_tools.search_courses import SearchCoursesTool

ALL_TOOLS = [
    GetStudentDetailsTool,
    GetCourseDetailsTool,
    GetRegistrationDetailsTool,
    ListDepartmentsTool,
    ListCoursesByTermTool,
    SearchCoursesTool,
    GetCourseMeetingStatusTool,
    GetStudentCandidates,
    Think,
]
