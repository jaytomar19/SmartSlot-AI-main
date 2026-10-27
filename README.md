# SmartSlot AI: Intelligent Academic Timetable Generator
### Using Constraint Satisfaction Problems (CSP) and Backtracking Search

SmartSlot AI is an end-to-end, locally runnable academic timetable scheduling platform designed for an **Artificial Intelligence Course (AISC)**. The system formulates university scheduling as a formal **Constraint Satisfaction Problem (CSP)** and solves it using **Backtracking Search** enhanced with **Minimum Remaining Values (MRV)**, **Least Constraining Value (LCV)**, and **Forward Checking (FC)**.

The project demonstrates full software engineering and AI principles: genuine scheduling algorithms, independent 10-constraint auditing, conflict detection with root-cause explanations, weekly matrix visualization, empirical performance benchmarking, and CSV/Markdown export.

---

## 🏛️ Fictional Institution Dataset
The application is pre-configured with a complete demonstration dataset for the fictional institution:
- **Institution:** Northstar Institute of Technology (NIT)
- **Department:** Department of Computer Science & Engineering
- **Term:** Fall Semester 2026-27
- **Working Days:** Monday through Friday (5 days)
- **Daily Slots:** 6 Teaching Periods + 1 Designated Lunch Break
- **Classrooms:** 5 spaces (Lecture Hall A, Lecture Hall B, Seminar Hall, AI & Data Science Lab, Systems & Networks Lab)
- **Faculty:** 6 Fictional Faculty Members (Prof. Alan Turing, Dr. Grace Hopper, Prof. Ada Lovelace, Dr. John von Neumann, Dr. Claude Shannon, Prof. Barbara Liskov)
- **Student Sections:** CSE 3rd Year Section A (CS-A), CSE 3rd Year Section B (CS-B)
- **Subjects:** 8 courses covering both Theory and Multi-Period Laboratory blocks (22 weekly periods total)

---

## 🚀 Deploying to Vercel

The production app is a static single-page UI (`public/`) backed by a stateless FastAPI serverless function (`api/index.py`) that wraps the CSP engine.

1. Push this repository to GitHub.
2. In Vercel, click **Add New → Project**, import the repo, and keep the defaults (Framework Preset: **Other**). `vercel.json` already configures everything.
3. Click **Deploy**.

Or deploy from the CLI:
```bash
npm i -g vercel
vercel          # preview deployment
vercel --prod   # production deployment
```

**How state works on Vercel:** serverless functions have no persistent disk, so the browser stores the academic configuration, timetable, and reports in `localStorage` and sends the config with each API request. Use **Export & Reset → Download Academic Configuration** to back up or move a configuration between browsers.

API docs are served at `/api/docs` on any deployment.

---

## ⚡ Local Development

### 1. Prerequisites
- Python 3.10 – 3.12 (Vercel runs Python 3.12).

### 2. Setup Virtual Environment & Install Dependencies
```bash
python3 -m venv .venv

# On macOS / Linux:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate

pip install -r requirements-dev.txt
```

### 3. Run Automated Tests
```bash
pytest -v tests/
```

### 4. Launch the Web Application
```bash
python dev_server.py
```
Open `http://localhost:8000`. This serves the same UI and API as the Vercel deployment. (`vercel dev` also works.)

---

## 🧠 Core AI Concepts Implemented

### 1. Constraint Satisfaction Problem (CSP) Formulation
$$\mathcal{P} = \langle X, D, C \rangle$$
- **Variables ($X$):** Individual weekly class sessions for each subject. Multi-period labs represent contiguous session blocks.
- **Domains ($D$):** Triples of `(Day, TimeSlotIndex, RoomID)` filtered upfront by unary constraints (faculty availability, room type, and seating capacity).
- **Constraints ($C$):** 10 hard operational constraints:
  1. No faculty member assigned to multiple classes simultaneously.
  2. No classroom booked for multiple classes simultaneously.
  3. No student section assigned to multiple classes simultaneously.
  4. Class assigned to qualified and available faculty.
  5. Room type matching (e.g. Laboratory courses require Laboratory facilities).
  6. Classroom seating capacity $\ge$ expected student count.
  7. Multi-period sessions fit entirely within teaching hours.
  8. Faculty availability schedules respected.
  9. Classes never overlap with configured break intervals (e.g. Lunch).
  10. All required curriculum hours scheduled.

### 2. Search Algorithms and Heuristics
- **Backtracking Search:** Recursive depth-first search that backtracks upon constraint violation.
- **Minimum Remaining Values (MRV):** "Fail-First" heuristic selecting the unassigned variable with the fewest remaining domain values.
- **Degree Heuristic:** Breaks MRV ties by selecting the variable with the largest number of constraints with remaining unassigned variables.
- **Least Constraining Value (LCV):** "Fail-Last" heuristic ordering candidate domain values to maximize flexibility for neighbor variables.
- **Forward Checking (FC):** Prunes conflicting domain values from unassigned variables after each assignment; immediately backtracks upon detecting domain wipeouts.

---

## 📁 Project Architecture

