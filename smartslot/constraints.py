"""
Constraints and Independent Timetable Validation Module for SmartSlot AI.

Defines:
1. Academic domain data models.
2. Pre-scheduling configuration checks (feasibility diagnostics).
3. Hard constraint definitions and conflict detection.
4. Independent timetable validation engine with diagnostic suggestions.
"""

from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field

@dataclass
class TimeSlot:
    slot_id: str
    name: str
    start_time: str
    end_time: str
    is_break: bool = False

@dataclass
class Classroom:
    room_id: str
    name: str
    capacity: int
    room_type: str
    available: bool = True

@dataclass
class Faculty:
    faculty_id: str
    name: str
    email: str
    subjects: List[str]
    max_daily_sessions: int
    max_weekly_load: int
    available_days: List[str]
    unavailable_slots: Dict[str, List[str]] = field(default_factory=dict)

@dataclass
class Subject:
    subject_id: str
    name: str
    section_id: str
    faculty_id: str
    sessions_per_week: int
    duration_periods: int
    room_type: str
    expected_students: int
    consecutive: bool = False

@dataclass
class ScheduledPeriod:
    """Represents a scheduled unit of a session."""
    session_id: str
    subject_id: str
    subject_name: str
    section_id: str
    faculty_id: str
    faculty_name: str
    room_id: str
    room_name: str
    day: str
    slot_id: str
    period_index: int
    duration_periods: int
    is_consecutive_part: int = 1  # 1 for first period, 2 for second, etc.

@dataclass
class Conflict:
    conflict_type: str
    severity: str  # "ERROR" or "WARNING"
    description: str
    entities: Dict[str, Any]
    suggestion: str

@dataclass
class ValidationReport:
    is_valid: bool
    total_scheduled_periods: int
    total_required_periods: int
    conflicts: List[Conflict]
    summary_stats: Dict[str, Any]


