"""Toolkit for the school domain, ported from TRACER's environment
(tracer/tracer/envs/school/).

13 tools: one per tool module in tracer/tracer/envs/school/tools/, plus
`calculate` and `think`. Conversion rules from TRACER's tools:

- `data["courses"]` → `self.db.courses`.
- `return json.dumps(x)` → return the pydantic record.
- `return "Error: ..."` → `raise ValueError("...")`.
- Free-function `invoke(data, ...)` → instance method with `@is_tool(...)`.

New registration ids are the first free `REG000001`-style id, so the
ground-truth replay and the agent's run assign the same ids and test tasks can
refer to an id created earlier in the same task. TRACER's tool uses random
uuid-based ids.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from tau_emotion.domains.school.data_model import (
    Course,
    CourseMeeting,
    Payment,
    Registration,
    RegistrationCourse,
    SchoolDB,
    Student,
)
from tau_emotion.environment.toolkit import ToolKitBase, ToolType, is_tool

# Tuition is priced per credit, by study level.
PER_CREDIT_RATE = {
    "undergraduate": 500,
    "graduate": 800,
    "continuing_ed": 400,
}
HEALTH_INSURANCE_FEE = 300
FULL_TIME_CREDITS = 12
STANDARD_LOAD_CREDITS = 18
DEFAULT_GRADING_OPTION = "letter"
# TRACER keeps this static so behaviour stays deterministic across runs.
REGISTRATION_CREATED_AT = "25-05-15"


def _parse_time_hhmm(hhmm: str) -> int:
    """Convert an "HH-MM" time string (TRACER's format) to minutes since midnight."""
    parts = hhmm.split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {hhmm}")
    return int(parts[0]) * 60 + int(parts[1])


def _times_overlap(s1: str, e1: str, s2: str, e2: str) -> bool:
    a1, b1 = _parse_time_hhmm(s1), _parse_time_hhmm(e1)
    a2, b2 = _parse_time_hhmm(s2), _parse_time_hhmm(e2)
    return a1 < b2 and a2 < b1


# TRACER declares these as enums in its tool schemas, so the agent is told the
# allowed values; the strings go into the database as given.
WeekDay = Literal[
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
StudyLevel = Literal["undergraduate", "graduate", "continuing_ed"]
YesNo = Literal["yes", "no"]


class SchoolTools(ToolKitBase):
    """All the tools for the school domain."""

    db: SchoolDB

    def __init__(self, db: SchoolDB) -> None:
        super().__init__(db)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_student(self, student_id: str) -> Student:
        student = self.db.students.get(student_id)
        if student is None:
            raise ValueError(f"Student {student_id} not found")
        return student

    def _get_course(self, course_id: str) -> Course:
        course = self.db.courses.get(course_id)
        if course is None:
            raise ValueError(f"Course {course_id} not found")
        return course

    def _get_registration(self, registration_id: str) -> Registration:
        reg = self.db.registrations.get(registration_id)
        if reg is None:
            raise ValueError(f"Registration {registration_id} not found")
        return reg

    def _new_registration_id(self) -> str:
        """First free id of the form REG000001."""
        n = 1
        while f"REG{n:06d}" in self.db.registrations:
            n += 1
        return f"REG{n:06d}"

    def _course_tuition(self, course: Course, study_level: str) -> int:
        if study_level not in PER_CREDIT_RATE:
            raise ValueError(
                f"Invalid study level: {study_level}. "
                f"Must be one of {sorted(PER_CREDIT_RATE)}."
            )
        return course.credits * PER_CREDIT_RATE[study_level]

    def _build_registration_course(
        self, course: Course, grading_option: str, study_level: str
    ) -> RegistrationCourse:
        return RegistrationCourse(
            course_id=course.course_id,
            course_code=course.course_code,
            section="001",
            title=course.title,
            credits=course.credits,
            grading_option=grading_option,
            tuition=self._course_tuition(course, study_level),
        )

    @staticmethod
    def _credits_to_status(total_credits: int) -> str:
        return "full-time" if total_credits >= FULL_TIME_CREDITS else "part-time"

    @staticmethod
    def _overload_credits(total_credits: int) -> int:
        return max(0, total_credits - STANDARD_LOAD_CREDITS)

    @staticmethod
    def _find_conflicting_pair(
        courses: List[Course],
    ) -> Optional[tuple[Course, Course]]:
        """Return the first pair of courses that share a day and overlap in time."""
        for i in range(len(courses)):
            for j in range(i + 1, len(courses)):
                m1, m2 = courses[i].meeting_pattern, courses[j].meeting_pattern
                if not set(m1.days) & set(m2.days):
                    continue
                if _times_overlap(
                    m1.start_time_est,
                    m1.end_time_est,
                    m2.start_time_est,
                    m2.end_time_est,
                ):
                    return courses[i], courses[j]
        return None

    # ------------------------------------------------------------------
    # Read tools
    # ------------------------------------------------------------------

    @is_tool(ToolType.READ)
    def get_student_details(self, student_id: str) -> Student:
        """
        Get the details of a student.

        Args:
            student_id: The student id.

        Returns:
            The student details.

        Raises:
            ValueError: If the student is not found.
        """
        return self._get_student(student_id)

    @is_tool(ToolType.READ)
    def get_course_details(self, course_id: str) -> Course:
        """
        Get the details of a course.

        Args:
            course_id: The course id.

        Returns:
            The course details.

        Raises:
            ValueError: If the course is not found.
        """
        return self._get_course(course_id)

    @is_tool(ToolType.READ)
    def get_registration_details(self, registration_id: str) -> Registration:
        """
        Get the details of a registration.

        Args:
            registration_id: The registration id.

        Returns:
            The registration details.

        Raises:
            ValueError: If the registration is not found.
        """
        return self._get_registration(registration_id)

    @is_tool(ToolType.READ)
    def list_departments(self) -> List[str]:
        """
        List all unique departments.

        Returns:
            The sorted list of department codes that offer at least one course.
        """
        return sorted({c.department for c in self.db.courses.values()})

    @is_tool(ToolType.READ)
    def list_courses_by_term(self, term: str) -> List[dict]:
        """
        List all courses for a given term.

        Args:
            term: Term in the format YYYY-TERM, e.g. 2025-SPRING.

        Returns:
            A list of {course_id, course_code, title} for courses in that term.
        """
        return [
            {
                "course_id": c.course_id,
                "course_code": c.course_code,
                "title": c.title,
            }
            for c in self.db.courses.values()
            if c.term == term
        ]

    @is_tool(ToolType.READ)
    def search_courses(
        self,
        term: str,
        department: Optional[str] = None,
        campus: Optional[str] = None,
        day: Optional[WeekDay] = None,
        start_after: Optional[str] = None,
        end_before: Optional[str] = None,
        open_only: bool = False,
    ) -> List[Course]:
        """
        Search for courses with common filters.

        Args:
            term: Term in the format YYYY-TERM.
            department: Optional department code to filter.
            campus: Optional campus name to filter.
            day: Optional day of week filter, e.g. 'Monday'.
            start_after: Optional earliest start time ("HH-MM").
            end_before: Optional latest end time ("HH-MM").
            open_only: If True, only return courses with open seats.

        Returns:
            The list of matching courses.

        Raises:
            ValueError: If a time filter is not in "HH-MM" format.
        """
        results: List[Course] = []
        for c in self.db.courses.values():
            if c.term != term:
                continue
            if department and c.department != department:
                continue
            if campus and c.location.campus != campus:
                continue
            if day and day not in c.meeting_pattern.days:
                continue
            if start_after and _parse_time_hhmm(
                c.meeting_pattern.start_time_est
            ) < _parse_time_hhmm(start_after):
                continue
            if end_before and _parse_time_hhmm(
                c.meeting_pattern.end_time_est
            ) > _parse_time_hhmm(end_before):
                continue
            if open_only and c.current_enrollment >= c.capacity:
                continue
            results.append(c)
        return results

    @is_tool(ToolType.READ)
    def get_course_meeting_status(self, course_id: str, date: str) -> CourseMeeting:
        """
        Get the per-date meeting status for a course.

        Args:
            course_id: Course ID.
            date: Date key in the format YY-MM-DD.

        Returns:
            The meeting record for that date, including whether it was held.

        Raises:
            ValueError: If the course is not found, or has no record for the date.
        """
        course = self._get_course(course_id)
        if date not in course.dates:
            raise ValueError(f"No record for course {course_id} on date {date}")
        return course.dates[date]

    # ------------------------------------------------------------------
    # Write tools
    # ------------------------------------------------------------------

    @is_tool(ToolType.WRITE)
    def register_courses(
        self,
        student_id: str,
        term: str,
        course_ids: List[str],
        study_level: StudyLevel,
        grading_options: Optional[Dict[str, str]] = None,
        health_insurance: YesNo = "no",
        payment_methods: Optional[List[Dict]] = None,
    ) -> Registration:
        """
        Create a new registration for a student for a given term.

        Checks capacity and time conflicts, computes tuition, and validates that
        payments equal total charges. Increments course enrollments on success.
        The agent needs to list the proposed registration details and obtain
        explicit user confirmation (yes/no) before calling.

        Args:
            student_id: The ID of the student.
            term: Term in the format YYYY-TERM.
            course_ids: List of course IDs to register.
            study_level: Study level, one of 'undergraduate', 'graduate', 'continuing_ed'.
            grading_options: Optional map from course_id to grading option
                ('letter', 'pass/fail', 'audit'). Defaults to 'letter'.
            health_insurance: Whether the student elects health insurance
                through the school, 'yes' or 'no'.
            payment_methods: List of {payment_id, amount} entries covering the total due.

        Returns:
            The newly created registration.

        Raises:
            ValueError: If the student or a course is not found, a course is in
                the wrong term or full, the schedule conflicts, a payment method
                is unknown, or the payments do not sum to the total due.
        """
        payments = payment_methods or []
        student = self._get_student(student_id)

        courses = [self._get_course(cid) for cid in course_ids]

        for c in courses:
            if c.term != term:
                raise ValueError(
                    f"Course {c.course_id} term {c.term} does not match "
                    f"requested term {term}"
                )
        for c in courses:
            if c.current_enrollment >= c.capacity:
                raise ValueError(f"Course {c.course_code} is full")

        conflict = self._find_conflicting_pair(courses)
        if conflict is not None:
            raise ValueError(
                f"Schedule conflict between courses {conflict[0].course_code} "
                f"and {conflict[1].course_code}"
            )

        reg_courses: List[RegistrationCourse] = []
        total_credits = 0
        tuition_total = 0
        for c in courses:
            go = (grading_options or {}).get(c.course_id, DEFAULT_GRADING_OPTION)
            rc = self._build_registration_course(c, go, study_level)
            reg_courses.append(rc)
            total_credits += rc.credits
            tuition_total += rc.tuition

        total_due = tuition_total + (
            HEALTH_INSURANCE_FEE if health_insurance == "yes" else 0
        )

        for p in payments:
            if p["payment_id"] not in student.payment_methods:
                raise ValueError(
                    f"Payment method {p['payment_id']} not found for "
                    f"student {student_id}"
                )
        total_paid = sum(p["amount"] for p in payments)
        if total_paid != total_due:
            raise ValueError(
                f"Payment amount does not add up, total due is {total_due}, "
                f"but paid {total_paid}"
            )

        registration_id = self._new_registration_id()
        registration = Registration(
            registration_id=registration_id,
            student_id=student_id,
            campus=courses[0].location.campus if courses else "Main",
            program=f"{student.program.degree} {student.program.major}",
            study_level=study_level,
            term=term,
            status=self._credits_to_status(total_credits),
            courses=reg_courses,
            advisors=[],
            payment_history=[Payment(**p) for p in payments],
            created_at=REGISTRATION_CREATED_AT,
            total_credits=total_credits,
            overload_credits=self._overload_credits(total_credits),
            health_insurance=health_insurance,
        )

        for c in courses:
            c.current_enrollment += 1
        self.db.registrations[registration_id] = registration
        student.registrations.append(registration_id)
        return registration

    @is_tool(ToolType.WRITE)
    def update_registration_courses(
        self,
        registration_id: str,
        add_course_ids: List[str],
        drop_course_ids: List[str],
        grading_options: Optional[Dict[str, str]] = None,
        payment_id: str = "",
    ) -> Registration:
        """
        Add and/or drop courses on an existing registration, handling tuition differences.

        Checks capacity for added courses and schedule conflicts against the final
        schedule, adjusts course enrollments, computes the tuition difference and
        records a payment (positive charge) or refund (negative amount). The agent
        needs to list the planned changes and obtain explicit user confirmation
        (yes/no) before calling.

        Args:
            registration_id: Existing registration ID.
            add_course_ids: Course IDs to add.
            drop_course_ids: Course IDs to drop.
            grading_options: Optional map from course_id to grading option.
            payment_id: Student's saved payment method ID to use for additional charges.

        Returns:
            The updated registration.

        Raises:
            ValueError: If the registration, student or a course is not found, a
                course is in the wrong term or full, the final schedule conflicts,
                or a payment method is missing or unknown when a charge is due.
        """
        reg = self._get_registration(registration_id)
        student = self._get_student(reg.student_id)

        current_ids = [rc.course_id for rc in reg.courses]
        drop_set = set(drop_course_ids)
        target_ids = [cid for cid in current_ids if cid not in drop_set]
        for cid in add_course_ids:
            if cid not in target_ids:
                target_ids.append(cid)

        current_courses = [self._get_course(cid) for cid in current_ids]
        target_courses = [self._get_course(cid) for cid in target_ids]

        for c in target_courses:
            if c.term != reg.term:
                raise ValueError(
                    f"Course {c.course_id} term {c.term} does not match "
                    f"registration term {reg.term}"
                )
        for cid in add_course_ids:
            c = self._get_course(cid)
            if c.current_enrollment >= c.capacity:
                raise ValueError(f"Course {c.course_code} is full")

        conflict = self._find_conflicting_pair(target_courses)
        if conflict is not None:
            raise ValueError(
                f"Schedule conflict between courses {conflict[0].course_code} "
                f"and {conflict[1].course_code}"
            )

        old_tuition = sum(rc.tuition for rc in reg.courses)

        new_reg_courses: List[RegistrationCourse] = []
        new_tuition = 0
        new_credits = 0
        for c in target_courses:
            go = (grading_options or {}).get(c.course_id, DEFAULT_GRADING_OPTION)
            rc = self._build_registration_course(c, go, reg.study_level)
            new_reg_courses.append(rc)
            new_tuition += rc.tuition
            new_credits += rc.credits

        tuition_diff = new_tuition - old_tuition
        if tuition_diff > 0:
            if payment_id == "":
                raise ValueError("payment_id is required for additional charges")
            if payment_id not in student.payment_methods:
                raise ValueError(
                    f"Payment method {payment_id} not found for "
                    f"student {student.student_id}"
                )
            reg.payment_history.append(
                Payment(payment_id=payment_id, amount=tuition_diff)
            )
        elif tuition_diff < 0:
            refund_payment_id = payment_id or (
                reg.payment_history[-1].payment_id
                if reg.payment_history
                else "adjustment"
            )
            reg.payment_history.append(
                Payment(payment_id=refund_payment_id, amount=tuition_diff)
            )

        dropped, added = set(drop_course_ids), set(add_course_ids)
        for c in current_courses:
            if c.course_id in dropped:
                c.current_enrollment = max(0, c.current_enrollment - 1)
        for c in target_courses:
            if c.course_id in added:
                c.current_enrollment += 1

        reg.courses = new_reg_courses
        reg.total_credits = new_credits
        reg.overload_credits = self._overload_credits(new_credits)
        reg.status = self._credits_to_status(new_credits)
        return reg

    @is_tool(ToolType.WRITE)
    def cancel_registration(self, registration_id: str) -> Registration:
        """
        Cancel a registration.

        Issues refunds for all recorded payments (as negative amounts), drops all
        courses and updates enrollments, and sets total credits and overload
        credits to 0. The registration remains in the system with an empty course
        list. The agent needs to present a summary of the cancellation effects and
        obtain explicit user confirmation (yes/no) before calling.

        Args:
            registration_id: The registration id to cancel.

        Returns:
            The cancelled registration.

        Raises:
            ValueError: If the registration is not found.
        """
        reg = self._get_registration(registration_id)

        refunds = [
            Payment(payment_id=p.payment_id, amount=-p.amount)
            for p in reg.payment_history
        ]
        reg.payment_history.extend(refunds)

        for rc in reg.courses:
            course = self.db.courses.get(rc.course_id)
            if course is not None:
                course.current_enrollment = max(0, course.current_enrollment - 1)

        reg.courses = []
        reg.total_credits = 0
        reg.overload_credits = 0
        reg.status = self._credits_to_status(0)
        return reg

    @is_tool(ToolType.WRITE)
    def pay_registration(self, registration_id: str, payment: Dict) -> Registration:
        """
        Record a payment (or a refund, with a negative amount) for a registration.

        Args:
            registration_id: The registration ID.
            payment: Payment object with payment_id and amount, where amount is
                in dollars and negative for a refund.

        Returns:
            The updated registration.

        Raises:
            ValueError: If the registration or student is not found, or the
                payment method is not one of the student's saved methods.
        """
        reg = self._get_registration(registration_id)
        student = self._get_student(reg.student_id)

        if payment.get("payment_id") not in student.payment_methods:
            raise ValueError(
                f"Payment method {payment.get('payment_id')} not found for "
                f"student {student.student_id}"
            )
        reg.payment_history.append(Payment(**payment))
        return reg

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
