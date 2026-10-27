"""
SmartSlot AI - Intelligent Academic Timetable Generator
Using Constraint Satisfaction Problems (CSP) and Backtracking Search.

Main Streamlit Application.
"""

import streamlit as st
import pandas as pd
import json
import time
from typing import Dict, Any, List, Optional

from sample_data import get_default_academic_config, get_infeasible_academic_config
from data_manager import DataManager
from scheduler import TimetableCSP, run_benchmark_comparison
from constraints import validate_configuration, validate_timetable, Conflict, ValidationReport

# --- Page Configuration ---
st.set_page_config(
    page_title="SmartSlot AI | Academic Timetable Generator",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom Styling ---
st.markdown("""
<style>
    /* Global Styles */
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #475569;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0F172A;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .badge-theory {
        background-color: #DBEAFE;
        color: #1E40AF;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-lab {
        background-color: #FEF3C7;
        color: #92400E;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-success {
        background-color: #D1FAE5;
        color: #065F46;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .badge-danger {
        background-color: #FEE2E2;
        color: #991B1B;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .badge-warning {
        background-color: #FEF3C7;
        color: #92400E;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .timetable-cell {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 6px;
        padding: 8px;
        margin-bottom: 6px;
        font-size: 0.82rem;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }
    .timetable-break {
        background-color: #F1F5F9;
        border: 1px dashed #CBD5E1;
        border-radius: 6px;
        padding: 10px;
        text-align: center;
        color: #64748B;
        font-style: italic;
        font-weight: 500;
    }
    .timetable-empty {
        background-color: #FAFAFA;
        border: 1px dashed #E2E8F0;
        border-radius: 6px;
        padding: 10px;
        text-align: center;
        color: #94A3B8;
        font-size: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)


# --- Session State Initialization ---
if "data_manager" not in st.session_state:
    st.session_state.data_manager = DataManager()

dm: DataManager = st.session_state.data_manager

# Ensure timetable exists or is cached
if "timetable_results" not in st.session_state:
    st.session_state.timetable_results = dm.current_timetable

if "validation_report" not in st.session_state:
    st.session_state.validation_report = dm.last_validation

if "solver_metrics" not in st.session_state:
    st.session_state.solver_metrics = dm.last_solver_metrics

if "benchmark_results" not in st.session_state:
    st.session_state.benchmark_results = None


# --- Helper Methods ---
def solve_current_timetable(use_mrv=True, use_lcv=True, use_fc=True, max_backtracks=15000, timeout=20.0):
    """Executes the CSP solver and validates the resulting timetable independently."""
    cfg = dm.config
    
    # 1. Pre-validation of configuration
    cfg_conflicts = validate_configuration(cfg)
    has_errors = any(c.severity == "ERROR" for c in cfg_conflicts)
    
    if has_errors:
        st.session_state.timetable_results = []
        dm.current_timetable = []
        report = ValidationReport(
            is_valid=False,
            total_scheduled_periods=0,
            total_required_periods=sum(s.get("sessions_per_week", 1) * s.get("duration_periods", 1) for s in cfg.get("subjects", [])),
            conflicts=cfg_conflicts,
            summary_stats={"total_conflicts": len(cfg_conflicts), "error_count": len(cfg_conflicts), "warning_count": 0}
        )
        st.session_state.validation_report = report
        dm.last_validation = report
        return False, "Input academic configuration has severe errors. Resolve them before scheduling."

    # 2. Run CSP solver
    solver = TimetableCSP(cfg)
    solution, metrics = solver.solve(
        use_mrv=use_mrv,
        use_lcv=use_lcv,
        use_forward_checking=use_fc,
        max_backtracks=max_backtracks,
        timeout_seconds=timeout
    )
    
    st.session_state.solver_metrics = metrics.to_dict()
    dm.last_solver_metrics = metrics.to_dict()

    if solution is not None:
        formatted = solver.format_solution(solution)
        st.session_state.timetable_results = formatted
        dm.current_timetable = formatted
        
        # 3. Independent Validation Pass
        report = validate_timetable(formatted, cfg)
        st.session_state.validation_report = report
        dm.last_validation = report
        return True, "Timetable successfully generated and validated!"
    else:
        st.session_state.timetable_results = []
        dm.current_timetable = []
        report = ValidationReport(
            is_valid=False,
            total_scheduled_periods=0,
            total_required_periods=sum(s.get("sessions_per_week", 1) * s.get("duration_periods", 1) for s in cfg.get("subjects", [])),
            conflicts=[
                Conflict(
                    conflict_type="SOLVER_INFEASIBLE",
                    severity="ERROR",
                    description="CSP solver explored all search branches (or hit backtrack/time limit) without finding a conflict-free state.",
                    entities={"explored_nodes": metrics.candidate_assignments_explored, "backtracks": metrics.backtrack_count},
                    suggestion="Review faculty availability, expand classroom capacity, or relax section scheduling density."
                )
            ],
            summary_stats={"total_conflicts": 1, "error_count": 1, "warning_count": 0}
        )
        st.session_state.validation_report = report
        dm.last_validation = report
        return False, "No conflict-free timetable could be found with the current constraints."


# --- Sidebar Navigation ---
st.sidebar.image("https://img.icons8.com/color/96/calendar--v1.png", width=64)
st.sidebar.title("SmartSlot AI")
st.sidebar.caption("Intelligent CSP Timetable Generator")

menu_choice = st.sidebar.radio(
    "Navigation",
    [
        "📊 Dashboard",
        "⚙️ Academic Configuration",
        "👨‍🏫 Faculty Management",
        "📚 Subject & Course Management",
        "🏫 Classroom Management",
        "🤖 AI Timetable Generator",
        "🔍 Conflict Detection & Explanation",
        "📅 Timetable Viewer",
        "📈 Performance & Algorithm Analysis",
        "💾 Export & Reset",
        "📖 Academic Viva & Algorithm Docs",
    ]
)

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Institution:**\n*{dm.config.get('institution_name', 'Northstar Institute')}*")
st.sidebar.markdown(f"**Term:** *{dm.config.get('academic_term', 'Fall 2026')}*")


# ==============================================================================
# SECTION A: DASHBOARD
# ==============================================================================
if menu_choice == "📊 Dashboard":
    st.markdown('<div class="main-header">SmartSlot AI: Academic Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Constraint Satisfaction Problem (CSP) Timetable Management System</div>', unsafe_allow_html=True)

    cfg = dm.config
    num_subjects = len(cfg.get("subjects", []))
    num_faculty = len(cfg.get("faculty", []))
    num_rooms = len(cfg.get("classrooms", []))
    num_sections = len(cfg.get("sections", []))

    total_req_periods = sum(s.get("sessions_per_week", 1) * s.get("duration_periods", 1) for s in cfg.get("subjects", []))
    teaching_slots = [s for s in cfg.get("time_slots", []) if not s.get("is_break", False)]
    total_avail_slots_per_room = len(cfg.get("working_days", [])) * len(teaching_slots)
    total_capacity_slots = total_avail_slots_per_room * num_rooms

    scheduled_periods = len(st.session_state.timetable_results)
    val_report = st.session_state.validation_report

    # Quick KPIs
    kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5 = st.columns(5)
    with kpi_col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{num_subjects}</div>
            <div class="metric-label">Subjects</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{num_faculty}</div>
            <div class="metric-label">Faculty</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{num_rooms}</div>
            <div class="metric-label">Classrooms</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{total_req_periods}</div>
            <div class="metric-label">Required Periods</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_col5:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{total_capacity_slots}</div>
            <div class="metric-label">Slot Capacity</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Status Banner
    status_col1, status_col2 = st.columns([2, 1])
    with status_col1:
        st.subheader("Timetable Generation Status")
        if scheduled_periods == 0:
            st.info("ℹ️ **Status: Pending Generation.** No timetable has been generated for the active academic term.")
        elif val_report and val_report.is_valid:
            st.success(f"✅ **Status: Valid & Conflict-Free.** Successfully scheduled {scheduled_periods} / {total_req_periods} periods across {len(cfg.get('working_days', []))} working days with 0 hard constraint violations.")
        else:
            conflict_count = len(val_report.conflicts) if val_report else 0
            st.error(f"⚠️ **Status: Conflicts Detected.** Schedule contains {conflict_count} issues or unscheduled sessions requiring administrator resolution.")

        # Quick Action
        c_btn1, c_btn2 = st.columns([1, 1])
        with c_btn1:
            if st.button("🚀 Generate Conflict-Free Timetable (AI CSP)", width="stretch", type="primary"):
                with st.spinner("AI Solver exploring constraint graph via Backtracking with MRV & Forward Checking..."):
                    success, msg = solve_current_timetable()
                    if success:
                        st.toast(msg, icon="✅")
                    else:
                        st.toast(msg, icon="❌")
                    st.rerun()
        with c_btn2:
            if st.button("🔍 View Conflict Report", width="stretch"):
                st.session_state["menu_nav"] = "🔍 Conflict Detection & Explanation"
                st.rerun()

    with status_col2:
        st.subheader("Scheduling Health")
        health_data = {
            "Metric": ["Scheduled Periods", "Unscheduled Periods", "Active Conflicts", "Solver Execution"],
            "Value": [
                f"{scheduled_periods} / {total_req_periods}",
                f"{max(0, total_req_periods - scheduled_periods)}",
                f"{len(val_report.conflicts) if val_report else 0}",
                f"{st.session_state.solver_metrics.get('execution_time_seconds', 0.0) if st.session_state.solver_metrics else 'N/A'} s"
            ]
        }
        st.dataframe(pd.DataFrame(health_data), hide_index=True, width="stretch")

    st.markdown("---")
    st.subheader("Constraint Satisfaction Problem (CSP) Overview")
    st.markdown("""
    Academic timetabling is an **NP-complete** combinatorial optimization problem modeled formally as a Constraint Satisfaction Problem:
    $$\\mathcal{P} = \\langle X, D, C \\rangle$$
    - **Variables ($X$):** Individual weekly class sessions required for each academic subject.
    - **Domains ($D$):** Feasible triples of `(Day, Time Slot, Classroom)` pruned by unary constraints (faculty availability, room type compatibility, and capacity).
    - **Hard Constraints ($C$):** Zero-overlap guarantees for faculty members, student sections, classrooms, and breaks, plus daily and weekly workload caps.
    - **Search Engine:** Intelligent Backtracking Search augmented by **Minimum Remaining Values (MRV)** variable ordering, **Least Constraining Value (LCV)** value ordering, and **Forward Checking (FC)** for early dead-end detection.
    """)


# ==============================================================================
# SECTION B: ACADEMIC CONFIGURATION
# ==============================================================================
elif menu_choice == "⚙️ Academic Configuration":
    st.markdown('<div class="main-header">Academic Configuration</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Configure institutional working days, daily period slots, and break periods</div>', unsafe_allow_html=True)

    cfg = dm.config

    with st.expander("🏛️ Institution & Term Details", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            inst_name = st.text_input("Institution Name", value=cfg.get("institution_name", ""))
            dept_name = st.text_input("Department", value=cfg.get("department", ""))
        with col2:
            term_name = st.text_input("Academic Term", value=cfg.get("academic_term", ""))
            
        if st.button("Save Institution Details"):
            cfg["institution_name"] = inst_name.strip()
            cfg["department"] = dept_name.strip()
            cfg["academic_term"] = term_name.strip()
            dm.save_config()
            st.success("Institution details updated.")

    st.subheader("Working Days")
    all_possible_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    selected_days = st.multiselect(
        "Select Active Working Days",
        options=all_possible_days,
        default=cfg.get("working_days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
    )
    if st.button("Update Working Days"):
        if not selected_days:
            st.error("At least one working day must be active.")
        else:
            cfg["working_days"] = selected_days
            dm.save_config()
            st.success(f"Working days set to: {', '.join(selected_days)}")

    st.subheader("Daily Time Slots & Break Schedule")
    slots_df = pd.DataFrame(cfg.get("time_slots", []))
    st.dataframe(slots_df, width="stretch", hide_index=True)

    st.markdown("### Add / Configure Time Slot")
    with st.form("add_slot_form"):
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            new_slot_id = st.text_input("Slot ID", placeholder="e.g. P7")
        with c2:
            new_slot_name = st.text_input("Slot Name", placeholder="e.g. Period 7")
        with c3:
            new_start = st.text_input("Start Time", value="16:00")
        with c4:
            new_end = st.text_input("End Time", value="17:00")
        with c5:
            new_is_break = st.checkbox("Is Break Period?")
        
        submitted = st.form_submit_button("Add Time Slot")
        if submitted:
            new_slot_id = new_slot_id.strip()
            if not new_slot_id:
                st.error("Slot ID cannot be empty.")
            elif any(s["slot_id"] == new_slot_id for s in cfg["time_slots"]):
                st.error(f"Slot ID '{new_slot_id}' already exists.")
            else:
                cfg["time_slots"].append({
                    "slot_id": new_slot_id,
                    "name": new_slot_name.strip() or new_slot_id,
                    "start_time": new_start.strip(),
                    "end_time": new_end.strip(),
                    "is_break": new_is_break
                })
                dm.save_config()
                st.success(f"Slot '{new_slot_id}' added.")
                st.rerun()

    st.subheader("Student Sections")
    sec_df = pd.DataFrame(cfg.get("sections", []))
    st.dataframe(sec_df, width="stretch", hide_index=True)


# ==============================================================================
# SECTION C: FACULTY MANAGEMENT
# ==============================================================================
elif menu_choice == "👨‍🏫 Faculty Management":
    st.markdown('<div class="main-header">Faculty Management</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Manage teaching faculty, workloads, and day/slot availability restrictions</div>', unsafe_allow_html=True)

    faculty_list = dm.config.get("faculty", [])
    
    # Display Faculty Table
    summary_data = []
    for f in faculty_list:
        summary_data.append({
            "Faculty ID": f["faculty_id"],
            "Name": f["name"],
            "Email": f.get("email", ""),
            "Subjects Taught": ", ".join(f.get("subjects", [])),
            "Max Daily": f.get("max_daily_sessions", 3),
            "Max Weekly Load": f.get("max_weekly_load", 12),
            "Available Days": ", ".join(f.get("available_days", [])),
            "Unavailable Slots": json.dumps(f.get("unavailable_slots", {}))
        })
    st.dataframe(pd.DataFrame(summary_data), width="stretch", hide_index=True)

    tab1, tab2, tab3 = st.tabs(["➕ Add New Faculty", "✏️ Edit Faculty", "🗑️ Delete Faculty"])

    with tab1:
        st.markdown("### Add Faculty Member")
        with st.form("add_faculty_form"):
            c1, c2 = st.columns(2)
            with c1:
                f_id = st.text_input("Faculty ID *", placeholder="e.g. FAC07")
                f_name = st.text_input("Full Name *", placeholder="e.g. Dr. Donald Knuth")
                f_email = st.text_input("Email", placeholder="e.g. d.knuth@nit.edu")
            with c2:
                f_max_daily = st.number_input("Max Teaching Periods / Day", min_value=1, max_value=8, value=3)
                f_max_weekly = st.number_input("Max Teaching Periods / Week", min_value=1, max_value=30, value=12)
                f_days = st.multiselect("Available Working Days", options=dm.config.get("working_days", []), default=dm.config.get("working_days", []))

            add_submit = st.form_submit_button("Add Faculty")
            if add_submit:
                ok, msg = dm.add_faculty(
                    faculty_id=f_id,
                    name=f_name,
                    email=f_email,
                    subjects=[],
                    max_daily=f_max_daily,
                    max_weekly=f_max_weekly,
                    available_days=f_days
                )
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    with tab2:
        st.markdown("### Edit Faculty Availability & Load Limits")
        fac_options = {f["faculty_id"]: f"{f['faculty_id']} - {f['name']}" for f in faculty_list}
        selected_fac_id = st.selectbox("Select Faculty Member", options=list(fac_options.keys()), format_func=lambda x: fac_options[x])

        current_fac = next((f for f in faculty_list if f["faculty_id"] == selected_fac_id), None)
        if current_fac:
            with st.form("edit_faculty_form"):
                e_name = st.text_input("Name", value=current_fac["name"])
                e_email = st.text_input("Email", value=current_fac.get("email", ""))
                e_daily = st.number_input("Max Daily Periods", min_value=1, max_value=8, value=current_fac.get("max_daily_sessions", 3))
                e_weekly = st.number_input("Max Weekly Load", min_value=1, max_value=30, value=current_fac.get("max_weekly_load", 12))
                e_days = st.multiselect("Available Working Days", options=dm.config.get("working_days", []), default=current_fac.get("available_days", []))

                st.markdown("**Slot-Level Unavailability Restrictions**")
                teaching_slots_list = [s["slot_id"] for s in dm.config.get("time_slots", []) if not s.get("is_break", False)]
                unavail_day = st.selectbox("Restriction Day", options=dm.config.get("working_days", []))
                existing_unavail = current_fac.get("unavailable_slots", {}).get(unavail_day, [])
                unavail_slots = st.multiselect(f"Unavailable slots on {unavail_day}", options=teaching_slots_list, default=existing_unavail)

                save_edit = st.form_submit_button("Update Faculty Information")
                if save_edit:
                    unavail_dict = copy.deepcopy(current_fac.get("unavailable_slots", {}))
                    if unavail_slots:
                        unavail_dict[unavail_day] = unavail_slots
                    elif unavail_day in unavail_dict:
                        del unavail_dict[unavail_day]

                    ok, msg = dm.update_faculty(
                        faculty_id=selected_fac_id,
                        name=e_name,
                        email=e_email,
                        subjects=current_fac.get("subjects", []),
                        max_daily=e_daily,
                        max_weekly=e_weekly,
                        available_days=e_days,
                        unavailable_slots=unavail_dict
                    )
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    with tab3:
        st.markdown("### Delete Faculty Member")
        del_fac_id = st.selectbox("Select Faculty to Remove", options=list(fac_options.keys()), format_func=lambda x: fac_options[x], key="del_fac")
        if st.button("Delete Faculty Member", type="primary"):
            ok, msg = dm.delete_faculty(del_fac_id)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)


# ==============================================================================
# SECTION D: SUBJECT & COURSE MANAGEMENT
# ==============================================================================
elif menu_choice == "📚 Subject & Course Management":
    st.markdown('<div class="main-header">Subject & Course Management</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Manage course curricula, assigned faculty, room type requirements, and multi-period sessions</div>', unsafe_allow_html=True)

    subjects = dm.config.get("subjects", [])
    fac_map = {f["faculty_id"]: f["name"] for f in dm.config.get("faculty", [])}
    sec_map = {s["section_id"]: s["name"] for s in dm.config.get("sections", [])}

    # Subject Overview Table
    sub_table = []
    for s in subjects:
        sub_table.append({
            "Subject ID": s["subject_id"],
            "Course Name": s["name"],
            "Section": sec_map.get(s.get("section_id"), s.get("section_id")),
            "Assigned Faculty": fac_map.get(s.get("faculty_id"), s.get("faculty_id")),
            "Sessions / Week": s.get("sessions_per_week", 1),
            "Duration (Periods)": s.get("duration_periods", 1),
            "Room Type": s.get("room_type", "Classroom"),
            "Expected Students": s.get("expected_students", 30),
            "Consecutive": "Yes" if s.get("consecutive", False) else "No",
        })
    st.dataframe(pd.DataFrame(sub_table), width="stretch", hide_index=True)

    tab1, tab2, tab3 = st.tabs(["➕ Add New Subject", "✏️ Edit Subject", "🗑️ Delete Subject"])

    with tab1:
        st.markdown("### Register New Subject / Course")
        with st.form("add_subject_form"):
            c1, c2 = st.columns(2)
            with c1:
                s_id = st.text_input("Subject ID *", placeholder="e.g. CS109")
                s_name = st.text_input("Subject Name *", placeholder="e.g. Machine Learning")
                s_sec = st.selectbox("Student Section", options=[s["section_id"] for s in dm.config.get("sections", [])])
                s_fac = st.selectbox("Assigned Faculty Member", options=list(fac_map.keys()), format_func=lambda x: f"{x} - {fac_map[x]}")
            with c2:
                s_sessions = st.number_input("Sessions per Week", min_value=1, max_value=6, value=3)
                s_duration = st.number_input("Session Duration (Periods)", min_value=1, max_value=3, value=1)
                s_room_type = st.selectbox("Required Room Type", options=["Classroom", "Laboratory", "Seminar Hall"])
                s_students = st.number_input("Expected Student Enrollment", min_value=1, max_value=100, value=35)
                s_consecutive = st.checkbox("Consecutive Periods Required (Recommended for Labs)", value=(s_duration > 1))

            add_sub_submit = st.form_submit_button("Add Subject")
            if add_sub_submit:
                ok, msg = dm.add_subject(
                    subject_id=s_id,
                    name=s_name,
                    section_id=s_sec,
                    faculty_id=s_fac,
                    sessions_per_week=s_sessions,
                    duration_periods=s_duration,
                    room_type=s_room_type,
                    expected_students=s_students,
                    consecutive=s_consecutive
                )
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    with tab2:
        st.markdown("### Edit Existing Subject")
        s_options = {s["subject_id"]: f"{s['subject_id']} - {s['name']}" for s in subjects}
        selected_s_id = st.selectbox("Select Subject", options=list(s_options.keys()), format_func=lambda x: s_options[x])

        curr_s = next((s for s in subjects if s["subject_id"] == selected_s_id), None)
        if curr_s:
            with st.form("edit_subj_form"):
                e_sname = st.text_input("Subject Name", value=curr_s["name"])
                e_ssec = st.selectbox("Section", options=[s["section_id"] for s in dm.config.get("sections", [])], index=[s["section_id"] for s in dm.config.get("sections", [])].index(curr_s.get("section_id", "CS-A")))
                e_sfac = st.selectbox("Assigned Faculty", options=list(fac_map.keys()), index=list(fac_map.keys()).index(curr_s.get("faculty_id", list(fac_map.keys())[0])), format_func=lambda x: f"{x} - {fac_map[x]}")
                e_ssess = st.number_input("Sessions / Week", min_value=1, max_value=6, value=curr_s.get("sessions_per_week", 1))
                e_sdur = st.number_input("Duration (Periods)", min_value=1, max_value=3, value=curr_s.get("duration_periods", 1))
                e_sroom = st.selectbox("Room Type", options=["Classroom", "Laboratory", "Seminar Hall"], index=["Classroom", "Laboratory", "Seminar Hall"].index(curr_s.get("room_type", "Classroom")))
                e_sstud = st.number_input("Expected Students", min_value=1, max_value=100, value=curr_s.get("expected_students", 35))
                e_sconsec = st.checkbox("Consecutive Periods", value=curr_s.get("consecutive", False))

                save_s_btn = st.form_submit_button("Update Subject")
                if save_s_btn:
                    ok, msg = dm.update_subject(
                        subject_id=selected_s_id,
                        name=e_sname,
                        section_id=e_ssec,
                        faculty_id=e_sfac,
                        sessions_per_week=e_ssess,
                        duration_periods=e_sdur,
                        room_type=e_sroom,
                        expected_students=e_sstud,
                        consecutive=e_sconsec
                    )
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    with tab3:
        st.markdown("### Delete Subject")
        del_s_id = st.selectbox("Select Subject to Remove", options=list(s_options.keys()), format_func=lambda x: s_options[x], key="del_s")
        if st.button("Delete Subject", type="primary"):
            ok, msg = dm.delete_subject(del_s_id)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)


# ==============================================================================
# SECTION E: CLASSROOM MANAGEMENT
# ==============================================================================
elif menu_choice == "🏫 Classroom Management":
    st.markdown('<div class="main-header">Classroom & Laboratory Management</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Manage lecture halls, laboratory spaces, seating capacities, and operational availability</div>', unsafe_allow_html=True)

    rooms = dm.config.get("classrooms", [])
    st.dataframe(pd.DataFrame(rooms), width="stretch", hide_index=True)

    tab1, tab2, tab3 = st.tabs(["➕ Add Classroom", "✏️ Edit / Toggle Room", "🗑️ Delete Classroom"])

    with tab1:
        st.markdown("### Register New Classroom / Lab")
        with st.form("add_room_form"):
            c1, c2 = st.columns(2)
            with c1:
                r_id = st.text_input("Room ID *", placeholder="e.g. R204")
                r_name = st.text_input("Room Name", placeholder="e.g. Multimedia Hall")
            with c2:
                r_cap = st.number_input("Seating Capacity", min_value=1, max_value=200, value=40)
                r_type = st.selectbox("Room Classification", options=["Classroom", "Laboratory", "Seminar Hall"])
                r_avail = st.checkbox("Room is Operational / Available", value=True)

            r_submit = st.form_submit_button("Add Classroom")
            if r_submit:
                ok, msg = dm.add_classroom(r_id, r_name, r_cap, r_type, r_avail)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    with tab2:
        st.markdown("### Update Classroom Properties")
        r_options = {r["room_id"]: f"{r['room_id']} - {r['name']} ({r['room_type']})" for r in rooms}
        sel_rid = st.selectbox("Select Room", options=list(r_options.keys()), format_func=lambda x: r_options[x])

        curr_r = next((r for r in rooms if r["room_id"] == sel_rid), None)
        if curr_r:
            with st.form("edit_room_form"):
                e_rname = st.text_input("Room Name", value=curr_r["name"])
                e_rcap = st.number_input("Capacity", min_value=1, max_value=200, value=curr_r.get("capacity", 40))
                e_rtype = st.selectbox("Room Type", options=["Classroom", "Laboratory", "Seminar Hall"], index=["Classroom", "Laboratory", "Seminar Hall"].index(curr_r.get("room_type", "Classroom")))
                e_ravail = st.checkbox("Available for Scheduling", value=curr_r.get("available", True))

                save_r_btn = st.form_submit_button("Update Room")
                if save_r_btn:
                    ok, msg = dm.update_classroom(sel_rid, e_rname, e_rcap, e_rtype, e_ravail)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    with tab3:
        st.markdown("### Delete Classroom")
        del_rid = st.selectbox("Select Room to Remove", options=list(r_options.keys()), format_func=lambda x: r_options[x], key="del_r")
        if st.button("Delete Room", type="primary"):
            ok, msg = dm.delete_classroom(del_rid)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)


# ==============================================================================
# SECTION F: AI TIMETABLE GENERATOR
# ==============================================================================
elif menu_choice == "🤖 AI Timetable Generator":
    st.markdown('<div class="main-header">AI Timetable Generator</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Constraint Satisfaction Problem Solver powered by Backtracking Search, MRV, LCV & Forward Checking</div>', unsafe_allow_html=True)

    col_config, col_action = st.columns([2, 1])

    with col_config:
        st.subheader("Solver Heuristics & Search Controls")
        c1, c2 = st.columns(2)
        with c1:
            use_mrv = st.checkbox("Minimum Remaining Values (MRV) Heuristic", value=True, help="Selects variable with fewest remaining legal domain values (fail-first principle). Ties broken by Degree Heuristic.")
            use_lcv = st.checkbox("Least Constraining Value (LCV) Heuristic", value=True, help="Orders domain values by the number of domain choices ruled out for neighbor unassigned variables.")
        with c2:
            use_fc = st.checkbox("Forward Checking (FC)", value=True, help="Prunes inconsistent values from domains of unassigned variables and terminates early upon domain wipeout.")
            timeout_sec = st.slider("Search Timeout (Seconds)", min_value=5.0, max_value=60.0, value=20.0, step=5.0)

        max_backtracks = st.number_input("Maximum Backtrack Operations Limit", min_value=1000, max_value=50000, value=15000, step=1000)

    with col_action:
        st.subheader("Run Generator")
        st.write("Click below to trigger the local CSP Backtracking engine:")
        if st.button("🚀 Execute CSP Timetable Solver", width="stretch", type="primary"):
            with st.spinner("AI Solver running Backtracking Search across variables, domains, and constraints..."):
                success, msg = solve_current_timetable(
                    use_mrv=use_mrv,
                    use_lcv=use_lcv,
                    use_fc=use_fc,
                    max_backtracks=max_backtracks,
                    timeout=timeout_sec
                )
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
                st.rerun()

    st.markdown("---")
    st.subheader("Execution Metrics & Search Trajectory")

    if st.session_state.solver_metrics:
        m = st.session_state.solver_metrics
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Variables Scheduled", f"{len(st.session_state.timetable_results)} / {m.get('sessions_to_schedule', 0)}")
        m2.metric("Execution Time", f"{m.get('execution_time_seconds', 0.0)} s")
        m3.metric("Nodes Explored", m.get("candidate_assignments_explored", 0))
        m4.metric("Backtracks", m.get("backtrack_count", 0))
        m5.metric("Constraint Checks", m.get("constraint_checks", 0))
        m6.metric("FC Domain Prunes", m.get("forward_check_prunes", 0))

        # Independent Validation Stamp
        val = st.session_state.validation_report
        if val:
            if val.is_valid:
                st.success("🛡️ **Independent Timetable Validation Pass:** PASSED with 0 hard constraint violations! Every assignment strictly adheres to faculty availability, room capacity, section independence, and break periods.")
            else:
                st.warning(f"⚠️ **Independent Timetable Validation Pass:** Found {val.summary_stats.get('error_count', 0)} errors and {val.summary_stats.get('warning_count', 0)} warnings.")
    else:
        st.info("Execute the solver above to inspect real-time search trajectory and heuristic performance metrics.")


# ==============================================================================
# SECTION G: CONFLICT DETECTION & EXPLANATION
# ==============================================================================
elif menu_choice == "🔍 Conflict Detection & Explanation":
    st.markdown('<div class="main-header">Conflict Detection & Diagnostic Engine</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Independent constraint verification pass with root-cause explanations and actionable suggestions</div>', unsafe_allow_html=True)

    val = st.session_state.validation_report
    cfg_conflicts = validate_configuration(dm.config)

    # Pre-configuration status
    if cfg_conflicts:
        st.error(f"⚠️ Found {len(cfg_conflicts)} Pre-Scheduling Configuration Error(s) in Academic Setup:")
        for i, c in enumerate(cfg_conflicts, 1):
            with st.container():
                st.markdown(f"**{i}. [{c.severity}] {c.conflict_type}**")
                st.write(f"**Description:** {c.description}")
                st.info(f"💡 **Actionable Suggestion:** {c.suggestion}")
                st.divider()

    st.subheader("Timetable Schedule Verification Results")
    if not val:
        st.info("No timetable has been validated yet. Go to **AI Timetable Generator** and run the solver.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Validation Result", "VALID" if val.is_valid else "INVALID")
        c2.metric("Scheduled Periods", f"{val.total_scheduled_periods} / {val.total_required_periods}")
        c3.metric("Critical Errors", val.summary_stats.get("error_count", 0))
        c4.metric("Warnings", val.summary_stats.get("warning_count", 0))

        if val.is_valid:
            st.success("🎉 **All 10 Hard Constraints Satisfied!** Independent validation verified zero faculty clashes, zero classroom double-bookings, zero student section conflicts, valid room types, sufficient capacities, and zero break period overlaps.")
        else:
            st.markdown("### Detected Conflicts & Resolution Advice")
            for i, c in enumerate(val.conflicts, 1):
                badge_class = "badge-danger" if c.severity == "ERROR" else "badge-warning"
                st.markdown(f"""
                <div style="border-left: 4px solid {'#EF4444' if c.severity == 'ERROR' else '#F59E0B'}; padding-left: 1rem; margin-bottom: 1.2rem;">
                    <span class="{badge_class}">[{c.severity}] {c.conflict_type}</span>
                    <p style="margin-top: 0.5rem; font-weight: 500; color: #1E293B;">{c.description}</p>
                    <p style="color: #0369A1; background-color: #F0F9FF; padding: 8px 12px; border-radius: 6px; font-size: 0.9rem;">
                        💡 <strong>Recommended Fix:</strong> {c.suggestion}
                    </p>
                </div>
                """, unsafe_allow_html=True)


# ==============================================================================
# SECTION H: TIMETABLE VIEWER
# ==============================================================================
elif menu_choice == "📅 Timetable Viewer":
    st.markdown('<div class="main-header">Weekly Timetable Grid</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Interactive weekly schedule grid with multi-dimensional filtering by section, faculty, classroom, and subject</div>', unsafe_allow_html=True)

    timetable = st.session_state.timetable_results

    if not timetable:
        st.warning("No timetable generated yet. Please navigate to 'AI Timetable Generator' and click 'Execute CSP Timetable Solver'.")
    else:
        cfg = dm.config
        working_days = cfg.get("working_days", [])
        raw_slots = cfg.get("time_slots", [])

        # Filters
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            sec_options = ["All Sections"] + [s["section_id"] for s in cfg.get("sections", [])]
            selected_section = st.selectbox("Filter by Student Section", options=sec_options)
        with f2:
            fac_options = ["All Faculty"] + [f["faculty_id"] for f in cfg.get("faculty", [])]
            fac_label_map = {f["faculty_id"]: f["name"] for f in cfg.get("faculty", [])}
            selected_faculty = st.selectbox("Filter by Faculty", options=fac_options, format_func=lambda x: fac_label_map.get(x, x))
        with f3:
            room_options = ["All Classrooms"] + [r["room_id"] for r in cfg.get("classrooms", [])]
            selected_room = st.selectbox("Filter by Room", options=room_options)
        with f4:
            view_mode = st.radio("Display Mode", ["Weekly Grid View", "Structured Table View"], horizontal=True)

        # Apply Filters
        filtered_records = []
        for rec in timetable:
            if selected_section != "All Sections" and rec["section_id"] != selected_section:
                continue
            if selected_faculty != "All Faculty" and rec["faculty_id"] != selected_faculty:
                continue
            if selected_room != "All Classrooms" and rec["room_id"] != selected_room:
                continue
            filtered_records.append(rec)

        if view_mode == "Structured Table View":
            st.subheader(f"Filtered Timetable Records ({len(filtered_records)} periods)")
            if filtered_records:
                display_cols = ["day", "slot_name", "start_time", "end_time", "subject_name", "section_id", "faculty_name", "room_name", "room_type"]
                st.dataframe(pd.DataFrame(filtered_records)[display_cols], width="stretch", hide_index=True)
            else:
                st.info("No records match the current filter selection.")
        else:
            # Weekly Grid Matrix View
            st.subheader("Weekly Schedule Matrix")

            # Fast lookup map: (day, slot_id) -> list of matching records
            grid_lookup: Dict[tuple, List[Dict[str, Any]]] = {}
            for rec in filtered_records:
                key = (rec["day"], rec["slot_id"])
                if key not in grid_lookup:
                    grid_lookup[key] = []
                grid_lookup[key].append(rec)

            # Build Header Row
            cols = st.columns([1.5] + [2.2 for _ in working_days])
            cols[0].markdown("**Time Slot**")
            for idx, d in enumerate(working_days):
                cols[idx + 1].markdown(f"**{d}**")

            st.divider()

            # Render rows for each slot
            for slot in raw_slots:
                slot_id = slot["slot_id"]
                slot_name = slot["name"]
                slot_time = f"{slot['start_time']} - {slot['end_time']}"
                is_break = slot.get("is_break", False)

                row_cols = st.columns([1.5] + [2.2 for _ in working_days])
                row_cols[0].markdown(f"**{slot_name}**<br><span style='color: #64748B; font-size: 0.8rem;'>{slot_time}</span>", unsafe_allow_html=True)

                if is_break:
                    for idx, day in enumerate(working_days):
                        row_cols[idx + 1].markdown(f"""
                        <div class="timetable-break">
                            ☕ {slot_name}
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    for idx, day in enumerate(working_days):
                        cell_items = grid_lookup.get((day, slot_id), [])
                        if not cell_items:
                            row_cols[idx + 1].markdown("""
                            <div class="timetable-empty">
                                <em>Vacant Slot</em>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            content_html = ""
                            for item in cell_items:
                                is_lab = item.get("room_type") == "Laboratory"
                                badge = "badge-lab" if is_lab else "badge-theory"
                                consec_str = f" (Part {item.get('is_consecutive_part')}/{item.get('duration_periods')})" if item.get("duration_periods", 1) > 1 else ""
                                content_html += f"""
                                <div class="timetable-cell">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                        <strong>{item['subject_id']}</strong>
                                        <span class="{badge}">{item['room_type']}</span>
                                    </div>
                                    <div style="font-weight: 600; color: #1E293B;">{item['subject_name']}{consec_str}</div>
                                    <div style="color: #475569; font-size: 0.78rem;">👨‍🏫 {item['faculty_name']}</div>
                                    <div style="color: #0284C7; font-size: 0.78rem;">🏫 {item['room_name']} | 👥 {item['section_id']}</div>
                                </div>
                                """
                            row_cols[idx + 1].markdown(content_html, unsafe_allow_html=True)

                st.write("")


# ==============================================================================
# SECTION I: PERFORMANCE AND ALGORITHM ANALYSIS
# ==============================================================================
elif menu_choice == "📈 Performance & Algorithm Analysis":
    st.markdown('<div class="main-header">CSP Algorithm Performance & Benchmark Analysis</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Empirical comparison between Basic Backtracking, Forward Checking, and Full AI Heuristics (MRV + LCV + FC)</div>', unsafe_allow_html=True)

    st.markdown("""
    To demonstrate genuine Constraint Satisfaction Problem solving for an AI course, this benchmark executes three solver configurations
    on the **exact same institutional dataset**:
    1. **Basic Backtracking:** Standard depth-first search without variable or value heuristics.
    2. **Backtracking + Forward Checking (FC):** Prunes conflicting future domain values after each assignment; detects domain wipeouts early.
    3. **Full AI Solver (MRV + LCV + FC):** Minimum Remaining Values for fail-first variable selection, Least Constraining Value for value ordering, and Forward Checking.
    """)

    if st.button("🚀 Run Comparative Benchmark on Current Dataset", type="primary"):
        with st.spinner("Executing empirical benchmark across all 3 search configurations..."):
            b_results = run_benchmark_comparison(dm.config)
            st.session_state.benchmark_results = b_results
            st.success("Benchmark completed successfully!")

    if st.session_state.benchmark_results:
        b = st.session_state.benchmark_results

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("### 1. Basic Backtracking")
            st.write("Depth-first search with static variable order and no forward pruning.")
            st.dataframe(pd.DataFrame(list(b["basic"].items()), columns=["Metric", "Value"]), hide_index=True)

        with col2:
            st.markdown("### 2. Backtracking + FC")
            st.write("Forward checking added to prune domain conflicts immediately.")
            st.dataframe(pd.DataFrame(list(b["forward_checking"].items()), columns=["Metric", "Value"]), hide_index=True)

        with col3:
            st.markdown("### 3. Full AI (MRV + LCV + FC)")
            st.write("MRV fail-first variable ordering + LCV value ordering + Forward Checking.")
            st.dataframe(pd.DataFrame(list(b["full_ai"].items()), columns=["Metric", "Value"]), hide_index=True)

        st.markdown("---")
        st.subheader("Performance Comparison Table")

        comparison_summary = [
            {
                "Algorithm Configuration": "Basic Backtracking",
                "Candidates Explored": b["basic"]["candidate_assignments_explored"],
                "Constraint Checks": b["basic"]["constraint_checks"],
                "Backtracks": b["basic"]["backtrack_count"],
                "Rejected Choices": b["basic"]["rejected_assignments"],
                "Execution Time (s)": b["basic"]["execution_time_seconds"],
                "Solved?": "✅ Yes" if b["basic"]["solution_found"] else "❌ No"
            },
            {
                "Algorithm Configuration": "Backtracking + Forward Checking",
                "Candidates Explored": b["forward_checking"]["candidate_assignments_explored"],
                "Constraint Checks": b["forward_checking"]["constraint_checks"],
                "Backtracks": b["forward_checking"]["backtrack_count"],
                "Rejected Choices": b["forward_checking"]["rejected_assignments"],
                "Execution Time (s)": b["forward_checking"]["execution_time_seconds"],
                "Solved?": "✅ Yes" if b["forward_checking"]["solution_found"] else "❌ No"
            },
            {
                "Algorithm Configuration": "Full AI (MRV + LCV + Forward Checking)",
                "Candidates Explored": b["full_ai"]["candidate_assignments_explored"],
                "Constraint Checks": b["full_ai"]["constraint_checks"],
                "Backtracks": b["full_ai"]["backtrack_count"],
                "Rejected Choices": b["full_ai"]["rejected_assignments"],
                "Execution Time (s)": b["full_ai"]["execution_time_seconds"],
                "Solved?": "✅ Yes" if b["full_ai"]["solution_found"] else "❌ No"
            }
        ]
        st.dataframe(pd.DataFrame(comparison_summary), width="stretch", hide_index=True)

        st.info("""
        **Viva Explanation Insight:** Notice how Forward Checking drastically slashes the number of candidate assignments explored and constraint checks by pruning domain options upfront before recursion. MRV ensures the solver addresses the tightest constraints (such as laboratory classes with limited rooms and multi-hour blocks) first!
        """)


# ==============================================================================
# SECTION J: EXPORT AND RESET
# ==============================================================================
elif menu_choice == "💾 Export & Reset":
    st.markdown('<div class="main-header">Export & Configuration Reset</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Export generated timetable to CSV, generate validation audit logs, or restore demonstration datasets</div>', unsafe_allow_html=True)

    col_exp, col_rst = st.columns(2)

    with col_exp:
        st.subheader("📥 Export Timetable & Audit Report")
        csv_data = dm.export_timetable_csv()
        if csv_data:
            st.download_button(
                label="📄 Download Timetable as CSV",
                data=csv_data,
                file_name="northstar_academic_timetable.csv",
                mime="text/csv",
                width="stretch"
            )
        else:
            st.warning("No active timetable available for export. Generate one first.")

        audit_markdown = dm.generate_audit_summary_markdown()
        st.download_button(
            label="📑 Download Full Audit & Validation Report (.md)",
            data=audit_markdown,
            file_name="timetable_validation_report.md",
            mime="text/markdown",
            width="stretch"
        )

    with col_rst:
        st.subheader("🔄 Reset & Demonstration Datasets")
        st.write("Quickly reload baseline data or demonstrate failure handling:")

        if st.button("Restore Default Northstar Institute Dataset", width="stretch"):
            dm.reset_to_default()
            st.session_state.timetable_results = []
            st.session_state.validation_report = None
            st.session_state.solver_metrics = None
            st.session_state.benchmark_results = None
            st.success("Configuration reset to fictional Northstar Institute of Technology dataset.")
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("⚠️ Load Infeasible Test Case (Demonstrate Failure Handling)", width="stretch"):
            dm.load_infeasible_scenario()
            st.session_state.timetable_results = []
            st.session_state.validation_report = None
            st.session_state.solver_metrics = None
            st.session_state.benchmark_results = None
            st.warning("Loaded intentionally infeasible test case: 0 available laboratories, section overloaded to 35 periods vs 30 available slots, and faculty weekly overload.")
            st.rerun()


# ==============================================================================
# SECTION K: ACADEMIC VIVA & ALGORITHM DOCS
# ==============================================================================
elif menu_choice == "📖 Academic Viva & Algorithm Docs":
    st.markdown('<div class="main-header">Academic Deliverable & Viva Preparation Guide</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Theoretical foundation, CSP mathematical model, pseudocode, and viva examination questions</div>', unsafe_allow_html=True)

    viva_tab1, viva_tab2, viva_tab3 = st.tabs(["📐 CSP Formulation & Pseudocode", "❓ Top 10 Viva Questions & Answers", "🏗️ System Architecture"])

    with viva_tab1:
        st.markdown("""
        ### 1. CSP Mathematical Formulation
        An academic timetable problem is formulated as a Constraint Satisfaction Problem:
        $$\\mathcal{P} = \\langle X, D, C \\rangle$$

        - **Variables ($X$):**
          Each required weekly session $j$ of subject $i$ is an individual variable $V_{i,j}$.
          $$X = \\{ V_{i,j} \\mid 1 \\le i \\le |\\text{Subjects}|, 1 \\le j \\le \\text{Sessions}(i) \\}$$

        - **Domains ($D$):**
          Each variable $V$ has domain $D(V) \\subseteq \\text{Days} \\times \\text{TeachingSlots} \\times \\text{Rooms}$.
          A value $v = (d, s, r)$ is in $D(V)$ if and only if:
          1. $\\text{RoomType}(r) = \\text{RoomType}(V)$
          2. $\\text{Capacity}(r) \\ge \\text{ExpectedStudents}(V)$
          3. $r$ is active/available
          4. Faculty $\\text{Fac}(V)$ is available on day $d$ and slot $s$
          5. For multi-period sessions ($k > 1$), consecutive slots $[s, s+k-1]$ do not cross breaks.

        - **Hard Constraints ($C$):**
          1. **Faculty Conflict:** $\\forall V_a, V_b$ where $\\text{Fac}(V_a) = \\text{Fac}(V_b)$ and $a \\neq b$, assigned slots must not overlap.
          2. **Classroom Conflict:** $\\forall V_a, V_b$ where $\\text{Room}(V_a) = \\text{Room}(V_b)$ and $a \\neq b$, assigned slots must not overlap.
          3. **Section Conflict:** $\\forall V_a, V_b$ where $\\text{Sec}(V_a) = \\text{Sec}(V_b)$ and $a \\neq b$, assigned slots must not overlap.
          4. **Faculty Workload:** Daily sessions $\\le \\text{MaxDaily}$ and weekly sessions $\\le \\text{MaxWeekly}$.
          5. **Break Constraint:** Zero classes scheduled during designated break periods.

        ### 2. Backtracking Search Algorithm Pseudocode
        ```python
        def BACKTRACKING_SEARCH(csp):
            return BACKTRACK({}, csp)

        def BACKTRACK(assignment, csp):
            if len(assignment) == len(csp.variables):
                return assignment
            
            # Select unassigned variable using MRV with Degree heuristic tie-breaker
            var = SELECT_UNASSIGNED_VARIABLE(csp, assignment)
            
            # Order values using Least Constraining Value (LCV)
            for value in ORDER_DOMAIN_VALUES(var, assignment, csp):
                if IS_CONSISTENT(var, value, assignment, csp):
                    assignment[var] = value
                    
                    # Forward Checking: prune incompatible values from unassigned variables
                    success, pruned = FORWARD_CHECK(var, value, assignment, csp)
                    if success:
                        result = BACKTRACK(assignment, csp)
                        if result is not None:
                            return result
                    
                    # Backtrack: restore pruned domains and remove assignment
                    RESTORE_DOMAINS(pruned, csp)
                    del assignment[var]
            
            return None  # Trigger backtracking to parent node
        ```
        """)

    with viva_tab2:
        st.markdown("""
        ### Comprehensive Viva Examination Q&A

        **Q1: Why is academic timetabling modeled as a CSP instead of using pure machine learning?**
        > *Answer:* Academic scheduling requires strict satisfaction of hard mathematical constraints (no teacher in two places at once, no room double-booked). Machine learning algorithms (neural networks) are probabilistic and often violate hard constraints. CSP guarantees 100% adherence to all hard constraints and provides verifiable, explainable conflict detection.

        **Q2: What is the Minimum Remaining Values (MRV) heuristic?**
        > *Answer:* MRV, also known as the "Most Constrained Variable" or "Fail-First" heuristic, selects the variable with the smallest number of legal remaining values in its domain. By assigning the most difficult variable first, MRV detects failure early before deep recursion.

        **Q3: How does the Degree Heuristic complement MRV?**
        > *Answer:* When multiple variables have the same minimum domain size, the Degree Heuristic breaks ties by selecting the variable involved in the largest number of constraints with other *unassigned* variables, reducing the branching factor of future choices.

        **Q4: What is the Least Constraining Value (LCV) heuristic?**
        > *Answer:* LCV is a value-ordering heuristic that prefers the value that rules out the fewest choices for neighboring unassigned variables in the constraint graph ("Fail-Last" for values), leaving maximum flexibility for future assignments.

        **Q5: What is Forward Checking and how does it prevent thrashing?**
        > *Answer:* Whenever a variable $X$ is assigned value $v$, Forward Checking looks ahead to all unassigned variables $Y$ connected to $X$ by constraints and removes values from $Y$'s domain that are inconsistent with $v$. If any variable's domain becomes empty (domain wipeout), the algorithm immediately backtracks without exploring a futile subtree.

        **Q6: What happens if an impossible configuration is provided (e.g. 35 periods requested in a 30-period week)?**
        > *Answer:* Our system uses a two-tier approach: first, a pre-scheduling analytical validator detects mathematical infeasibilities (such as Pigeonhole principle violations and room shortages) before search. Second, if search is attempted, the CSP solver terminates safely at the domain initialization stage or backtrack bound and provides clear diagnostic reasons.

        **Q7: How are laboratory classes handled differently from theory lectures?**
        > *Answer:* Laboratory classes have two distinct requirements: (1) Room type restriction (must be assigned to a `Laboratory` room with required capacity), and (2) Multi-period block allocation (e.g. 2 consecutive hours) that cannot cross break periods.

        **Q8: What is independent timetable validation?**
        > *Answer:* Rather than assuming the solver output is valid, the system passes the generated timetable through an independent, decoupled validator (`constraints.py`) that audits every assignment against all 10 hard constraints.

        **Q9: What is the time complexity of the Backtracking Search algorithm?**
        > *Answer:* The worst-case time complexity of CSP backtracking is $O(d^n)$, where $n$ is the number of variables (sessions) and $d$ is the maximum domain size. Heuristics like MRV, LCV, and Forward Checking drastically prune the practical search space to polynomial-like efficiency on typical college instances.

        **Q10: What are future enhancements for SmartSlot AI?**
        > *Answer:* Incorporating soft constraints (faculty preferred time slots, minimizing student gap hours) via Optimization / Arc-Consistency (AC-3 / AC-4) and Genetic Algorithms for multi-objective optimization.
        """)

    with viva_tab3:
        st.markdown("""
        ### Modular System Architecture
        ```
        +------------------------------------------------------------------+
        |                  SmartSlot AI - Web Dashboard (app.py)           |
        |   - Streamlit Multi-Page UI     - Weekly Grid Visualization      |
        |   - Heuristic Benchmark Panel   - Interactive Form Editors       |
        +---------------------------------+--------------------------------+
                                          |
                        +-----------------+-----------------+
                        |                                   |
                        v                                   v
        +-------------------------------+   +-------------------------------+
        |  Data Manager                 |   |  AI Scheduling Engine         |
        |  (data_manager.py)            |   |  (scheduler.py)               |
        |  - JSON Persistence           |   |  - CSP Formulation           |
        |  - Input CRUD & Validation    |   |  - Backtracking Search        |
        |  - CSV & Report Export        |   |  - MRV & Degree Heuristics    |
        +---------------+---------------+   |  - LCV Value Ordering         |
                        |                   |  - Forward Checking (FC)      |
                        |                   +---------------+---------------+
                        v                                   |
        +-------------------------------+                   |
        |  Independent Constraint       |<------------------+
        |  Validation Engine            |
        |  (constraints.py)             |
        |  - 10 Hard Constraints Audit  |
        |  - Conflict Root-Cause Advice |
        +-------------------------------+
        ```
        """)