def validate_configuration(config: Dict[str, Any]) -> List[Conflict]:
    """
    Validates input academic configuration before solver execution.
    Catches invalid configurations, missing assignments, duplicate IDs,
    and mathematical infeasibilities (e.g., Pigeonhole principle violations).
    """
    conflicts: List[Conflict] = []
    
    # Check working days
    days = config.get("working_days", [])
    if not days:
        conflicts.append(Conflict(
            conflict_type="CONFIG_ERROR",
            severity="ERROR",
            description="No working days configured in academic configuration.",
            entities={"working_days": days},
            suggestion="Add at least one working day (e.g., Monday through Friday)."
        ))

    # Check time slots
    slots = config.get("time_slots", [])
    teaching_slots = [s for s in slots if not s.get("is_break", False)]
    if not teaching_slots:
        conflicts.append(Conflict(
            conflict_type="CONFIG_ERROR",
            severity="ERROR",
            description="No active teaching time slots configured (all slots are breaks or empty).",
            entities={"time_slots_count": len(slots)},
            suggestion="Configure at least 2 non-break teaching periods per day."
        ))

    total_weekly_slots_per_room = len(days) * len(teaching_slots)

    # Check duplicate IDs
    slot_ids = [s["slot_id"] for s in slots]
    if len(slot_ids) != len(set(slot_ids)):
        conflicts.append(Conflict(
            conflict_type="DUPLICATE_ID",
            severity="ERROR",
            description="Duplicate slot IDs detected in time slot configuration.",
            entities={"duplicate_ids": [id_ for id_ in slot_ids if slot_ids.count(id_) > 1]},
            suggestion="Ensure each time slot has a distinct identifier."
        ))

    faculty_list = config.get("faculty", [])
    fac_ids = [f["faculty_id"] for f in faculty_list]
    if len(fac_ids) != len(set(fac_ids)):
        conflicts.append(Conflict(
            conflict_type="DUPLICATE_ID",
            severity="ERROR",
            description="Duplicate faculty IDs detected in faculty configuration.",
            entities={"duplicate_ids": [id_ for id_ in fac_ids if fac_ids.count(id_) > 1]},
            suggestion="Ensure each faculty member has a unique Faculty ID."
        ))

    rooms = config.get("classrooms", [])
    room_ids = [r["room_id"] for r in rooms]
    if len(room_ids) != len(set(room_ids)):
        conflicts.append(Conflict(
            conflict_type="DUPLICATE_ID",
            severity="ERROR",
            description="Duplicate classroom IDs detected in room configuration.",
            entities={"duplicate_ids": [id_ for id_ in room_ids if room_ids.count(id_) > 1]},
            suggestion="Ensure each classroom has a unique Room ID."
        ))

    subjects = config.get("subjects", [])
    subj_ids = [s["subject_id"] for s in subjects]
    if len(subj_ids) != len(set(subj_ids)):
        conflicts.append(Conflict(
            conflict_type="DUPLICATE_ID",
            severity="ERROR",
            description="Duplicate subject IDs detected in subject configuration.",
            entities={"duplicate_ids": [id_ for id_ in subj_ids if subj_ids.count(id_) > 1]},
            suggestion="Ensure each course subject has a unique Subject ID."
        ))

    # Entity maps for foreign key verification
    fac_map = {f["faculty_id"]: f for f in faculty_list}
    room_map = {r["room_id"]: r for r in rooms}
    sec_map = {s["section_id"]: s for s in config.get("sections", [])}

    # Track section demand and faculty load demand
    section_periods: Dict[str, int] = {sec_id: 0 for sec_id in sec_map}
    faculty_periods: Dict[str, int] = {fac_id: 0 for fac_id in fac_map}
    room_type_demand: Dict[str, int] = {}

    for subj in subjects:
        sid = subj.get("subject_id", "Unknown")
        fid = subj.get("faculty_id")
        sec_id = subj.get("section_id")
        req_room_type = subj.get("room_type", "Classroom")
        sessions_cnt = subj.get("sessions_per_week", 0)
        duration = subj.get("duration_periods", 1)
        total_subj_periods = sessions_cnt * duration

        room_type_demand[req_room_type] = room_type_demand.get(req_room_type, 0) + total_subj_periods

        # Check faculty reference
        if not fid or fid not in fac_map:
            conflicts.append(Conflict(
                conflict_type="MISSING_FACULTY",
                severity="ERROR",
                description=f"Subject '{subj.get('name', sid)}' has an unassigned or invalid faculty member '{fid}'.",
                entities={"subject_id": sid, "faculty_id": fid},
                suggestion=f"Assign an existing, valid faculty member to subject '{sid}'."
            ))
        else:
            faculty_periods[fid] += total_subj_periods

        # Check section reference
        if not sec_id or sec_id not in sec_map:
            conflicts.append(Conflict(
                conflict_type="MISSING_SECTION",
                severity="ERROR",
                description=f"Subject '{subj.get('name', sid)}' references undefined student section '{sec_id}'.",
                entities={"subject_id": sid, "section_id": sec_id},
                suggestion=f"Assign subject '{sid}' to an existing section defined in student sections."
            ))
        else:
            section_periods[sec_id] += total_subj_periods

        # Check expected students vs available room capacity
        matching_rooms = [
            r for r in rooms 
            if r.get("room_type") == req_room_type and r.get("available", True)
        ]
        if not matching_rooms:
            conflicts.append(Conflict(
                conflict_type="NO_COMPATIBLE_ROOM",
                severity="ERROR",
                description=f"Subject '{subj.get('name', sid)}' requires room type '{req_room_type}', but no active rooms of that type exist.",
                entities={"subject_id": sid, "room_type": req_room_type},
                suggestion=f"Add or enable at least one active classroom with room type '{req_room_type}'."
            ))
        else:
            max_cap = max(r.get("capacity", 0) for r in matching_rooms)
            exp_students = subj.get("expected_students", 0)
            if exp_students > max_cap:
                conflicts.append(Conflict(
                    conflict_type="INSUFFICIENT_ROOM_CAPACITY",
                    severity="ERROR",
                    description=f"Subject '{subj.get('name', sid)}' has {exp_students} expected students, but the largest available '{req_room_type}' accommodates only {max_cap}.",
                    entities={"subject_id": sid, "expected_students": exp_students, "max_capacity": max_cap},
                    suggestion=f"Increase room capacity or decrease expected student enrollment for subject '{sid}'."
                ))

    # Pigeonhole Principle: Section demand vs Available periods
    for sec_id, total_demanded in section_periods.items():
        if total_demanded > total_weekly_slots_per_room:
            sec_name = sec_map[sec_id].get("name", sec_id)
            conflicts.append(Conflict(
                conflict_type="SECTION_OVERLOAD",
                severity="ERROR",
                description=f"Section '{sec_name}' requires {total_demanded} periods per week, but only {total_weekly_slots_per_room} teaching slots exist in the weekly schedule.",
                entities={"section_id": sec_id, "required_periods": total_demanded, "available_slots": total_weekly_slots_per_room},
                suggestion=f"Reduce required sessions for section '{sec_id}' or expand working days / daily periods."
            ))

    # Faculty Max Weekly Load check
    for fid, total_demanded in faculty_periods.items():
        fac_obj = fac_map[fid]
        max_load = fac_obj.get("max_weekly_load", total_weekly_slots_per_room)
        if total_demanded > max_load:
            conflicts.append(Conflict(
                conflict_type="FACULTY_OVERLOAD",
                severity="ERROR",
                description=f"Faculty '{fac_obj.get('name', fid)}' assigned {total_demanded} teaching periods, exceeding their maximum weekly limit of {max_load} periods.",
                entities={"faculty_id": fid, "demanded_load": total_demanded, "max_weekly_load": max_load},
                suggestion=f"Increase maximum weekly load for '{fac_obj.get('name', fid)}' or reassign some courses to another faculty member."
            ))

    # Room Type Capacity vs Total Demand
    for r_type, demanded_periods in room_type_demand.items():
        avail_rooms_for_type = [r for r in rooms if r.get("room_type") == r_type and r.get("available", True)]
        total_type_supply = len(avail_rooms_for_type) * total_weekly_slots_per_room
        if demanded_periods > total_type_supply:
            conflicts.append(Conflict(
                conflict_type="ROOM_TYPE_SHORTAGE",
                severity="ERROR",
                description=f"Total demand for '{r_type}' is {demanded_periods} periods, but available '{r_type}' supply is only {total_type_supply} periods.",
                entities={"room_type": r_type, "demanded": demanded_periods, "available_capacity": total_type_supply},
                suggestion=f"Add more rooms of type '{r_type}' or reduce sessions requiring this room type."
            ))

    return conflicts


