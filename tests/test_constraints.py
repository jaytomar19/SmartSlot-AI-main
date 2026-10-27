"""
Unit tests for SmartSlot AI - Constraints and Independent Validation.
Verifies:
- Feasibility checks
- Faculty clash detection
- Room clash detection
- Section clash detection
- Faculty unavailability rejection
- Room type mismatch detection
- Room capacity violation detection
- Infeasible configuration handling
"""

import pytest
import copy
from smartslot.sample_data import get_default_academic_config, get_infeasible_academic_config
from smartslot.constraints import validate_configuration, validate_timetable


def test_default_config_is_valid():
    config = get_default_academic_config()
    conflicts = validate_configuration(config)
    assert len(conflicts) == 0, f"Expected 0 configuration conflicts, found: {conflicts}"


def test_infeasible_config_detection():
    config = get_infeasible_academic_config()
    conflicts = validate_configuration(config)
    assert len(conflicts) > 0
    types = [c.conflict_type for c in conflicts]
    assert "NO_COMPATIBLE_ROOM" in types or "ROOM_TYPE_SHORTAGE" in types
    assert "SECTION_OVERLOAD" in types
    assert "FACULTY_OVERLOAD" in types


def test_faculty_clash_detection():
    config = get_default_academic_config()
    # Create artificial timetable assignment where faculty is double booked
    bad_assignment = [
        {
            "session_id": "CS101_S1",
            "subject_id": "CS101",
            "subject_name": "Artificial Intelligence",
            "section_id": "CS-A",
            "faculty_id": "FAC01",
            "room_id": "R101",
            "day": "Monday",
            "slot_id": "P1",
            "is_consecutive_part": 1,
        },
        {
            "session_id": "CS105L_S1",
            "subject_id": "CS105L",
            "subject_name": "AI & Machine Learning Lab",
            "section_id": "CS-B",
            "faculty_id": "FAC01",  # Same faculty simultaneously!
            "room_id": "LAB1",
            "day": "Monday",
            "slot_id": "P1",
            "is_consecutive_part": 1,
        }
    ]
    report = validate_timetable(bad_assignment, config)
    assert not report.is_valid
    clash_types = [c.conflict_type for c in report.conflicts]
    assert "FACULTY_CLASH" in clash_types


def test_room_clash_detection():
    config = get_default_academic_config()
    # Create artificial assignment where room R101 has 2 distinct classes at the same time
    bad_assignment = [
        {
            "session_id": "CS101_S1",
            "subject_id": "CS101",
            "subject_name": "Artificial Intelligence",
            "section_id": "CS-A",
            "faculty_id": "FAC01",
            "room_id": "R101",
            "day": "Tuesday",
            "slot_id": "P2",
            "is_consecutive_part": 1,
        },
        {
            "session_id": "CS102_S1",
            "subject_id": "CS102",
            "subject_name": "Data Structures",
            "section_id": "CS-B",
            "faculty_id": "FAC02",
            "room_id": "R101",  # Same room simultaneously!
            "day": "Tuesday",
            "slot_id": "P2",
            "is_consecutive_part": 1,
        }
    ]
    report = validate_timetable(bad_assignment, config)
    assert not report.is_valid
    clash_types = [c.conflict_type for c in report.conflicts]
    assert "ROOM_CLASH" in clash_types


def test_section_clash_detection():
    config = get_default_academic_config()
    # Create artificial assignment where students in section CS-A are assigned two rooms at once
    bad_assignment = [
        {
            "session_id": "CS101_S1",
            "subject_id": "CS101",
            "subject_name": "Artificial Intelligence",
            "section_id": "CS-A",  # CS-A
            "faculty_id": "FAC01",
            "room_id": "R101",
            "day": "Wednesday",
            "slot_id": "P3",
            "is_consecutive_part": 1,
        },
        {
            "session_id": "CS102_S1",
            "subject_id": "CS102",
            "subject_name": "Data Structures",
            "section_id": "CS-A",  # Also CS-A!
            "faculty_id": "FAC02",
            "room_id": "R102",
            "day": "Wednesday",
            "slot_id": "P3",
            "is_consecutive_part": 1,
        }
    ]
    report = validate_timetable(bad_assignment, config)
    assert not report.is_valid
    clash_types = [c.conflict_type for c in report.conflicts]
    assert "SECTION_CLASH" in clash_types


def test_faculty_unavailability_detection():
    config = get_default_academic_config()
    # Prof. Alan Turing (FAC01) is unavailable on Friday periods P5, P6
    bad_assignment = [
        {
            "session_id": "CS101_S1",
            "subject_id": "CS101",
            "subject_name": "Artificial Intelligence",
            "section_id": "CS-A",
            "faculty_id": "FAC01",
            "room_id": "R101",
            "day": "Friday",
            "slot_id": "P5",  # Marked unavailable!
            "is_consecutive_part": 1,
        }
    ]
    report = validate_timetable(bad_assignment, config)
    assert not report.is_valid
    clash_types = [c.conflict_type for c in report.conflicts]
    assert "FACULTY_UNAVAILABLE" in clash_types


def test_room_type_mismatch_detection():
    config = get_default_academic_config()
    # CS105L requires "Laboratory", artificially assign to "R101" (Classroom)
    bad_assignment = [
        {
            "session_id": "CS105L_S1",
            "subject_id": "CS105L",
            "subject_name": "AI & Machine Learning Lab",
            "section_id": "CS-A",
            "faculty_id": "FAC01",
            "room_id": "R101",  # Classroom instead of Laboratory!
            "day": "Thursday",
            "slot_id": "P1",
            "is_consecutive_part": 1,
        }
    ]
    report = validate_timetable(bad_assignment, config)
    assert not report.is_valid
    clash_types = [c.conflict_type for c in report.conflicts]
    assert "ROOM_TYPE_MISMATCH" in clash_types


def test_room_capacity_violation_detection():
    config = get_default_academic_config()
    # Artificially modify room R102 capacity to 10 students when subject has 35 students
    config_copy = copy.deepcopy(config)
    for r in config_copy["classrooms"]:
        if r["room_id"] == "R102":
            r["capacity"] = 10

    assignment = [
        {
            "session_id": "CS101_S1",
            "subject_id": "CS101",
            "subject_name": "Artificial Intelligence",
            "section_id": "CS-A",
            "faculty_id": "FAC01",
            "room_id": "R102",  # Only 10 seats for 35 students!
            "day": "Monday",
            "slot_id": "P2",
            "is_consecutive_part": 1,
        }
    ]
    report = validate_timetable(assignment, config_copy)
    assert not report.is_valid
    clash_types = [c.conflict_type for c in report.conflicts]
    assert "CAPACITY_VIOLATION" in clash_types


def test_break_overlap_detection():
    config = get_default_academic_config()
    # Artificially assign class to "LUNCH" break slot
    bad_assignment = [
        {
            "session_id": "CS101_S1",
            "subject_id": "CS101",
            "subject_name": "Artificial Intelligence",
            "section_id": "CS-A",
            "faculty_id": "FAC01",
            "room_id": "R101",
            "day": "Monday",
            "slot_id": "LUNCH",  # Break slot
            "is_consecutive_part": 1,
        }
    ]
    report = validate_timetable(bad_assignment, config)
    assert not report.is_valid
    clash_types = [c.conflict_type for c in report.conflicts]
    assert "BREAK_COLLISION" in clash_types
