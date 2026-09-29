import json
import random
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool

# Max number of students to return per call (paginated batch)
_MAX_STUDENTS = 5

# Call counter: each invoke returns the "next" batch so subsequent calls get different students
_call_counter = 0


def _student_registrations(
    student: Dict[str, Any], registrations: Dict[str, Any]
) -> List[Dict[str, Any]]:
    return [
        registrations[rid]
        for rid in student.get("registrations", [])
        if rid in registrations
    ]


def _has_payment_method_source(student: Dict[str, Any], source: str) -> bool:
    return any(
        pm.get("source") == source for pm in student.get("payment_methods", {}).values()
    )


def _has_registration_field(regs: List[Dict[str, Any]], field: str, value: str) -> bool:
    return any(r.get(field) == value for r in regs)


def _has_min_registered_courses(regs: List[Dict[str, Any]], n: int) -> bool:
    return any(len(r.get("courses", [])) >= n for r in regs)


def _has_grading_option(regs: List[Dict[str, Any]], option: str) -> bool:
    return any(
        rc.get("grading_option") == option for r in regs for rc in r.get("courses", [])
    )


def _has_overload_credits(regs: List[Dict[str, Any]]) -> bool:
    return any(r.get("overload_credits", 0) > 0 for r in regs)


def _has_min_payments(regs: List[Dict[str, Any]], n: int) -> bool:
    return any(len(r.get("payment_history", [])) >= n for r in regs)


