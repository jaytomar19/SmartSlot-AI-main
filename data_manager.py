"""
SmartSlot AI - Data Management, Persistence, and Export Module.

Handles:
- Configuration persistence (JSON save/load/reset).
- Data model mutations (add, edit, delete with input validation).
- Timetable transformations to Pandas DataFrame for UI rendering.
- CSV and Markdown exports.
"""

import json
import os
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
from sample_data import get_default_academic_config, get_infeasible_academic_config
from constraints import ValidationReport

DEFAULT_DATA_FILE = "academic_config.json"


class DataManager:
    """Manages local state, persistence, validation, and export of timetable data."""

    def __init__(self, filepath: str = DEFAULT_DATA_FILE):
        self.filepath = filepath
        self.config: Dict[str, Any] = self.load_config()
        self.current_timetable: List[Dict[str, Any]] = []
        self.last_validation: Optional[ValidationReport] = None
        self.last_solver_metrics: Optional[Dict[str, Any]] = None

    def load_config(self) -> Dict[str, Any]:
        """Loads configuration from JSON file or initializes with default Northstar dataset."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return get_default_academic_config()
        return get_default_academic_config()

    def save_config(self) -> bool:
        """Persists the current configuration to local JSON."""
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception:
            return False

    def reset_to_default(self):
        """Restores the fictional Northstar Institute of Technology dataset."""
        self.config = get_default_academic_config()
        self.current_timetable = []
        self.last_validation = None
        self.last_solver_metrics = None
        self.save_config()

    def load_infeasible_scenario(self):
        """Loads intentionally infeasible configuration for testing conflict detection."""
        self.config = get_infeasible_academic_config()
        self.current_timetable = []
        self.last_validation = None
        self.last_solver_metrics = None
        self.save_config()

    # --- Classroom Management ---
    def add_classroom(self, room_id: str, name: str, capacity: int, room_type: str, available: bool = True) -> Tuple[bool, str]:
        room_id = room_id.strip()
        if not room_id:
            return False, "Room ID cannot be empty."
        if any(r["room_id"] == room_id for r in self.config["classrooms"]):
            return False, f"Room ID '{room_id}' already exists."
        if capacity <= 0:
            return False, "Capacity must be greater than zero."

        self.config["classrooms"].append({
            "room_id": room_id,
            "name": name.strip() or f"Room {room_id}",
            "capacity": capacity,
            "room_type": room_type,
            "available": available
        })
        self.save_config()
        return True, f"Classroom '{room_id}' added successfully."

    def update_classroom(self, room_id: str, name: str, capacity: int, room_type: str, available: bool) -> Tuple[bool, str]:
        for room in self.config["classrooms"]:
            if room["room_id"] == room_id:
                if capacity <= 0:
                    return False, "Capacity must be greater than zero."
                room["name"] = name.strip() or room["name"]
                room["capacity"] = capacity
                room["room_type"] = room_type
                room["available"] = available
                self.save_config()
                return True, f"Classroom '{room_id}' updated."
        return False, f"Room '{room_id}' not found."

    def delete_classroom(self, room_id: str) -> Tuple[bool, str]:
        rooms = self.config["classrooms"]
        for i, r in enumerate(rooms):
            if r["room_id"] == room_id:
                rooms.pop(i)
                self.save_config()
                return True, f"Classroom '{room_id}' removed."
        return False, f"Classroom '{room_id}' not found."

    # --- Faculty Management ---
    def add_faculty(
        self,
        faculty_id: str,
        name: str,
        email: str,
        subjects: List[str],
        max_daily: int,
        max_weekly: int,
        available_days: List[str],
        unavailable_slots: Optional[Dict[str, List[str]]] = None
    ) -> Tuple[bool, str]:
        faculty_id = faculty_id.strip()
        if not faculty_id:
            return False, "Faculty ID cannot be empty."
        if any(f["faculty_id"] == faculty_id for f in self.config["faculty"]):
            return False, f"Faculty ID '{faculty_id}' already exists."
        if max_daily <= 0 or max_weekly <= 0:
            return False, "Workload limits must be greater than zero."
        if not available_days:
            return False, "At least one available day must be selected."

        self.config["faculty"].append({
            "faculty_id": faculty_id,
            "name": name.strip() or f"Faculty {faculty_id}",
            "email": email.strip(),
            "subjects": subjects,
            "max_daily_sessions": max_daily,
            "max_weekly_load": max_weekly,
            "available_days": available_days,
            "unavailable_slots": unavailable_slots or {}
        })
        self.save_config()
        return True, f"Faculty '{faculty_id}' added successfully."

    def update_faculty(
        self,
        faculty_id: str,
        name: str,
        email: str,
        subjects: List[str],
        max_daily: int,
        max_weekly: int,
        available_days: List[str],
        unavailable_slots: Optional[Dict[str, List[str]]] = None
    ) -> Tuple[bool, str]:
        for fac in self.config["faculty"]:
            if fac["faculty_id"] == faculty_id:
                if max_daily <= 0 or max_weekly <= 0:
                    return False, "Workload limits must be positive numbers."
                if not available_days:
                    return False, "At least one available day must be selected."
                fac["name"] = name.strip() or fac["name"]
                fac["email"] = email.strip()
                fac["subjects"] = subjects
                fac["max_daily_sessions"] = max_daily
                fac["max_weekly_load"] = max_weekly
                fac["available_days"] = available_days
                fac["unavailable_slots"] = unavailable_slots or {}
                self.save_config()
                return True, f"Faculty '{faculty_id}' updated."
        return False, f"Faculty '{faculty_id}' not found."

    def delete_faculty(self, faculty_id: str) -> Tuple[bool, str]:
        # Check if any subject references this faculty
        assigned_subjects = [s["name"] for s in self.config["subjects"] if s.get("faculty_id") == faculty_id]
        if assigned_subjects:
            return False, f"Cannot delete faculty '{faculty_id}': Assigned to subjects ({', '.join(assigned_subjects)}). Reassign courses first."

        faculty_list = self.config["faculty"]
        for i, f in enumerate(faculty_list):
            if f["faculty_id"] == faculty_id:
                faculty_list.pop(i)
                self.save_config()
                return True, f"Faculty '{faculty_id}' removed."
        return False, f"Faculty '{faculty_id}' not found."

    # --- Subject Management ---
    def add_subject(
        self,
        subject_id: str,
        name: str,
        section_id: str,
        faculty_id: str,
        sessions_per_week: int,
        duration_periods: int,
        room_type: str,
        expected_students: int,
        consecutive: bool
    ) -> Tuple[bool, str]:
        subject_id = subject_id.strip()
        if not subject_id:
            return False, "Subject ID cannot be empty."
        if any(s["subject_id"] == subject_id for s in self.config["subjects"]):
            return False, f"Subject ID '{subject_id}' already exists."
        if sessions_per_week <= 0:
            return False, "Sessions per week must be at least 1."
        if duration_periods <= 0:
            return False, "Duration must be at least 1 period."
        if expected_students <= 0:
            return False, "Expected students must be greater than zero."

        self.config["subjects"].append({
            "subject_id": subject_id,
            "name": name.strip() or f"Subject {subject_id}",
            "section_id": section_id,
            "faculty_id": faculty_id,
            "sessions_per_week": sessions_per_week,
            "duration_periods": duration_periods,
            "room_type": room_type,
            "expected_students": expected_students,
            "consecutive": consecutive
        })
        self.save_config()
        return True, f"Subject '{subject_id}' added successfully."

    def update_subject(
        self,
        subject_id: str,
        name: str,
        section_id: str,
        faculty_id: str,
        sessions_per_week: int,
        duration_periods: int,
        room_type: str,
        expected_students: int,
        consecutive: bool
    ) -> Tuple[bool, str]:
        for subj in self.config["subjects"]:
            if subj["subject_id"] == subject_id:
                if sessions_per_week <= 0 or duration_periods <= 0 or expected_students <= 0:
                    return False, "Sessions, duration, and expected students must be positive numbers."
                subj["name"] = name.strip() or subj["name"]
                subj["section_id"] = section_id
                subj["faculty_id"] = faculty_id
                subj["sessions_per_week"] = sessions_per_week
                subj["duration_periods"] = duration_periods
                subj["room_type"] = room_type
                subj["expected_students"] = expected_students
                subj["consecutive"] = consecutive
                self.save_config()
                return True, f"Subject '{subject_id}' updated."
        return False, f"Subject '{subject_id}' not found."

    def delete_subject(self, subject_id: str) -> Tuple[bool, str]:
        subjects = self.config["subjects"]
        for i, s in enumerate(subjects):
            if s["subject_id"] == subject_id:
                subjects.pop(i)
                self.save_config()
                return True, f"Subject '{subject_id}' removed."
        return False, f"Subject '{subject_id}' not found."

    # --- Timetable Transformation and Export ---
    def get_timetable_dataframe(self) -> pd.DataFrame:
        """Converts current timetable assignments into a tabular Pandas DataFrame."""
        if not self.current_timetable:
            return pd.DataFrame()
        return pd.DataFrame(self.current_timetable)

    def export_timetable_csv(self) -> str:
        """Generates CSV string of the active generated timetable."""
        df = self.get_timetable_dataframe()
        if df.empty:
            return ""
        export_cols = [
            "day", "slot_id", "slot_name", "start_time", "end_time",
            "subject_id", "subject_name", "section_id",
            "faculty_name", "room_id", "room_name", "room_type", "duration_periods"
        ]
        available_cols = [c for c in export_cols if c in df.columns]
        return df[available_cols].to_csv(index=False)

    def generate_audit_summary_markdown(self) -> str:
        """Generates comprehensive validation and audit report in Markdown format."""
        lines = [
            f"# SmartSlot AI - Timetable Generation & Validation Report",
            f"**Institution:** {self.config.get('institution_name', 'Fictional University')}",
            f"**Department:** {self.config.get('department', 'Computer Science & Engineering')}",
            f"**Academic Term:** {self.config.get('academic_term', 'Current Term')}",
            "",
            "## 1. Executive Summary",
        ]

        if not self.last_validation:
            lines.append("No active validation report available. Run timetable generation first.")
            return "\n".join(lines)

        val = self.last_validation
        lines.append(f"- **Validation Status:** {'VALID (CONFLICT-FREE)' if val.is_valid else 'INVALID (CONFLICTS DETECTED)'}")
        lines.append(f"- **Scheduled Periods:** {val.total_scheduled_periods} / {val.total_required_periods} ({val.summary_stats.get('completion_percentage', 0)}%)")
        lines.append(f"- **Total Conflicts:** {val.summary_stats.get('total_conflicts', 0)} ({val.summary_stats.get('error_count', 0)} errors, {val.summary_stats.get('warning_count', 0)} warnings)")
        
        if self.last_solver_metrics:
            m = self.last_solver_metrics
            lines.extend([
                "",
                "## 2. Solver Algorithm Performance",
                f"- **Sessions to Schedule:** {m.get('sessions_to_schedule', 0)}",
                f"- **Candidate Assignments Explored:** {m.get('candidate_assignments_explored', 0)}",
                f"- **Backtrack Count:** {m.get('backtrack_count', 0)}",
                f"- **Constraint Checks Performed:** {m.get('constraint_checks', 0)}",
                f"- **Search Execution Time:** {m.get('execution_time_seconds', 0.0)} seconds",
                f"- **Max Search Depth:** {m.get('max_search_depth', 0)}",
            ])

        lines.extend([
            "",
            "## 3. Faculty Teaching Load Distribution",
            "| Faculty Member | Weekly Periods Assigned |",
            "|:---|:---:|"
        ])
        for fac_name, count in val.summary_stats.get("faculty_load_distribution", {}).items():
            lines.append(f"| {fac_name} | {count} |")

        if val.conflicts:
            lines.extend([
                "",
                "## 4. Detected Conflicts and Resolution Advice",
            ])
            for i, c in enumerate(val.conflicts, 1):
                lines.append(f"### {i}. [{c.severity}] {c.conflict_type}")
                lines.append(f"- **Description:** {c.description}")
                lines.append(f"- **Suggested Action:** {c.suggestion}")

        return "\n".join(lines)