```
SmartSlot-AI/
├── api/
│   └── index.py                # Vercel serverless FastAPI app (stateless JSON API)
├── public/
│   ├── index.html              # Single-page web UI (served by Vercel CDN)
│   ├── app.js                  # UI views, localStorage state, API client
│   └── styles.css              # UI styling
├── smartslot/                  # Core AI engine (Python package)
│   ├── scheduler.py            # CSP formulation, Backtracking, MRV, LCV, FC engine
│   ├── constraints.py          # 10 Hard constraints audit & conflict diagnostics
│   ├── data_manager.py         # Configuration CRUD, optional JSON persistence, CSV exports
│   └── sample_data.py          # Northstar Institute of Technology dataset + infeasible test case
├── docs/
│   └── ACADEMIC_REPORT.md      # Comprehensive AI viva documentation & report
├── tests/
│   ├── test_api.py            # Tests for the serverless API
│   ├── test_constraints.py    # Unit tests for conflict detection and validation
│   └── test_scheduler.py      # Unit tests for CSP solver and timetable generation
├── dev_server.py               # Local server mirroring the Vercel deployment
├── vercel.json                 # Vercel routing & function configuration
├── .vercelignore               # Files excluded from the Vercel upload
├── .python-version             # Python version for Vercel (3.12)
├── requirements.txt            # Production dependencies (fastapi, pandas)
├── requirements-dev.txt        # Dev dependencies (pytest, uvicorn, httpx)
├── pytest.ini                  # Pytest configuration
└── README.md                   # Project overview and instructions
```

---

## 🖥️ Application Features Walkthrough

1. **📊 Dashboard:**
   - Real-time KPIs: Subjects, Faculty, Classrooms, Required Periods, Slot Capacity.
   - Generation health status with one-click "🚀 Generate Timetable" action.
   - Formal mathematical CSP overview.

2. **⚙️ Academic Configuration:**
   - Configure institution name, term, and department.
   - Manage working days (Monday–Saturday).
   - Configure daily periods, start/end times, and designated break intervals.

3. **👨‍🏫 Faculty Management:**
   - View faculty records, max daily limits, and max weekly load.
   - Interactive Add/Edit/Delete forms with input validation.
   - Slot-level unavailability restrictions (e.g., mark specific faculty unavailable on Friday afternoons).

4. **📚 Subject & Course Management:**
   - Theory courses vs Multi-period Laboratory sessions.
   - Faculty mapping, section assignment, student count, and consecutive period flags.

5. **🏫 Classroom Management:**
   - Classrooms vs Laboratories vs Seminar Halls.
   - Seating capacity and active/operational status toggles.

6. **🤖 AI Timetable Generator:**
   - Configurable heuristics: Toggle MRV, LCV, Forward Checking, and search limits.
   - Live solver execution with metrics: nodes explored, backtracks, constraint checks, and runtime.
   - Search trajectory trace log for viva demonstration.

7. **🔍 Conflict Detection & Explanation:**
   - Pre-scheduling analytical validation (catches Pigeonhole violations and resource shortages).
   - Independent 10-constraint audit pass.
   - Root-cause diagnostics with actionable administrator resolution suggestions.

8. **📅 Timetable Viewer:**
   - Interactive weekly matrix grid (Days as columns, Time Slots as rows).
   - Distinct tags for Theory vs Lab courses.
   - Break period indicators and empty slot visibility.
   - Filters by Student Section, Faculty, Classroom, or Subject.

9. **📈 Performance & Algorithm Analysis:**
   - Empirical comparative benchmark on the active dataset:
     1. Basic Backtracking
     2. Backtracking + Forward Checking
     3. Full AI (MRV + LCV + Forward Checking)
   - Visual comparison table showing candidates explored, backtracks, and constraint checks.

10. **💾 Export & Reset:**
    - Download generated timetable as clean CSV.
    - Download comprehensive Audit & Validation Report as Markdown.
    - Quick actions to restore the Northstar Institute dataset or load an intentionally infeasible scenario.

---

## 🧪 Testing and Verification

All 22 automated tests (14 engine tests below + 8 API tests in `tests/test_api.py`) can be executed with:
```bash
pytest -v tests/
```

### Verified Test Cases:
1. `test_default_config_is_valid`: Feasible baseline passes configuration validation.
2. `test_infeasible_config_detection`: Pre-check catches laboratory shortages and section overloads.
3. `test_faculty_clash_detection`: Rejects simultaneous faculty double-booking.
4. `test_room_clash_detection`: Rejects classroom double-booking.
5. `test_section_clash_detection`: Rejects student section clashes.
6. `test_faculty_unavailability_detection`: Unavailable faculty slots are never assigned.
7. `test_room_type_mismatch_detection`: Laboratory courses rejected in lecture rooms.
8. `test_room_capacity_violation_detection`: Classes exceeding room capacity rejected.
9. `test_break_overlap_detection`: Classes overlapping lunch breaks rejected.
10. `test_solver_generates_valid_timetable`: Generates complete, valid timetable for default dataset.
11. `test_solver_with_heuristics_combinations`: Verifies MRV, LCV, and FC combinations.
12. `test_solver_handles_infeasible_config`: Safe termination when no solution exists.
13. `test_csv_export_contains_assignments`: Real CSV export contains all fields and rows.
14. `test_benchmark_comparison_structure`: Empirical benchmark executes and compares configurations.

---

## 🎓 Academic Viva Highlights

- **NP-Completeness:** Timetabling is NP-complete; exhaustive enumeration is $O(d^n)$.
- **MRV (Fail-First):** Choosing the variable with the smallest remaining domain detects dead ends at shallow depths.
- **LCV (Fail-Last):** Choosing the value that leaves the most options for neighbors avoids unnecessary backtracks.
- **Forward Checking:** Proactively reduces neighbor domains after every assignment, terminating immediately if a domain becomes empty.
- **Independent Validation:** Separates the search engine from the verification logic to guarantee 100% clash-free schedules.