def _enrolled_courses(
    regs: List[Dict[str, Any]], courses: Dict[str, Any]
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for reg in regs:
        for rc in reg.get("courses", []):
            course = courses.get(rc.get("course_id"))
            if course is not None:
                out.append(course)
    return out


def _has_meeting_status(enrolled: List[Dict[str, Any]], status: str) -> bool:
    for course in enrolled:
        for record in course.get("dates", {}).values():
            if record.get("status") == status:
                return True
    return False


def _is_enrolled_in_full_course(enrolled: List[Dict[str, Any]]) -> bool:
    return any(c.get("current_enrollment", 0) >= c.get("capacity", 0) for c in enrolled)


class GetStudentCandidates(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        min_payment_methods: Optional[int] = None,
        payment_method_source: Optional[str] = None,
        registration_term: Optional[str] = None,
        study_level: Optional[str] = None,
        enrollment_status: Optional[str] = None,
        health_insurance: Optional[str] = None,
        min_registered_courses: Optional[int] = None,
        min_registrations: Optional[int] = None,
        grading_option: Optional[str] = None,
        has_overload_credits: Optional[bool] = None,
        min_payments_in_history: Optional[int] = None,
        enrolled_course_meeting_status: Optional[str] = None,
        enrolled_in_full_course: Optional[bool] = None,
    ) -> str:
        global _call_counter

        students: Dict[str, Any] = data.get("students") or {}
        registrations: Dict[str, Any] = data.get("registrations") or {}
        courses: Dict[str, Any] = data.get("courses") or {}

        candidates: List[Dict[str, Any]] = []

        for student_id, student in students.items():
            if min_payment_methods is not None:
                try:
                    if len(student.get("payment_methods", {})) < int(
                        min_payment_methods
                    ):
                        continue
                except (TypeError, ValueError):
                    pass
            if payment_method_source is not None and not _has_payment_method_source(
                student, payment_method_source
            ):
                continue

            regs = _student_registrations(student, registrations)
            if min_registrations is not None and len(regs) < int(min_registrations):
                continue
            if registration_term is not None and not _has_registration_field(
                regs, "term", registration_term
            ):
                continue
            if study_level is not None and not _has_registration_field(
                regs, "study_level", study_level
            ):
                continue
            if enrollment_status is not None and not _has_registration_field(
                regs, "status", enrollment_status
            ):
                continue
            if health_insurance is not None and not _has_registration_field(
                regs, "health_insurance", health_insurance
            ):
                continue
            if min_registered_courses is not None:
                try:
                    if not _has_min_registered_courses(
                        regs, int(min_registered_courses)
                    ):
                        continue
                except (TypeError, ValueError):
                    pass
            if grading_option is not None and not _has_grading_option(
                regs, grading_option
            ):
                continue
            if has_overload_credits is not None and bool(
                has_overload_credits
            ) != _has_overload_credits(regs):
                continue
            if min_payments_in_history is not None:
                try:
                    if not _has_min_payments(regs, int(min_payments_in_history)):
                        continue
                except (TypeError, ValueError):
                    pass

            enrolled = _enrolled_courses(regs, courses)
            if enrolled_course_meeting_status is not None and not _has_meeting_status(
                enrolled, enrolled_course_meeting_status
            ):
                continue
            if enrolled_in_full_course is not None and bool(
                enrolled_in_full_course
            ) != _is_enrolled_in_full_course(enrolled):
                continue

            name = student.get("name", {})
            display_name = (
                " ".join(
                    p for p in [name.get("first_name"), name.get("last_name")] if p
                ).strip()
                or "Unknown"
            )
            pair: Dict[str, Any] = {}
            if len(regs) >= 2:
                ordered = sorted(regs, key=lambda r: r.get("registration_id", ""))
                modify = next(
                    (
                        r
                        for r in ordered
                        if registration_term is None
                        or r.get("term") == registration_term
                    ),
                    ordered[0],
                )
                cancel = next(r for r in ordered if r is not modify)
                pair = {
                    "modify_target": {
                        "registration_id": modify.get("registration_id"),
                        "term": modify.get("term"),
                        "why": "matches your registration filters -> update_registration_courses target",
                    },
                    "cancel_target": {
                        "registration_id": cancel.get("registration_id"),
                        "term": cancel.get("term"),
                        "why_cancellable": "another registration of this student (cancel_registration has no state check)",
                    },
                }
            candidates.append(
                {
                    **pair,
                    "student_id": student_id,
                    "name": display_name,
                    "email": student.get("email", ""),
                    "registration_ids": list(student.get("registrations", [])),
                    "num_payment_methods": len(student.get("payment_methods", {})),
                    "terms": [r.get("term") for r in regs],
                    "study_levels": [r.get("study_level") for r in regs],
                    "num_registered_courses": sum(
                        len(r.get("courses", [])) for r in regs
                    ),
                    "total_credits": sum(r.get("total_credits", 0) for r in regs),
                    "num_payments_in_history": sum(
                        len(r.get("payment_history", [])) for r in regs
                    ),
                }
            )

        random.shuffle(candidates)
        total = len(candidates)
        if total == 0:
            return json.dumps(
                {"total_matching": 0, "returned_count": 0, "students": []}, indent=2
            )

        offset = (_call_counter * _MAX_STUDENTS) % total
        _call_counter += 1
        doubled = candidates + candidates
        batch = doubled[offset : offset + _MAX_STUDENTS]

        payload = {
            "total_matching": total,
            "returned_count": len(batch),
            "students": batch,
        }
        return json.dumps(payload, indent=2)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_student_candidates",
                "description": (
                    "Read-only roster of students matching zero or more filters, for finding a real student whose "
                    "data already satisfies a scenario precondition (e.g. a student with two saved payment methods "
                    "who can split a tuition charge, or a student enrolled in a course that actually had a canceled "
                    "meeting). All filter parameters are optional; when a filter is omitted, no constraint is "
                    "applied for that field. Filters combine with AND semantics — a student must satisfy every "
                    "filter provided to match. Registration-level and course-level filters are satisfied if ANY of "
                    "the student's registrations (or any course inside them) matches. Returns concise summaries "
                    "(student_id, name, email, registration_ids, and counts of payment methods / courses / "
                    "payments), not full records — use get_student_details, get_registration_details and "
                    "get_course_details for full details once a candidate student_id is chosen. The list is "
                    f"randomized; each call returns the next batch (up to {_MAX_STUDENTS} students, different from "
                    "previous calls)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "min_payment_methods": {
                            "type": "integer",
                            "description": (
                                "If set, only students with at least this many saved payment methods. Registration "
                                "payments must use saved payment methods and may be split across several so long as "
                                "the amounts sum exactly to the total due, so use 2 here to find a student who can "
                                "genuinely split a register_courses charge across two cards/accounts. Most students "
                                "have only one saved method, so this filter narrows the roster sharply."
                            ),
                        },
                        "payment_method_source": {
                            "type": "string",
                            "enum": ["credit_card", "bank_account"],
                            "description": (
                                "If set, only students with at least one saved payment method of this source. Useful "
                                "for grounding a task where the customer names the method in natural language, e.g. "
                                "'put it on my Visa' (credit_card) or 'take it from my checking account' "
                                "(bank_account)."
                            ),
                        },
                        "registration_term": {
                            "type": "string",
                            "enum": ["2025-SPRING", "2025-FALL"],
                            "description": (
                                "If set, only students with a registration in this term. Every course in a "
                                "registration must stay in the registration's own term and the term itself can never "
                                "be changed, so any add/drop story has to be grounded in the term the student is "
                                "actually registered for. The roster is heavily skewed toward 2025-SPRING."
                            ),
                        },
                        "study_level": {
                            "type": "string",
                            "enum": ["undergraduate", "graduate", "continuing_ed"],
                            "description": (
                                "If set, only students with a registration at this study level. Study level cannot be "
                                "changed on an existing registration and it drives the per-credit tuition rate, so "
                                "the tuition figures quoted in a story only add up if the level matches the real "
                                "registration."
                            ),
                        },
                        "enrollment_status": {
                            "type": "string",
                            "enum": ["full-time", "part-time"],
                            "description": (
                                "If set, only students with a registration in this enrollment status. Status is "
                                "computed by the system (full-time at 12+ total credits, otherwise part-time), so use "
                                "'full-time' to ground a story where dropping a course would push the student down to "
                                "part-time, or 'part-time' where adding one would push them up."
                            ),
                        },
                        "health_insurance": {
                            "type": "string",
                            "enum": ["yes", "no"],
                            "description": (
                                "If set, only students with a registration carrying this health insurance election. "
                                "The election adds a $300 fee and cannot be changed after the initial registration, "
                                "so use 'yes' to ground a question about that fee (or a refusal to remove it) in a "
                                "registration that really has it."
                            ),
                        },
                        "min_registrations": {
                            "type": "integer",
                            "description": (
                                "If set, only students holding at least this many registrations (different terms). "
                                "Use 2 when the trace cancels one registration and modifies another: the row then "
                                "carries modify_target and cancel_target (two DIFFERENT registration ids) -- copy both."
                            ),
                        },
                        "min_registered_courses": {
                            "type": "integer",
                            "description": (
                                "If set, only students with a registration holding at least this many courses. A drop "
                                "or a swap via update_registration_courses needs a registration that actually has "
                                "courses to drop — use 2 to leave the registration non-empty after a single drop, or "
                                "3 for a multi-course shuffle."
                            ),
                        },
                        "grading_option": {
                            "type": "string",
                            "enum": ["letter", "pass/fail", "audit"],
                            "description": (
                                "If set, only students with at least one registered course under this grading option. "
                                "Changing a grading option is an allowed modification, so use 'pass/fail' or 'audit' "
                                "to find a student who already has a non-default option to switch back to letter, or "
                                "'letter' for the reverse."
                            ),
                        },
                        "has_overload_credits": {
                            "type": "boolean",
                            "description": (
                                "If set, only students whose registration does (True) or does not (False) carry "
                                "overload credits, i.e. total credits above the standard load of 18. Overload is rare "
                                "in the data, so pass True only when the scenario genuinely needs an overloaded "
                                "student — the matching set is very small."
                            ),
                        },
                        "min_payments_in_history": {
                            "type": "integer",
                            "description": (
                                "If set, only students with a registration whose payment_history holds at least this "
                                "many entries. Cancelling a registration refunds every recorded payment as a separate "
                                "negative amount, so use 2 here to ground a cancellation story where the refund is "
                                "genuinely split across more than one payment method."
                            ),
                        },
                        "enrolled_course_meeting_status": {
                            "type": "string",
                            "enum": ["held", "canceled", "rescheduled"],
                            "description": (
                                "If set, only students enrolled in at least one course that has a per-date meeting "
                                "record with this status. get_course_meeting_status errors out unless the course has "
                                "a record on the requested date, so use 'canceled' or 'rescheduled' to ground a 'was "
                                "my class canceled?' story in a course whose calendar really shows one."
                            ),
                        },
                        "enrolled_in_full_course": {
                            "type": "boolean",
                            "description": (
                                "If set, only students who are (True) or are not (False) enrolled in a course that is "
                                "at capacity. Registration and course adds both fail when the target course is full, "
                                "so use True to ground a story about a sought-after, closed-out section, or False for "
                                "a student whose whole schedule still has open seats."
                            ),
                        },
                    },
                    "required": [],
                },
            },
        }