def validate_timetable(assignments: List[Dict[str, Any]], config: Dict[str, Any]) -> ValidationReport:
    """
    Performs an exhaustive, independent validation pass on a generated or manually edited timetable.
    Does not assume or trust that the solver succeeded without checking every constraint.
    """
    conflicts: List[Conflict] = []
    
    # Entity lookup maps
    faculty_map = {f["faculty_id"]: f for f in config.get("faculty", [])}
    room_map = {r["room_id"]: r for r in config.get("classrooms", [])}
    section_map = {s["section_id"]: s for s in config.get("sections", [])}
    subject_map = {s["subject_id"]: s for s in config.get("subjects", [])}
    time_slots_map = {s["slot_id"]: s for s in config.get("time_slots", [])}

    # Tracking sets/dicts for simultaneous clashes
    # Key: (day, slot_id)
    faculty_slot_bookings: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    room_slot_bookings: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    section_slot_bookings: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

    # Faculty load tracking: faculty_id -> { "total": int, "by_day": { day: int } }
    faculty_load: Dict[str, Dict[str, Any]] = {
        fid: {"total": 0, "by_day": {d: 0 for d in config.get("working_days", [])}}
        for fid in faculty_map
    }

    # Subject session counts scheduled
    subject_scheduled_count: Dict[str, int] = {sid: 0 for sid in subject_map}
    subject_scheduled_periods: Dict[str, int] = {sid: 0 for sid in subject_map}

    total_periods = len(assignments)

    for item in assignments:
        day = item.get("day")
        slot_id = item.get("slot_id")
        fac_id = item.get("faculty_id")
        room_id = item.get("room_id")
        sec_id = item.get("section_id")
        subj_id = item.get("subject_id")
        subj_name = item.get("subject_name", subj_id)

        # 1. Break Period Overlap Constraint
        slot_info = time_slots_map.get(slot_id)
        if slot_info and slot_info.get("is_break", False):
            conflicts.append(Conflict(
                conflict_type="BREAK_COLLISION",
                severity="ERROR",
                description=f"Subject '{subj_name}' is scheduled during break period '{slot_info.get('name', slot_id)}' on {day}.",
                entities={"subject_id": subj_id, "day": day, "slot_id": slot_id},
                suggestion="Re-schedule the session to an active teaching period outside designated breaks."
            ))

        # 2. Faculty Simultaneous Clash
        if fac_id:
            key = (day, slot_id)
            if key not in faculty_slot_bookings:
                faculty_slot_bookings[key] = []
            for prior in faculty_slot_bookings[key]:
                if prior.get("faculty_id") == fac_id:
                    fac_name = faculty_map.get(fac_id, {}).get("name", fac_id)
                    conflicts.append(Conflict(
                        conflict_type="FACULTY_CLASH",
                        severity="ERROR",
                        description=f"Faculty clash: {fac_name} is simultaneously assigned to '{subj_name}' in room {room_id} and '{prior.get('subject_name')}' in room {prior.get('room_id')} on {day} during {slot_id}.",
                        entities={"faculty_id": fac_id, "day": day, "slot_id": slot_id, "first_session": prior, "second_session": item},
                        suggestion=f"Move one of {fac_name}'s conflicting classes to a different period or day."
                    ))
            faculty_slot_bookings[key].append(item)

            # Faculty Load Accumulation
            if fac_id in faculty_load:
                faculty_load[fac_id]["total"] += 1
                if day in faculty_load[fac_id]["by_day"]:
                    faculty_load[fac_id]["by_day"][day] += 1

            # 3. Faculty Availability & Unavailability Schedule
            fac_info = faculty_map.get(fac_id)
            if fac_info:
                avail_days = fac_info.get("available_days", [])
                if day not in avail_days:
                    conflicts.append(Conflict(
                        conflict_type="FACULTY_UNAVAILABLE",
                        severity="ERROR",
                        description=f"Faculty {fac_info.get('name')} is scheduled on {day}, but is only available on {', '.join(avail_days)}.",
                        entities={"faculty_id": fac_id, "day": day},
                        suggestion=f"Move the class to one of {fac_info.get('name')}'s available working days."
                    ))
                unavail_slots = fac_info.get("unavailable_slots", {}).get(day, [])
                if slot_id in unavail_slots:
                    conflicts.append(Conflict(
                        conflict_type="FACULTY_UNAVAILABLE",
                        severity="ERROR",
                        description=f"Faculty {fac_info.get('name')} is marked as unavailable during slot {slot_id} on {day}.",
                        entities={"faculty_id": fac_id, "day": day, "slot_id": slot_id},
                        suggestion=f"Avoid scheduling {fac_info.get('name')} in slot {slot_id} on {day}."
                    ))

        # 4. Classroom Simultaneous Clash
        if room_id:
            key = (day, slot_id)
            if key not in room_slot_bookings:
                room_slot_bookings[key] = []
            for prior in room_slot_bookings[key]:
                if prior.get("room_id") == room_id:
                    r_name = room_map.get(room_id, {}).get("name", room_id)
                    conflicts.append(Conflict(
                        conflict_type="ROOM_CLASH",
                        severity="ERROR",
                        description=f"Classroom clash: Room '{r_name}' is double-booked for '{subj_name}' and '{prior.get('subject_name')}' on {day} during {slot_id}.",
                        entities={"room_id": room_id, "day": day, "slot_id": slot_id},
                        suggestion=f"Move one of the sessions in '{r_name}' to an alternate vacant classroom or time slot."
                    ))
            room_slot_bookings[key].append(item)

            # 5. Room Type & Capacity Checks
            room_obj = room_map.get(room_id)
            subj_obj = subject_map.get(subj_id)
            if room_obj and subj_obj:
                req_type = subj_obj.get("room_type", "Classroom")
                if room_obj.get("room_type") != req_type:
                    conflicts.append(Conflict(
                        conflict_type="ROOM_TYPE_MISMATCH",
                        severity="ERROR",
                        description=f"Room type mismatch: Subject '{subj_name}' requires '{req_type}', but was assigned room '{room_obj.get('name')}' which is a '{room_obj.get('room_type')}'.",
                        entities={"subject_id": subj_id, "room_id": room_id, "required": req_type, "actual": room_obj.get("room_type")},
                        suggestion=f"Assign subject '{subj_name}' to a room matching required type '{req_type}'."
                    ))

                exp_students = subj_obj.get("expected_students", 0)
                if room_obj.get("capacity", 0) < exp_students:
                    conflicts.append(Conflict(
                        conflict_type="CAPACITY_VIOLATION",
                        severity="ERROR",
                        description=f"Capacity violation: Subject '{subj_name}' has {exp_students} students, but room '{room_obj.get('name')}' can only hold {room_obj.get('capacity')}.",
                        entities={"subject_id": subj_id, "room_id": room_id, "capacity": room_obj.get("capacity"), "students": exp_students},
                        suggestion=f"Move '{subj_name}' to a room with capacity >= {exp_students}."
                    ))

        # 6. Student Section Simultaneous Clash
        if sec_id:
            key = (day, slot_id)
            if key not in section_slot_bookings:
                section_slot_bookings[key] = []
            for prior in section_slot_bookings[key]:
                if prior.get("section_id") == sec_id:
                    s_name = section_map.get(sec_id, {}).get("name", sec_id)
                    conflicts.append(Conflict(
                        conflict_type="SECTION_CLASH",
                        severity="ERROR",
                        description=f"Section clash: Students of '{s_name}' are scheduled for both '{subj_name}' and '{prior.get('subject_name')}' on {day} during {slot_id}.",
                        entities={"section_id": sec_id, "day": day, "slot_id": slot_id},
                        suggestion=f"Avoid overlapping classes for section '{s_name}'."
                    ))
            section_slot_bookings[key].append(item)

        # Track subject session count
        if subj_id in subject_scheduled_periods:
            subject_scheduled_periods[subj_id] += 1
            if item.get("is_consecutive_part", 1) == 1:
                subject_scheduled_count[subj_id] += 1

    # 7. Faculty Maximum Daily & Weekly Workload Checks
    for fid, load_data in faculty_load.items():
        fac_obj = faculty_map.get(fid, {})
        max_weekly = fac_obj.get("max_weekly_load", 99)
        max_daily = fac_obj.get("max_daily_sessions", 99)

        if load_data["total"] > max_weekly:
            conflicts.append(Conflict(
                conflict_type="FACULTY_WORKLOAD_EXCEEDED",
                severity="ERROR",
                description=f"Faculty '{fac_obj.get('name', fid)}' taught {load_data['total']} periods this week, exceeding maximum weekly load of {max_weekly}.",
                entities={"faculty_id": fid, "actual": load_data["total"], "max": max_weekly},
                suggestion=f"Rebalance load by shifting courses from '{fac_obj.get('name', fid)}' to other qualified faculty."
            ))

        for day, daily_count in load_data["by_day"].items():
            if daily_count > max_daily:
                conflicts.append(Conflict(
                    conflict_type="FACULTY_DAILY_LIMIT_EXCEEDED",
                    severity="WARNING",
                    description=f"Faculty '{fac_obj.get('name', fid)}' taught {daily_count} periods on {day}, exceeding daily limit of {max_daily}.",
                    entities={"faculty_id": fid, "day": day, "actual": daily_count, "max": max_daily},
                    suggestion=f"Redistribute '{fac_obj.get('name', fid)}' classes across other days of the week."
                ))

    # 8. Unscheduled Sessions & Completeness Check
    total_required_periods = 0
    unscheduled_subjects: List[str] = []
    for subj in config.get("subjects", []):
        sid = subj["subject_id"]
        req_sessions = subj.get("sessions_per_week", 0)
        duration = subj.get("duration_periods", 1)
        expected_periods = req_sessions * duration
        total_required_periods += expected_periods

        actual_sessions = subject_scheduled_count.get(sid, 0)
        actual_periods = subject_scheduled_periods.get(sid, 0)

        if actual_sessions < req_sessions or actual_periods < expected_periods:
            unscheduled_subjects.append(subj.get("name", sid))
            conflicts.append(Conflict(
                conflict_type="UNSCHEDULED_SESSIONS",
                severity="ERROR",
                description=f"Subject '{subj.get('name', sid)}' requires {req_sessions} sessions ({expected_periods} periods), but only {actual_sessions} sessions ({actual_periods} periods) were scheduled.",
                entities={"subject_id": sid, "required_sessions": req_sessions, "scheduled_sessions": actual_sessions},
                suggestion=f"Adjust room availability or relaxation constraints to accommodate remaining sessions of '{subj.get('name', sid)}'."
            ))

    is_valid = len([c for c in conflicts if c.severity == "ERROR"]) == 0

    stats = {
        "total_scheduled_periods": total_periods,
        "total_required_periods": total_required_periods,
        "completion_percentage": round((total_periods / max(1, total_required_periods)) * 100, 1),
        "total_conflicts": len(conflicts),
        "error_count": len([c for c in conflicts if c.severity == "ERROR"]),
        "warning_count": len([c for c in conflicts if c.severity == "WARNING"]),
        "faculty_load_distribution": {
            faculty_map[fid]["name"]: data["total"] 
            for fid, data in faculty_load.items() if fid in faculty_map
        }
    }

    return ValidationReport(
        is_valid=is_valid,
        total_scheduled_periods=total_periods,
        total_required_periods=total_required_periods,
        conflicts=conflicts,
        summary_stats=stats
    )
