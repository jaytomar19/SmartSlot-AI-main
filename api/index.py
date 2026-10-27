"""
SmartSlot AI - Serverless JSON API (Vercel Python runtime).

Stateless by design: Vercel functions have a read-only filesystem and no
shared memory between invocations, so the browser owns the academic
configuration and sends it with every request. The CSP engine, validators,
and DataManager CRUD rules are reused unchanged from the core modules.
"""

import os
import sys
from dataclasses import asdict
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

# The smartslot package lives at the project root, one level above api/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartslot.sample_data import get_default_academic_config, get_infeasible_academic_config  # noqa: E402
from smartslot.data_manager import DataManager  # noqa: E402
from smartslot.scheduler import TimetableCSP, run_benchmark_comparison  # noqa: E402
from smartslot.constraints import validate_configuration, validate_timetable, Conflict, ValidationReport  # noqa: E402

# Vercel Hobby functions are capped at 60s; keep solver work well inside that.
MAX_SOLVE_TIMEOUT = 25.0
BENCHMARK_TIMEOUT_PER_RUN = 15.0
MAX_BACKTRACKS = 50000

app = FastAPI(title="SmartSlot AI API", docs_url="/api/docs", openapi_url="/api/openapi.json")


# --- Helpers ---
def _config_from(body: Dict[str, Any]) -> Dict[str, Any]:
    config = body.get("config")
    if not isinstance(config, dict):
        raise HTTPException(status_code=400, detail="Request body must include a 'config' object.")
    for key in ("working_days", "time_slots", "classrooms", "faculty", "sections", "subjects"):
        config.setdefault(key, [])
    return config


def _report_from_dict(data: Optional[Dict[str, Any]]) -> Optional[ValidationReport]:
    if not data:
        return None
    return ValidationReport(
        is_valid=data.get("is_valid", False),
        total_scheduled_periods=data.get("total_scheduled_periods", 0),
        total_required_periods=data.get("total_required_periods", 0),
        conflicts=[Conflict(**c) for c in data.get("conflicts", [])],
        summary_stats=data.get("summary_stats", {}),
    )


def _required_periods(config: Dict[str, Any]) -> int:
    return sum(s.get("sessions_per_week", 1) * s.get("duration_periods", 1) for s in config.get("subjects", []))


# Maps mutation action names to DataManager methods (all return (ok, message)).
MUTATIONS = {
    "update_institution": "update_institution",
    "set_working_days": "set_working_days",
    "add_time_slot": "add_time_slot",
    "add_faculty": "add_faculty",
    "update_faculty": "update_faculty",
    "delete_faculty": "delete_faculty",
    "add_subject": "add_subject",
    "update_subject": "update_subject",
    "delete_subject": "delete_subject",
    "add_classroom": "add_classroom",
    "update_classroom": "update_classroom",
    "delete_classroom": "delete_classroom",
}


# --- Routes ---
@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config/default")
def default_config(scenario: str = "default") -> Dict[str, Any]:
    if scenario == "infeasible":
        return get_infeasible_academic_config()
    return get_default_academic_config()


@app.post("/api/config/validate")
def validate_config(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    conflicts = validate_configuration(_config_from(body))
    return {"conflicts": [asdict(c) for c in conflicts]}


@app.post("/api/config/mutate")
def mutate_config(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    config = _config_from(body)
    action = body.get("action")
    if action not in MUTATIONS:
        raise HTTPException(status_code=400, detail=f"Unknown action '{action}'.")

    dm = DataManager(filepath=None, config=config)
    try:
        ok, message = getattr(dm, MUTATIONS[action])(**(body.get("payload") or {}))
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid payload for '{action}': {exc}")
    return {"ok": ok, "message": message, "config": dm.config}


@app.post("/api/solve")
def solve(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    config = _config_from(body)
    opts = body.get("options") or {}

    cfg_conflicts = validate_configuration(config)
    if any(c.severity == "ERROR" for c in cfg_conflicts):
        report = ValidationReport(
            is_valid=False,
            total_scheduled_periods=0,
            total_required_periods=_required_periods(config),
            conflicts=cfg_conflicts,
            summary_stats={"total_conflicts": len(cfg_conflicts), "error_count": len(cfg_conflicts), "warning_count": 0},
        )
        return {
            "success": False,
            "message": "Input academic configuration has severe errors. Resolve them before scheduling.",
            "timetable": [],
            "validation": asdict(report),
            "metrics": None,
        }

    solver = TimetableCSP(config)
    solution, metrics = solver.solve(
        use_mrv=bool(opts.get("use_mrv", True)),
        use_lcv=bool(opts.get("use_lcv", True)),
        use_forward_checking=bool(opts.get("use_fc", True)),
        max_backtracks=min(int(opts.get("max_backtracks", 15000)), MAX_BACKTRACKS),
        timeout_seconds=min(float(opts.get("timeout", 20.0)), MAX_SOLVE_TIMEOUT),
    )
    metrics_dict = metrics.to_dict()
    metrics_dict["trace_events"] = metrics.trace_events

    if solution is not None:
        formatted = solver.format_solution(solution)
        report = validate_timetable(formatted, config)
        return {
            "success": True,
            "message": "Timetable successfully generated and validated!",
            "timetable": formatted,
            "validation": asdict(report),
            "metrics": metrics_dict,
        }

    report = ValidationReport(
        is_valid=False,
        total_scheduled_periods=0,
        total_required_periods=_required_periods(config),
        conflicts=[
            Conflict(
                conflict_type="SOLVER_INFEASIBLE",
                severity="ERROR",
                description="CSP solver explored all search branches (or hit backtrack/time limit) without finding a conflict-free state.",
                entities={"explored_nodes": metrics.candidate_assignments_explored, "backtracks": metrics.backtrack_count},
                suggestion="Review faculty availability, expand classroom capacity, or relax section scheduling density.",
            )
        ],
        summary_stats={"total_conflicts": 1, "error_count": 1, "warning_count": 0},
    )
    return {
        "success": False,
        "message": "No conflict-free timetable could be found with the current constraints.",
        "timetable": [],
        "validation": asdict(report),
        "metrics": metrics_dict,
    }


@app.post("/api/benchmark")
def benchmark(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    return run_benchmark_comparison(_config_from(body), timeout_seconds=BENCHMARK_TIMEOUT_PER_RUN)


@app.post("/api/export/csv", response_class=PlainTextResponse)
def export_csv(body: Dict[str, Any] = Body(...)) -> str:
    dm = DataManager(filepath=None, config=_config_from(body))
    dm.current_timetable = body.get("timetable") or []
    return dm.export_timetable_csv()


@app.post("/api/export/report", response_class=PlainTextResponse)
def export_report(body: Dict[str, Any] = Body(...)) -> str:
    dm = DataManager(filepath=None, config=_config_from(body))
    dm.current_timetable = body.get("timetable") or []
    dm.last_validation = _report_from_dict(body.get("validation"))
    dm.last_solver_metrics = body.get("metrics")
    return dm.generate_audit_summary_markdown()
