"""Pydantic models for the school domain.

Schema is reverse-engineered from TRACER's school data files
(tracer/tracer/envs/school/data/) merged into
db.json. Fields the tools add at write time
(e.g. advisors on a freshly created registration) are modelled with
defaults so new records validate.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from tau_emotion.domains.school.utils import SCHOOL_DB_PATH
from tau_emotion.environment.db import DB

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class Name(BaseModel):
    first_name: str
    last_name: str


class Person(BaseModel):
    """An instructor or advisor: a name plus a contact address."""

    first_name: str
    last_name: str
    email: str


class Address(BaseModel):
    street: str
    city: str
    state: str
    zip: str
    country: str


class PaymentMethodExtraInfo(BaseModel):
    brand: Optional[str] = None
    bank: Optional[str] = None
    last_four: Optional[str] = None


class PaymentMethod(BaseModel):
    source: str
    payment_method_id: str
    extra_info: PaymentMethodExtraInfo = Field(default_factory=PaymentMethodExtraInfo)


class Payment(BaseModel):
    """An entry in a registration's payment history. Negative = refund."""

    payment_id: str
    amount: int


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------


class CourseLocation(BaseModel):
    campus: str
    building: str
    room: str


class MeetingPattern(BaseModel):
    days: List[str]
    start_time_est: str
    end_time_est: str


class CourseMeeting(BaseModel):
    """Per-date meeting record: whether the class was held, and when.

    Canceled meetings carry no actual start/end time.
    """

    status: str
    topic: str
    actual_start_time_est: Optional[str] = None
    actual_end_time_est: Optional[str] = None
    notes: Optional[str] = None


class Course(BaseModel):
    course_id: str
    department: str
    course_code: str
    title: str
    credits: int
    term: str
    instructor: Person
    location: CourseLocation
    meeting_pattern: MeetingPattern
    capacity: int
    current_enrollment: int
    waitlist_capacity: int
    current_waitlist: int
    scheduled_first_meeting_est: str
    scheduled_last_meeting_est: str
    dates: Dict[str, CourseMeeting]


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------


class Program(BaseModel):
    school: str
    degree: str
    major: str
    minor: Optional[str] = None


class SavedContact(BaseModel):
    first_name: str
    last_name: str
    relationship: str
    phone: str
    # TRACER's data spells this with hyphens rather than underscores.
    date_of_birth: str = Field(alias="date-of-birth")

    # Serialize as "date-of-birth" so tool output and saved DBs keep TRACER's key.
    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class Student(BaseModel):
    student_id: str
    name: Name
    address: Address
    email: str
    dob: str
    payment_methods: Dict[str, PaymentMethod]
    saved_contacts: List[SavedContact]
    program: Program
    registrations: List[str]
    membership: Optional[str] = None


# ---------------------------------------------------------------------------
# Registrations
# ---------------------------------------------------------------------------


class RegistrationCourse(BaseModel):
    """A course as recorded on a registration, with its priced tuition."""

    course_id: str
    course_code: str
    section: str
    title: str
    credits: int
    grading_option: str
    tuition: int


class FinancialAid(BaseModel):
    scholarships: int = 0
    grants: int = 0
    loans: int = 0


class Registration(BaseModel):
    registration_id: str
    student_id: str
    campus: str
    program: str
    study_level: str
    term: str
    status: str
    courses: List[RegistrationCourse]
    advisors: List[Person] = Field(default_factory=list)
    payment_history: List[Payment] = Field(default_factory=list)
    created_at: str
    total_credits: int
    overload_credits: int
    financial_aid: FinancialAid = Field(default_factory=FinancialAid)
    health_insurance: str


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------


class SchoolDB(DB):
    """Database for the school domain."""

    courses: Dict[str, Course]
    students: Dict[str, Student]
    registrations: Dict[str, Registration]

    def get_statistics(self) -> dict[str, Any]:
        return {
            "num_courses": len(self.courses),
            "num_students": len(self.students),
            "num_registrations": len(self.registrations),
        }


def get_db() -> SchoolDB:
    return SchoolDB.load(SCHOOL_DB_PATH)


if __name__ == "__main__":
    db = get_db()
    print(db.get_statistics())
