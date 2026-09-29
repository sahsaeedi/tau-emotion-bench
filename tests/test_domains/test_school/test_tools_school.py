"""Tests for the school domain, ported from TRACER\'s environment.

These run against the real data/tau_emotion/domains/school/db.json rather than
a synthetic fixture, so they also assert that the shipped data validates
against the pydantic models. Each test gets its own freshly loaded db, so
write tools cannot leak state between tests.
"""

import pytest

from tau_emotion.domains.school.data_model import SchoolDB
from tau_emotion.domains.school.environment import get_environment
from tau_emotion.domains.school.tools import SchoolTools
from tau_emotion.domains.school.utils import SCHOOL_DB_PATH

# Known-good records from the shipped db.json.
STUDENT_ID = "02WW7PC"
REGISTRATION_ID = "WR30HJH"
COURSE_ID = "FH4QYFJ"
COURSE_CODE = "ECON-3020"
TERM = "2025-SPRING"
OTHER_TERM = "2025-FALL"
MEETING_DATE = "25-01-23"

EXPECTED_TOOLS = {
    "calculate",
    "cancel_registration",
    "get_course_details",
    "get_course_meeting_status",
    "get_registration_details",
    "get_student_details",
    "list_courses_by_term",
    "list_departments",
    "pay_registration",
    "register_courses",
    "search_courses",
    "think",
    "update_registration_courses",
}


def _addable_course(tools: SchoolTools, registration_id: str):
    """An open course in the registration's term that fits its schedule."""
    reg = tools.get_registration_details(registration_id)
    existing = [tools.get_course_details(rc.course_id) for rc in reg.courses]
    held = {c.course_id for c in existing}
    return next(
        c
        for c in tools.search_courses(term=reg.term, open_only=True)
        if c.course_id not in held
        and tools._find_conflicting_pair(existing + [c]) is None
    )


@pytest.fixture
def db() -> SchoolDB:
    return SchoolDB.load(SCHOOL_DB_PATH)


@pytest.fixture
def tools(db: SchoolDB) -> SchoolTools:
    return SchoolTools(db)


def test_shipped_db_validates(db: SchoolDB):
    stats = db.get_statistics()
    assert stats["num_courses"] > 0
    assert stats["num_students"] > 0
    assert stats["num_registrations"] > 0


def test_environment_exposes_expected_tools():
    env = get_environment()
    assert set(env.tools.get_tools()) == EXPECTED_TOOLS
    assert env.domain_name == "school"
    assert env.policy.strip()


def test_every_tool_has_a_valid_openai_schema():
    env = get_environment()
    for name, tool in env.tools.get_tools().items():
        schema = tool.openai_schema
        assert schema["function"]["name"] == name
        assert schema["function"]["description"].strip(), f"{name} has no description"


def test_solo_mode_is_rejected():
    with pytest.raises(ValueError, match="solo mode"):
        get_environment(solo_mode=True)


# --- read tools ------------------------------------------------------------


def test_get_student_details(tools: SchoolTools):
    student = tools.get_student_details(STUDENT_ID)
    assert student.student_id == STUDENT_ID
    assert REGISTRATION_ID in student.registrations


def test_get_course_details(tools: SchoolTools):
    course = tools.get_course_details(COURSE_ID)
    assert course.course_id == COURSE_ID
    assert course.course_code == COURSE_CODE


def test_get_registration_details(tools: SchoolTools):
    reg = tools.get_registration_details(REGISTRATION_ID)
    assert reg.registration_id == REGISTRATION_ID
    assert reg.student_id == STUDENT_ID


def test_missing_records_raise(tools: SchoolTools):
    with pytest.raises(ValueError, match="not found"):
        tools.get_student_details("NOPE")
    with pytest.raises(ValueError, match="not found"):
        tools.get_course_details("NOPE")
    with pytest.raises(ValueError, match="not found"):
        tools.get_registration_details("NOPE")


def test_list_departments(tools: SchoolTools):
    departments = tools.list_departments()
    assert departments == sorted(set(departments)), "must be sorted and unique"
    assert tools.get_course_details(COURSE_ID).department in departments


def test_list_courses_by_term(tools: SchoolTools):
    listed = tools.list_courses_by_term(TERM)
    assert listed
    assert COURSE_ID in {c["course_id"] for c in listed}
    assert tools.list_courses_by_term("1999-WINTER") == []


def test_search_courses_filters(tools: SchoolTools):
    course = tools.get_course_details(COURSE_ID)
    by_term = tools.search_courses(term=TERM)
    assert course in by_term

    by_dept = tools.search_courses(term=TERM, department=course.department)
    assert all(c.department == course.department for c in by_dept)
    assert len(by_dept) <= len(by_term)

    open_only = tools.search_courses(term=TERM, open_only=True)
    assert all(c.current_enrollment < c.capacity for c in open_only)


def test_search_courses_rejects_bad_time_format(tools: SchoolTools):
    with pytest.raises(ValueError, match="Invalid time format"):
        tools.search_courses(term=TERM, start_after="09:00")


