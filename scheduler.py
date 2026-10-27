"""
SmartSlot AI - Constraint Satisfaction Problem (CSP) Timetable Engine.

This module implements a full academic timetable generator using:
- CSP formulation (Variables, Domains, Hard Constraints).
- Backtracking Search with recursion and state restoration.
- Minimum Remaining Values (MRV) heuristic with Degree Heuristic tie-breaker.
- Least Constraining Value (LCV) heuristic for value ordering.
- Forward Checking (FC) for early domain pruning and failure detection.
- Detailed search statistics and performance tracing.
"""

from typing import List, Dict, Any, Tuple, Optional, Set
from dataclasses import dataclass, field
import time
import copy


@dataclass
class CSPVariable:
    var_id: str
    subject_id: str
    subject_name: str
    section_id: str
    faculty_id: str
    duration_periods: int
    room_type: str
    expected_students: int
    consecutive: bool = False
    session_index: int = 1

    def __hash__(self):
        return hash(self.var_id)

    def __eq__(self, other):
        if isinstance(other, CSPVariable):
            return self.var_id == other.var_id
        return False


@dataclass(frozen=True)
class CSPValue:
    """
    An assignment value represents:
    - day: name of working day (e.g. 'Monday')
    - start_period_idx: 0-based index in the teaching periods sequence
    - room_id: assigned classroom identifier
    """
    day: str
    start_period_idx: int
    room_id: str


@dataclass
class SolverMetrics:
    sessions_to_schedule: int = 0
    candidate_assignments_explored: int = 0
    backtrack_count: int = 0
    constraint_checks: int = 0
    rejected_assignments: int = 0
    forward_check_prunes: int = 0
    forward_check_wipeouts: int = 0
    execution_time_seconds: float = 0.0
    solution_found: bool = False
    max_search_depth: int = 0
    trace_events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sessions_to_schedule": self.sessions_to_schedule,
            "candidate_assignments_explored": self.candidate_assignments_explored,
            "backtrack_count": self.backtrack_count,
            "constraint_checks": self.constraint_checks,
            "rejected_assignments": self.rejected_assignments,
            "forward_check_prunes": self.forward_check_prunes,
            "forward_check_wipeouts": self.forward_check_wipeouts,
            "execution_time_seconds": round(self.execution_time_seconds, 4),
            "solution_found": self.solution_found,
            "max_search_depth": self.max_search_depth,
        }


