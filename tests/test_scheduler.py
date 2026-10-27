"""
Unit tests for SmartSlot AI - CSP Timetable Solver and Export.
Verifies:
- Feasible configuration generates a valid timetable.
- All constraints are satisfied by solver output.
- Solver honors MRV, LCV, and Forward Checking.
- Solver safely handles infeasible configuration without hanging.
- Timetable CSV export functionality.
- Benchmark comparison execution.
"""

import pytest
import io
import pandas as pd
from smartslot.sample_data import get_default_academic_config, get_infeasible_academic_config
from smartslot.scheduler import TimetableCSP, run_benchmark_comparison
from smartslot.constraints import validate_timetable
from smartslot.data_manager import DataManager


def test_solver_generates_valid_timetable_for_default_config():
    config = get_default_academic_config()
    solver = TimetableCSP(config)
    solution, metrics = solver.solve(use_mrv=True, use_lcv=True, use_forward_checking=True)

    assert metrics.solution_found is True
    assert solution is not None
    assert len(solution) == len(solver.variables)

    # Format solution and validate independently
    formatted = solver.format_solution(solution)
    assert len(formatted) > 0

    report = validate_timetable(formatted, config)
    assert report.is_valid is True
    assert len([c for c in report.conflicts if c.severity == "ERROR"]) == 0


def test_solver_with_heuristics_combinations():
    config = get_default_academic_config()
    solver = TimetableCSP(config)

    # Test with Forward Checking only
    sol_fc, m_fc = solver.solve(use_mrv=False, use_lcv=False, use_forward_checking=True)
    assert m_fc.solution_found is True

    # Test with MRV + FC
    sol_mrv_fc, m_mrv_fc = solver.solve(use_mrv=True, use_lcv=False, use_forward_checking=True)
    assert m_mrv_fc.solution_found is True

    # Test with Full AI (MRV + LCV + FC)
    sol_full, m_full = solver.solve(use_mrv=True, use_lcv=True, use_forward_checking=True)
    assert m_full.solution_found is True


def test_solver_handles_infeasible_configuration():
    config = get_infeasible_academic_config()
    solver = TimetableCSP(config)
    solution, metrics = solver.solve(use_mrv=True, use_lcv=True, use_forward_checking=True, timeout_seconds=5.0)

    # Solver must report failure gracefully without raising uncaught exceptions
    assert metrics.solution_found is False
    assert solution is None


def test_csv_export_contains_generated_assignments(tmp_path):
    config = get_default_academic_config()
    solver = TimetableCSP(config)
    solution, _ = solver.solve()
    records = solver.format_solution(solution)

    dm = DataManager(filepath=str(tmp_path / "test_config.json"))
    dm.current_timetable = records
    csv_data = dm.export_timetable_csv()

    assert len(csv_data) > 0
    df = pd.read_csv(io.StringIO(csv_data))
    assert len(df) == len(records)
    assert "subject_name" in df.columns
    assert "faculty_name" in df.columns
    assert "room_name" in df.columns
    assert "day" in df.columns
    assert "slot_id" in df.columns


def test_benchmark_comparison_structure():
    config = get_default_academic_config()
    comparison = run_benchmark_comparison(config)

    assert "basic" in comparison
    assert "forward_checking" in comparison
    assert "full_ai" in comparison
    assert comparison["solution_available"] is True

    for mode in ["basic", "forward_checking", "full_ai"]:
        data = comparison[mode]
        assert "candidate_assignments_explored" in data
        assert "constraint_checks" in data
        assert "execution_time_seconds" in data
        assert data["solution_found"] is True
