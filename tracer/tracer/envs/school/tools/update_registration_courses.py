import json
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool


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


class UpdateRegistrationCoursesTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        registration_id: str,
        add_course_ids: List[str],
        drop_course_ids: List[str],
        grading_options: Optional[Dict[str, str]] = None,
        payment_id: str = "",
    ) -> str:
        reg = data["registrations"].get(registration_id)
        if reg is None:
            return f"Error: Registration {registration_id} not found"
        student = data["students"].get(reg["student_id"])
        if student is None:
            return f"Error: Student {reg['student_id']} not found"

        # Current and target course sets
        current_ids = [rc["course_id"] for rc in reg["courses"]]
        drop_set = set(drop_course_ids)
        target_ids = [cid for cid in current_ids if cid not in drop_set]
        for cid in add_course_ids:
            if cid not in target_ids:
                target_ids.append(cid)

        # Load courses
        current_courses = []
        for cid in current_ids:
            c = data["courses"].get(cid)
            if c is None:
                return f"Error: Course {cid} not found"
            current_courses.append(c)

        target_courses = []
        for cid in target_ids:
            c = data["courses"].get(cid)
            if c is None:
                return f"Error: Course {cid} not found"
            target_courses.append(c)

        # Validate term consistency
        for c in target_courses:
            if c["term"] != reg["term"]:
                return f"Error: Course {c['course_id']} term {c['term']} does not match registration term {reg['term']}"

        # Capacity check for added courses
        for cid in add_course_ids:
            c = data["courses"].get(cid)
            if c is None:
                return f"Error: Course {cid} not found"
            if c["current_enrollment"] >= c["capacity"]:
                return f"Error: Course {c['course_code']} is full"

        # Time conflict check against the final schedule
        conflict = _find_conflicting_pair(target_courses)
        if conflict is not None:
            return f"Error: Schedule conflict between courses {conflict[0]['course_code']} and {conflict[1]['course_code']}"

        # Compute old and new tuition totals
        old_tuition = sum(rc["tuition"] for rc in reg["courses"])

        new_reg_courses: List[Dict[str, Any]] = []
        new_tuition = 0
        new_credits = 0

        for c in target_courses:
            go = "letter"
            if grading_options and c["course_id"] in grading_options:
                go = grading_options[c["course_id"]]
            rc = _build_registration_course(c, go, reg["study_level"])
            new_reg_courses.append(rc)
            new_tuition += rc["tuition"]
            new_credits += rc["credits"]

        # Tuition difference (insurance fee unchanged)
        tuition_diff = new_tuition - old_tuition

        # Create payment/refund entry if needed
        if tuition_diff != 0:
            if tuition_diff > 0:
                if payment_id == "":
                    return "Error: payment_id is required for additional charges"
                if payment_id not in student["payment_methods"]:
                    return f"Error: Payment method {payment_id} not found for student {student['student_id']}"
                reg["payment_history"].append(
                    {"payment_id": payment_id, "amount": tuition_diff}
                )
            else:
                # Refund
                refund_payment_id = payment_id or (
                    reg["payment_history"][-1]["payment_id"]
                    if reg["payment_history"]
                    else "adjustment"
                )
                reg["payment_history"].append(
                    {"payment_id": refund_payment_id, "amount": tuition_diff}
                )

        # Update enrollments: decrement dropped, increment added
        dropped = set(drop_course_ids)
        added = set(add_course_ids)
        for c in current_courses:
            if c["course_id"] in dropped:
                c["current_enrollment"] = max(0, c["current_enrollment"] - 1)
        for c in target_courses:
            if c["course_id"] in added:
                c["current_enrollment"] += 1

        # Update registration record
        reg["courses"] = new_reg_courses
        reg["total_credits"] = new_credits
        reg["overload_credits"] = _overload_credits(new_credits)
        reg["status"] = _credits_to_status(new_credits)

        return json.dumps(reg)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "update_registration_courses",
                "description": (
                    "Add and/or drop courses from an existing registration, handling tuition "
                    "differences. Checks capacity for added courses and schedule conflicts against the "
                    "final schedule, adjusts course enrollments, and computes the tuition difference "
                    "and records a payment (positive charge) or refund (negative charge). The agent "
                    "needs to list the planned changes and obtain explicit user confirmation (yes/no) "
                    "before calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "registration_id": {
                            "type": "string",
                            "description": "Existing registration ID.",
                        },
                        "add_course_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Course IDs to add.",
                        },
                        "drop_course_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Course IDs to drop.",
                        },
                        "grading_options": {
                            "type": "object",
                            "description": "Optional map from course_id to grading option.",
                        },
                        "payment_id": {
                            "type": "string",
                            "description": "Student's saved payment method ID to use for additional charges.",
                        },
                    },
                    "required": [
                        "registration_id",
                        "add_course_ids",
                        "drop_course_ids",
                    ],
                },
            },
        }