class TimetableCSP:
    """
    CSP formulation and Backtracking Solver for academic scheduling.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.working_days: List[str] = config.get("working_days", [])
        
        # Filter all time slots into teaching periods (excluding breaks)
        # and keep the global slot list with indexes
        raw_slots = config.get("time_slots", [])
        self.raw_slots = raw_slots
        self.teaching_slots: List[Dict[str, Any]] = [s for s in raw_slots if not s.get("is_break", False)]
        self.teaching_slot_ids: List[str] = [s["slot_id"] for s in self.teaching_slots]
        self.slot_id_to_obj = {s["slot_id"]: s for s in raw_slots}
        
        # Classroom catalog
        self.classrooms = {r["room_id"]: r for r in config.get("classrooms", [])}
        
        # Faculty catalog
        self.faculty = {f["faculty_id"]: f for f in config.get("faculty", [])}
        
        # Student sections
        self.sections = {s["section_id"]: s for s in config.get("sections", [])}
        
        # Subjects catalog
        self.subjects = {s["subject_id"]: s for s in config.get("subjects", [])}

        # Initialize Variables and Domains
        self.variables: List[CSPVariable] = self._create_variables()
        self.initial_domains: Dict[CSPVariable, List[CSPValue]] = self._generate_initial_domains()

    def _create_variables(self) -> List[CSPVariable]:
        """
        Creates a CSPVariable for each individual weekly session of each subject.
        """
        variables: List[CSPVariable] = []
        for subj in self.config.get("subjects", []):
            sid = subj["subject_id"]
            num_sessions = subj.get("sessions_per_week", 1)
            duration = subj.get("duration_periods", 1)
            consecutive = subj.get("consecutive", duration > 1)
            
            for i in range(1, num_sessions + 1):
                var = CSPVariable(
                    var_id=f"{sid}_S{i}",
                    subject_id=sid,
                    subject_name=subj.get("name", sid),
                    section_id=subj.get("section_id", ""),
                    faculty_id=subj.get("faculty_id", ""),
                    duration_periods=duration,
                    room_type=subj.get("room_type", "Classroom"),
                    expected_students=subj.get("expected_students", 30),
                    consecutive=consecutive,
                    session_index=i
                )
                variables.append(var)
        return variables

    def _generate_initial_domains(self) -> Dict[CSPVariable, List[CSPValue]]:
        """
        Prunes unary constraints upfront:
        - Room type match
        - Room capacity >= expected students
        - Room availability is True
        - Faculty availability on day and period
        - Duration fits within the day's teaching slots
        - For multi-period blocks, periods must be contiguous in teaching slots
        """
        domains: Dict[CSPVariable, List[CSPValue]] = {}
        num_teaching_periods = len(self.teaching_slots)

        for var in self.variables:
            valid_values: List[CSPValue] = []
            dur = var.duration_periods
            fac = self.faculty.get(var.faculty_id)

            # Compatible rooms
            comp_rooms = [
                r for r in self.classrooms.values()
                if r.get("available", True)
                and r.get("room_type") == var.room_type
                and r.get("capacity", 0) >= var.expected_students
            ]

            for day in self.working_days:
                # Faculty working day check
                if fac and day not in fac.get("available_days", self.working_days):
                    continue

                # Possible start periods
                for start_idx in range(0, num_teaching_periods - dur + 1):
                    # Check if faculty is available for all periods in this block
                    faculty_ok = True
                    if fac:
                        unavail_slots = set(fac.get("unavailable_slots", {}).get(day, []))
                        for offset in range(dur):
                            slot_id = self.teaching_slot_ids[start_idx + offset]
                            if slot_id in unavail_slots:
                                faculty_ok = False
                                break
                    if not faculty_ok:
                        continue

                    # For each candidate room
                    for r in comp_rooms:
                        valid_values.append(CSPValue(day=day, start_period_idx=start_idx, room_id=r["room_id"]))

            domains[var] = valid_values
        return domains

    def is_consistent(
        self,
        var: CSPVariable,
        val: CSPValue,
        assignment: Dict[CSPVariable, CSPValue],
        metrics: Optional[SolverMetrics] = None
    ) -> bool:
        """
        Checks if assigning `val` to `var` satisfies all hard constraints
        against current partial `assignment`.
        """
        if metrics:
            metrics.constraint_checks += 1

        val_periods = range(val.start_period_idx, val.start_period_idx + var.duration_periods)
        fac = self.faculty.get(var.faculty_id)
        max_daily = fac.get("max_daily_sessions", 99) if fac else 99
        max_weekly = fac.get("max_weekly_load", 99) if fac else 99

        current_daily_count = 0
        current_weekly_count = 0

        for other_var, other_val in assignment.items():
            if metrics:
                metrics.constraint_checks += 1

            # Check faculty weekly load count
            if other_var.faculty_id == var.faculty_id:
                current_weekly_count += other_var.duration_periods
                if other_val.day == val.day:
                    current_daily_count += other_var.duration_periods

            # Same day overlap checks
            if other_val.day == val.day:
                other_periods = range(other_val.start_period_idx, other_val.start_period_idx + other_var.duration_periods)
                # Check period overlap
                overlap = any(p in other_periods for p in val_periods)
                if overlap:
                    # 1. Faculty Clash: Same faculty cannot be in 2 classes at once
                    if other_var.faculty_id == var.faculty_id:
                        return False
                    # 2. Room Clash: Same room cannot host 2 classes at once
                    if other_val.room_id == val.room_id:
                        return False
                    # 3. Section Clash: Same student section cannot be in 2 classes at once
                    if other_var.section_id == var.section_id:
                        return False

        # Workload bounds
        if (current_weekly_count + var.duration_periods) > max_weekly:
            return False
        if (current_daily_count + var.duration_periods) > max_daily:
            return False

        return True

    def _degree_heuristic(self, var: CSPVariable, unassigned: List[CSPVariable]) -> int:
        """
        Degree heuristic: count how many unassigned variables share a constraint
        with `var` (same faculty or same section).
        """
        count = 0
        for other in unassigned:
            if other != var and (other.faculty_id == var.faculty_id or other.section_id == var.section_id):
                count += 1
        return count

    def select_unassigned_variable(
        self,
        assignment: Dict[CSPVariable, CSPValue],
        domains: Dict[CSPVariable, List[CSPValue]],
        use_mrv: bool = True
    ) -> Optional[CSPVariable]:
        """
        Variable ordering heuristic.
        If use_mrv is True, uses Minimum Remaining Values (MRV) with Degree Heuristic tie-breaker.
        Otherwise picks next unassigned variable in static order.
        """
        unassigned = [v for v in self.variables if v not in assignment]
        if not unassigned:
            return None

        if not use_mrv:
            return unassigned[0]

        # MRV: Choose variable with minimum remaining values
        # Tie-breaker: Maximum degree with remaining unassigned variables
        min_domain_size = float('inf')
        best_candidates: List[CSPVariable] = []

        for var in unassigned:
            d_size = len(domains[var])
            if d_size < min_domain_size:
                min_domain_size = d_size
                best_candidates = [var]
            elif d_size == min_domain_size:
                best_candidates.append(var)

        if len(best_candidates) == 1:
            return best_candidates[0]

        # Tie breaker: Degree Heuristic (most constraining on remaining variables)
        best_candidates.sort(key=lambda v: self._degree_heuristic(v, unassigned), reverse=True)
        return best_candidates[0]

    def order_domain_values(
        self,
        var: CSPVariable,
        assignment: Dict[CSPVariable, CSPValue],
        domains: Dict[CSPVariable, List[CSPValue]],
        use_lcv: bool = True
    ) -> List[CSPValue]:
        """
        Value ordering heuristic.
        If use_lcv is True, orders values by Least Constraining Value:
        Values that rule out the fewest choices for neighboring unassigned variables are tried first.
        """
        candidate_values = domains[var]
        if not use_lcv or len(candidate_values) <= 1:
            return candidate_values

        unassigned_neighbors = [
            v for v in self.variables 
            if v not in assignment and v != var and (v.faculty_id == var.faculty_id or v.section_id == var.section_id)
        ]

        if not unassigned_neighbors:
            return candidate_values

        def count_eliminated_choices(val: CSPValue) -> int:
            eliminated = 0
            val_periods = range(val.start_period_idx, val.start_period_idx + var.duration_periods)
            for neighbor in unassigned_neighbors:
                for n_val in domains[neighbor]:
                    if n_val.day == val.day:
                        n_periods = range(n_val.start_period_idx, n_val.start_period_idx + neighbor.duration_periods)
                        if any(p in n_periods for p in val_periods):
                            # Conflict with neighbor
                            if (neighbor.faculty_id == var.faculty_id or 
                                neighbor.section_id == var.section_id or 
                                n_val.room_id == val.room_id):
                                eliminated += 1
            return eliminated

        # Sort ascending by eliminated choices (least constraining first)
        return sorted(candidate_values, key=count_eliminated_choices)

    def forward_check(
        self,
        var: CSPVariable,
        val: CSPValue,
        assignment: Dict[CSPVariable, CSPValue],
        domains: Dict[CSPVariable, List[CSPValue]],
        metrics: Optional[SolverMetrics] = None
    ) -> Tuple[bool, Dict[CSPVariable, List[CSPValue]]]:
        """
        Forward Checking:
        Temporarily prunes conflicting values from domains of unassigned variables.
        Returns:
            (success: bool, pruned_map: Dict[CSPVariable, List[CSPValue]])
        If any unassigned variable's domain becomes empty, returns False (domain wipeout).
        """
        val_periods = range(val.start_period_idx, val.start_period_idx + var.duration_periods)
        pruned_map: Dict[CSPVariable, List[CSPValue]] = {}

        for other_var in self.variables:
            if other_var in assignment or other_var == var:
                continue

            current_domain = domains[other_var]
            valid_remaining: List[CSPValue] = []
            removed_for_var: List[CSPValue] = []

            for other_val in current_domain:
                is_clash = False
                if other_val.day == val.day:
                    other_periods = range(other_val.start_period_idx, other_val.start_period_idx + other_var.duration_periods)
                    overlap = any(p in other_periods for p in val_periods)
                    if overlap:
                        if (other_var.faculty_id == var.faculty_id or
                            other_var.section_id == var.section_id or
                            other_val.room_id == val.room_id):
                            is_clash = True

                if is_clash:
                    removed_for_var.append(other_val)
                    if metrics:
                        metrics.forward_check_prunes += 1
                else:
                    valid_remaining.append(other_val)

            if removed_for_var:
                pruned_map[other_var] = removed_for_var
                domains[other_var] = valid_remaining

            # Domain wipeout detected
            if len(valid_remaining) == 0:
                if metrics:
                    metrics.forward_check_wipeouts += 1
                return False, pruned_map

        return True, pruned_map

    def restore_pruned_domains(
        self,
        pruned_map: Dict[CSPVariable, List[CSPValue]],
        domains: Dict[CSPVariable, List[CSPValue]]
    ):
        """Restores pruned domain values upon backtracking."""
        for var, values in pruned_map.items():
            domains[var].extend(values)

    def solve(
        self,
        use_mrv: bool = True,
        use_lcv: bool = True,
        use_forward_checking: bool = True,
        max_backtracks: int = 15000,
        timeout_seconds: float = 30.0
    ) -> Tuple[Optional[Dict[CSPVariable, CSPValue]], SolverMetrics]:
        """
        Executes CSP Backtracking Search with configured heuristics and safety bounds.
        """
        metrics = SolverMetrics(sessions_to_schedule=len(self.variables))
        assignment: Dict[CSPVariable, CSPValue] = {}
        # Working copy of domains for forward checking
        domains: Dict[CSPVariable, List[CSPValue]] = {
            v: list(vals) for v, vals in self.initial_domains.items()
        }

        # Check for immediate empty domains before search starts
        for v, d in domains.items():
            if len(d) == 0:
                metrics.solution_found = False
                metrics.trace_events.append({
                    "type": "IMMEDIATE_FAILURE",
                    "variable": v.var_id,
                    "reason": f"No valid slots or rooms available for subject '{v.subject_name}' (room type '{v.room_type}')."
                })
                return None, metrics

        start_time = time.time()

        def backtrack(depth: int) -> bool:
            metrics.max_search_depth = max(metrics.max_search_depth, depth)

            # Check time limit & backtrack limit
            if (time.time() - start_time) > timeout_seconds:
                metrics.trace_events.append({"type": "TIMEOUT", "depth": depth})
                return False
            if metrics.backtrack_count >= max_backtracks:
                metrics.trace_events.append({"type": "MAX_BACKTRACKS_EXCEEDED", "depth": depth})
                return False

            # Base case: all variables assigned
            if len(assignment) == len(self.variables):
                return True

            var = self.select_unassigned_variable(assignment, domains, use_mrv=use_mrv)
            if var is None:
                return True

            ordered_values = self.order_domain_values(var, assignment, domains, use_lcv=use_lcv)

            for val in ordered_values:
                metrics.candidate_assignments_explored += 1

                if self.is_consistent(var, val, assignment, metrics):
                    assignment[var] = val

                    # Record trace event for viva demo (keep size bounded)
                    if len(metrics.trace_events) < 50:
                        metrics.trace_events.append({
                            "type": "ASSIGN",
                            "step": metrics.candidate_assignments_explored,
                            "variable": var.var_id,
                            "subject": var.subject_name,
                            "day": val.day,
                            "period": self.teaching_slot_ids[val.start_period_idx],
                            "room": val.room_id
                        })

                    if use_forward_checking:
                        fc_ok, pruned_map = self.forward_check(var, val, assignment, domains, metrics)
                        if fc_ok:
                            if backtrack(depth + 1):
                                return True
                        # Forward checking detected future wipeout, undo pruning
                        self.restore_pruned_domains(pruned_map, domains)
                    else:
                        if backtrack(depth + 1):
                            return True

                    # Backtrack step
                    del assignment[var]
                    metrics.backtrack_count += 1
                    metrics.rejected_assignments += 1

                    if len(metrics.trace_events) < 50:
                        metrics.trace_events.append({
                            "type": "BACKTRACK",
                            "variable": var.var_id,
                            "backtrack_no": metrics.backtrack_count
                        })
                else:
                    metrics.rejected_assignments += 1

            return False

        success = backtrack(0)
        metrics.execution_time_seconds = time.time() - start_time
        metrics.solution_found = success

        if success:
            return assignment, metrics
        return None, metrics

    def format_solution(self, assignment: Optional[Dict[CSPVariable, CSPValue]]) -> List[Dict[str, Any]]:
        """
        Translates raw CSP assignment into clean, structured timetable records.
        Handles expansion of multi-period lab blocks into individual period units.
        """
        if not assignment:
            return []

        results: List[Dict[str, Any]] = []
        for var, val in assignment.items():
            fac = self.faculty.get(var.faculty_id, {})
            room = self.classrooms.get(val.room_id, {})
            subj = self.subjects.get(var.subject_id, {})
            dur = var.duration_periods

            for offset in range(dur):
                period_idx = val.start_period_idx + offset
                slot = self.teaching_slots[period_idx]

                record = {
                    "session_id": var.var_id,
                    "subject_id": var.subject_id,
                    "subject_name": var.subject_name,
                    "section_id": var.section_id,
                    "faculty_id": var.faculty_id,
                    "faculty_name": fac.get("name", var.faculty_id),
                    "room_id": val.room_id,
                    "room_name": room.get("name", val.room_id),
                    "room_type": room.get("room_type", var.room_type),
                    "day": val.day,
                    "slot_id": slot["slot_id"],
                    "slot_name": slot["name"],
                    "start_time": slot["start_time"],
                    "end_time": slot["end_time"],
                    "duration_periods": dur,
                    "is_consecutive_part": offset + 1,
                    "expected_students": var.expected_students,
                }
                results.append(record)

        # Sort chronologically by day and slot index for clean presentation
        day_order = {d: i for i, d in enumerate(self.working_days)}
        slot_order = {s["slot_id"]: i for i, s in enumerate(self.raw_slots)}

        results.sort(key=lambda x: (
            day_order.get(x["day"], 99),
            slot_order.get(x["slot_id"], 99),
            x["section_id"]
        ))
        return results


def run_benchmark_comparison(config: Dict[str, Any], timeout_seconds: float = 20.0) -> Dict[str, Any]:
    """
    Executes a side-by-side empirical benchmark of:
    1. Basic Backtracking (no MRV, no LCV, no Forward Checking)
    2. Backtracking + Forward Checking
    3. Fully Optimized AI Backtracking (MRV + LCV + Forward Checking)

    Uses the exact same problem instance for strict fairness.
    """
    solver = TimetableCSP(config)

    # 1. Basic Backtracking
    _, metrics_basic = solver.solve(
        use_mrv=False,
        use_lcv=False,
        use_forward_checking=False,
        max_backtracks=20000,
        timeout_seconds=timeout_seconds
    )

    # 2. Backtracking + Forward Checking
    _, metrics_fc = solver.solve(
        use_mrv=False,
        use_lcv=False,
        use_forward_checking=True,
        max_backtracks=20000,
        timeout_seconds=timeout_seconds
    )

    # 3. Full Optimization (MRV + LCV + FC)
    solution_full, metrics_full = solver.solve(
        use_mrv=True,
        use_lcv=True,
        use_forward_checking=True,
        max_backtracks=20000,
        timeout_seconds=timeout_seconds
    )

    return {
        "basic": metrics_basic.to_dict(),
        "forward_checking": metrics_fc.to_dict(),
        "full_ai": metrics_full.to_dict(),
        "solution_available": solution_full is not None,
    }
