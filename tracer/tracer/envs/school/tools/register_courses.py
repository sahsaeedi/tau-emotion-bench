import json
import uuid
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool


def _new_registration_id(data: Dict[str, Any]) -> str:
    while True:
        rid = "REG" + uuid.uuid4().hex[:8].upper()
        if rid not in data["registrations"]:
            return rid


def _get_datetime_short() -> str:
    """Return a created_at date string matching the model format YY-MM-DD."""
    # Keep static for deterministic behavior in tests
    return "25-05-15"


def _per_credit_rate(study_level: str) -> int:
    # Example per-credit rates; adjust as needed.
    rates = {
        "undergraduate": 500,
        "graduate": 800,
        "continuing_ed": 400,
    }
    return rates[study_level]


def _compute_course_tuition(course: Dict[str, Any], study_level: str) -> int:
    return course["credits"] * _per_credit_rate(study_level)


def _build_registration_course(
    course: Dict[str, Any], grading_option: str, study_level: str
) -> Dict[str, Any]:
    return {
        "course_id": course["course_id"],
        "course_code": course["course_code"],
        "section": "001",
        "title": course["title"],
        "credits": course["credits"],
        "grading_option": grading_option,
        "tuition": _compute_course_tuition(course, study_level),
    }


def _credits_to_status(total_credits: int) -> str:
    return "full-time" if total_credits >= 12 else "part-time"


def _overload_credits(total_credits: int) -> int:
    standard_load = 18
    return max(0, total_credits - standard_load)


def _parse_time_hhmm(hhmm: str) -> int:
    # "HH-MM" -> minutes since midnight
    parts = hhmm.split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {hhmm}")
    h = int(parts[0])
    m = int(parts[1])
    return h * 60 + m


def _times_overlap(s1: str, e1: str, s2: str, e2: str) -> bool:
    a1 = _parse_time_hhmm(s1)
    b1 = _parse_time_hhmm(e1)
    a2 = _parse_time_hhmm(s2)
    b2 = _parse_time_hhmm(e2)
    return a1 < b2 and a2 < b1


def _meeting_conflict(m1: Dict[str, Any], m2: Dict[str, Any]) -> bool:
    # Conflict if any day overlaps and times overlap
    set_days = set(m1["days"]).intersection(set(m2["days"]))
    if not set_days:
        return False
    return _times_overlap(
        m1["start_time_est"],
        m1["end_time_est"],
        m2["start_time_est"],
        m2["end_time_est"],
    )


def _find_conflicting_pair(
    courses: List[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    for i in range(len(courses)):
        for j in range(i + 1, len(courses)):
            if _meeting_conflict(
                courses[i]["meeting_pattern"], courses[j]["meeting_pattern"]
            ):
                return [courses[i], courses[j]]
    return None


def _find_missing_payment_method(
    student: Dict[str, Any], payments: List[Dict[str, Any]]
) -> Optional[str]:
    for p in payments:
        if p["payment_id"] not in student["payment_methods"]:
            return p["payment_id"]
    return None


def _health_insurance_fee(health_insurance: str) -> int:
    return 300 if health_insurance == "yes" else 0


class RegisterCoursesTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        student_id: str,
        term: str,
        course_ids: List[str],
        study_level: str,
        grading_options: Optional[Dict[str, str]] = None,
        health_insurance: str = "no",
        payment_methods: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        payment_methods = payment_methods or []

        student = data["students"].get(student_id)
        if student is None:
            return f"Error: Student {student_id} not found"

        courses = []
        for cid in course_ids:
            c = data["courses"].get(cid)
            if c is None:
                return f"Error: Course {cid} not found"
            courses.append(c)

        # Term validation
        for c in courses:
            if c["term"] != term:
                return f"Error: Course {c['course_id']} term {c['term']} does not match requested term {term}"

        # Capacity check
        for c in courses:
            if c["current_enrollment"] >= c["capacity"]:
                return f"Error: Course {c['course_code']} is full"

        # Time conflict check
        conflict = _find_conflicting_pair(courses)
        if conflict is not None:
            return f"Error: Schedule conflict between courses {conflict[0]['course_code']} and {conflict[1]['course_code']}"

        # Build registration courses
        reg_courses: List[Dict[str, Any]] = []
        total_credits = 0
        tuition_total = 0
        for c in courses:
            go = "letter"
            if grading_options and c["course_id"] in grading_options:
                go = grading_options[c["course_id"]]
            rc = _build_registration_course(c, go, study_level)
            reg_courses.append(rc)
            total_credits += rc["credits"]
            tuition_total += rc["tuition"]

        # Add fees
        insurance_fee = _health_insurance_fee(health_insurance)
        total_due = tuition_total + insurance_fee

        # Validate payments
        missing = _find_missing_payment_method(student, payment_methods)
        if missing is not None:
            return f"Error: Payment method {missing} not found for student {student_id}"
        total_paid = sum(p["amount"] for p in payment_methods)
        if total_paid != total_due:
            return f"Error: Payment amount does not add up, total due is {total_due}, but paid {total_paid}"

        # Create registration
        registration_id = _new_registration_id(data)
        campus = courses[0]["location"]["campus"] if courses else "Main"
        status = _credits_to_status(total_credits)
        overload = _overload_credits(total_credits)
        registration = {
            "registration_id": registration_id,
            "student_id": student_id,
            "campus": campus,
            "program": f"{student['program']['degree']} {student['program']['major']}",
            "study_level": study_level,
            "term": term,
            "status": status,
            "courses": reg_courses,
            "advisors": [],
            "payment_history": [dict(p) for p in payment_methods],
            "created_at": _get_datetime_short(),
            "total_credits": total_credits,
            "overload_credits": overload,
            "financial_aid": {"scholarships": 0, "grants": 0, "loans": 0},
            "health_insurance": health_insurance,
        }

        # Update DB: increment enrollments, save registration, link to student
        for c in courses:
            c["current_enrollment"] += 1

        data["registrations"][registration_id] = registration
        data["students"][student_id]["registrations"].append(registration_id)
        return json.dumps(registration)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "register_courses",
                "description": (
                    "Create a new registration for a student for a given term. Checks capacity and "
                    "time conflicts, computes tuition, and validates that payments equal total charges. "
                    "Increments course enrollments on success. The agent needs to list the proposed "
                    "registration details and obtain explicit user confirmation (yes/no) before calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "student_id": {
                            "type": "string",
                            "description": "The ID of the student.",
                        },
                        "term": {
                            "type": "string",
                            "description": "Term in the format YYYY-TERM.",
                        },
                        "course_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of course IDs to register.",
                        },
                        "study_level": {
                            "type": "string",
                            "enum": ["undergraduate", "graduate", "continuing_ed"],
                            "description": "Study level.",
                        },
                        "grading_options": {
                            "type": "object",
                            "description": (
                                "Optional map from course_id to grading option "
                                '("letter", "pass/fail", "audit"). Defaults to "letter".'
                            ),
                        },
                        "health_insurance": {
                            "type": "string",
                            "enum": ["yes", "no"],
                            "description": "Whether the student elects health insurance through the school.",
                        },
                        "payment_methods": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "payment_id": {
                                        "type": "string",
                                        "description": "Saved payment method ID.",
                                    },
                                    "amount": {
                                        "type": "integer",
                                        "description": "Amount to charge in dollars.",
                                    },
                                },
                            },
                            "description": "List of payment method entries (payment_id, amount) covering the total due.",
                        },
                    },
                    "required": ["student_id", "term", "course_ids", "study_level"],
                },
            },
        }