def test_get_course_meeting_status(tools: SchoolTools):
    meeting = tools.get_course_meeting_status(COURSE_ID, MEETING_DATE)
    assert meeting.status
    with pytest.raises(ValueError, match="No record"):
        tools.get_course_meeting_status(COURSE_ID, "99-99-99")


# --- write tools -----------------------------------------------------------


def test_pay_registration_appends_and_validates(tools: SchoolTools):
    reg = tools.get_registration_details(REGISTRATION_ID)
    before = len(reg.payment_history)
    payment_id = next(iter(tools.get_student_details(STUDENT_ID).payment_methods))

    updated = tools.pay_registration(
        REGISTRATION_ID, {"payment_id": payment_id, "amount": 100}
    )
    assert len(updated.payment_history) == before + 1
    assert updated.payment_history[-1].amount == 100

    with pytest.raises(ValueError, match="Payment method"):
        tools.pay_registration(
            REGISTRATION_ID, {"payment_id": "not_a_card", "amount": 1}
        )


def test_cancel_registration_refunds_and_drops(tools: SchoolTools):
    reg = tools.get_registration_details(REGISTRATION_ID)
    assert reg.payment_history, "fixture registration should have payments to refund"
    enrolled_before = {
        rc.course_id: tools.get_course_details(rc.course_id).current_enrollment
        for rc in reg.courses
    }

    cancelled = tools.cancel_registration(REGISTRATION_ID)

    assert cancelled.courses == []
    assert cancelled.total_credits == 0
    assert cancelled.overload_credits == 0
    assert cancelled.status == "part-time"
    # every prior payment is mirrored by a refund, so the net is zero
    assert sum(p.amount for p in cancelled.payment_history) == 0
    for course_id, before in enrolled_before.items():
        assert tools.get_course_details(course_id).current_enrollment == before - 1


def test_register_courses_happy_path(tools: SchoolTools):
    student = tools.get_student_details(STUDENT_ID)
    payment_id = next(iter(student.payment_methods))
    course = tools.search_courses(term=TERM, open_only=True)[0]
    tuition = course.credits * 500  # undergraduate rate
    before_enrollment = course.current_enrollment
    before_registrations = len(student.registrations)

    reg = tools.register_courses(
        student_id=STUDENT_ID,
        term=TERM,
        course_ids=[course.course_id],
        study_level="undergraduate",
        payment_methods=[{"payment_id": payment_id, "amount": tuition}],
    )

    assert reg.student_id == STUDENT_ID
    assert reg.term == TERM
    assert [rc.course_id for rc in reg.courses] == [course.course_id]
    assert reg.courses[0].tuition == tuition
    assert reg.courses[0].grading_option == "letter"
    assert reg.total_credits == course.credits
    assert tools.get_course_details(course.course_id).current_enrollment == (
        before_enrollment + 1
    )
    assert len(tools.get_student_details(STUDENT_ID).registrations) == (
        before_registrations + 1
    )
    # first free REG000001-style id, so replays assign the same one
    assert reg.registration_id == "REG000001"


def test_register_courses_rejects_payment_mismatch(tools: SchoolTools):
    student = tools.get_student_details(STUDENT_ID)
    payment_id = next(iter(student.payment_methods))
    course = tools.search_courses(term=TERM, open_only=True)[0]

    with pytest.raises(ValueError, match="does not add up"):
        tools.register_courses(
            student_id=STUDENT_ID,
            term=TERM,
            course_ids=[course.course_id],
            study_level="undergraduate",
            payment_methods=[{"payment_id": payment_id, "amount": 1}],
        )


def test_register_courses_rejects_wrong_term(tools: SchoolTools):
    course = tools.search_courses(term=TERM, open_only=True)[0]
    with pytest.raises(ValueError, match="does not match"):
        tools.register_courses(
            student_id=STUDENT_ID,
            term=OTHER_TERM,
            course_ids=[course.course_id],
            study_level="undergraduate",
        )


def test_update_registration_courses_adds_and_charges(tools: SchoolTools):
    reg = tools.get_registration_details(REGISTRATION_ID)
    payment_id = next(iter(tools.get_student_details(STUDENT_ID).payment_methods))
    addition = _addable_course(tools, REGISTRATION_ID)
    credits_before = reg.total_credits

    updated = tools.update_registration_courses(
        registration_id=REGISTRATION_ID,
        add_course_ids=[addition.course_id],
        drop_course_ids=[],
        payment_id=payment_id,
    )

    assert addition.course_id in {rc.course_id for rc in updated.courses}
    assert updated.total_credits == credits_before + addition.credits
    assert updated.payment_history[-1].amount > 0


def test_update_registration_requires_payment_for_charge(tools: SchoolTools):
    addition = _addable_course(tools, REGISTRATION_ID)
    with pytest.raises(ValueError, match="payment_id is required"):
        tools.update_registration_courses(
            registration_id=REGISTRATION_ID,
            add_course_ids=[addition.course_id],
            drop_course_ids=[],
        )
