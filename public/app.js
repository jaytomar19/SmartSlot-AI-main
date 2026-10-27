/*
 * SmartSlot AI - Browser client.
 *
 * The serverless API is stateless, so the browser owns the academic
 * configuration, generated timetable, validation report and solver metrics
 * (persisted in localStorage) and sends the config with each API call.
 */

const STORAGE_KEY = "smartslot_state_v1";
const ALL_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const ROOM_TYPES = ["Classroom", "Laboratory", "Seminar Hall"];

const VIEWS = [
  ["dashboard", "Dashboard"],
  ["config", "Academic Configuration"],
  ["faculty", "Faculty Management"],
  ["subjects", "Subject & Course Management"],
  ["classrooms", "Classroom Management"],
  ["generator", "AI Timetable Generator"],
  ["conflicts", "Conflict Detection & Explanation"],
  ["viewer", "Timetable Viewer"],
  ["benchmark", "Performance & Algorithm Analysis"],
  ["export", "Export & Reset"],
  ["docs", "Academic Viva & Algorithm Docs"],
];

// Sidebar toggle groups (presentation only).
const NAV_GROUPS = [
  ["overview", ["dashboard"]],
  ["school info", ["config", "faculty", "subjects", "classrooms"]],
  ["ai planner", ["generator", "conflicts", "viewer", "benchmark"]],
  ["resources", ["export", "docs"]],
];

let state = { config: null, timetable: [], validation: null, metrics: null, benchmark: null };
// Per-view UI selections that should survive re-renders but not reloads.
const ui = { tabs: {}, viewer: { section: "", faculty: "", room: "", mode: "grid" }, editFac: "", editFacDay: "", editSub: "", editRoom: "" };

// --- Utilities ---
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function saveState() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (_) { /* storage unavailable */ }
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (_) { /* storage unavailable or corrupt */ }
  return null;
}

function clearResults() {
  state.timetable = [];
  state.validation = null;
  state.metrics = null;
  state.benchmark = null;
}

let toastTimer;
function toast(msg, ok = true) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("toast-error", !ok);
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3500);
}

function busy(text) {
  $("#busy-text").textContent = text || "";
  $("#busy").hidden = !text;
}

async function api(path, body, { text = false } = {}) {
  const res = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) { /* non-JSON error */ }
    throw new Error(`${res.status}: ${detail}`);
  }
  return text ? res.text() : res.json();
}

async function mutate(action, payload) {
  try {
    const r = await api("/api/config/mutate", { config: state.config, action, payload });
    if (r.ok) {
      state.config = r.config;
      saveState();
      render();
    }
    toast(r.message, r.ok);
    return r.ok;
  } catch (e) {
    toast(e.message, false);
    return false;
  }
}

function download(filename, content, mime) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

const requiredPeriods = (cfg) => cfg.subjects.reduce((n, s) => n + (s.sessions_per_week || 1) * (s.duration_periods || 1), 0);
const teachingSlots = (cfg) => cfg.time_slots.filter((s) => !s.is_break);

// --- HTML builders ---
function table(rows, cols) {
  if (!rows.length) return `<div class="alert alert-info">No records.</div>`;
  cols = cols || Object.keys(rows[0]);
  const head = cols.map((c) => `<th>${esc(c)}</th>`).join("");
  const body = rows.map((r) => `<tr>${cols.map((c) => `<td>${esc(typeof r[c] === "object" && r[c] !== null ? JSON.stringify(r[c]) : r[c])}</td>`).join("")}</tr>`).join("");
  return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

const header = (title, sub) => `<div class="main-header">${esc(title)}</div><div class="sub-header">${esc(sub)}</div>`;
const alertBox = (kind, html) => `<div class="alert alert-${kind}">${html}</div>`;
const metricCard = (value, label) => `<div class="metric-card"><div class="metric-value">${esc(value)}</div><div class="metric-label">${esc(label)}</div></div>`;
const metric = (label, value) => `<div class="metric"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div></div>`;

const text = (name, label, value = "", attrs = "") => `<label>${esc(label)}<input type="text" name="${name}" value="${esc(value)}" ${attrs}></label>`;
const num = (name, label, value, min, max, step = 1) => `<label>${esc(label)}<input type="number" name="${name}" value="${esc(value)}" min="${min}" max="${max}" step="${step}" required></label>`;
const check = (name, label, checked) => `<label class="check"><input type="checkbox" name="${name}" ${checked ? "checked" : ""}> ${esc(label)}</label>`;
function select(name, label, options, value, attrs = "") {
  const opts = options.map(([v, t]) => `<option value="${esc(v)}" ${v === value ? "selected" : ""}>${esc(t)}</option>`).join("");
  return `<label>${esc(label)}<select name="${name}" ${attrs}>${opts}</select></label>`;
}
const pairs = (arr) => arr.map((v) => [v, v]);
function multiCheck(name, label, options, selected) {
  const boxes = options.map((o) => `<label class="check"><input type="checkbox" name="${name}" value="${esc(o)}" ${selected.includes(o) ? "checked" : ""}> ${esc(o)}</label>`).join("");
  return `<div class="field-group-title">${esc(label)}</div><div class="checks">${boxes}</div>`;
}

function tabs(id, items) {
  const active = ui.tabs[id] ?? 0;
  const btns = items.map(([t], i) => `<button type="button" class="tab ${i === active ? "active" : ""}" data-tabs="${id}" data-tab="${i}">${esc(t)}</button>`).join("");
  const panels = items.map(([, html], i) => `<div class="tab-panel" ${i === active ? "" : "hidden"}>${html}</div>`).join("");
  return `<div class="tabs">${btns}</div>${panels}`;
}

function formData(form) {
  const fd = new FormData(form);
  const get = (k) => (fd.get(k) ?? "").toString();
  return {
    str: get,
    int: (k) => parseInt(get(k), 10),
    float: (k) => parseFloat(get(k)),
    bool: (k) => form.elements[k]?.checked ?? false,
    all: (k) => fd.getAll(k).map(String),
  };
}

function conflictCard(c) {
  const isErr = c.severity === "ERROR";
  return `<div class="conflict ${isErr ? "" : "warn"}">
    <span class="badge ${isErr ? "badge-danger" : "badge-warning"}">[${esc(c.severity)}] ${esc(c.conflict_type)}</span>
    <p>${esc(c.description)}</p>
    <p class="fix"><strong>Recommended Fix:</strong> ${esc(c.suggestion)}</p>
  </div>`;
}

// --- Solver actions ---
async function runSolver(options = {}) {
  busy("AI Solver running Backtracking Search with MRV, LCV & Forward Checking…");
  try {
    const r = await api("/api/solve", { config: state.config, options });
    state.timetable = r.timetable;
    state.validation = r.validation;
    state.metrics = r.metrics;
    saveState();
    toast(r.message, r.success);
  } catch (e) {
    toast(e.message, false);
  } finally {
    busy();
    render();
  }
}

// ==============================================================================
// Views
// ==============================================================================
const views = {};

views.dashboard = () => {
  const cfg = state.config;
  const totalReq = requiredPeriods(cfg);
  const capacity = cfg.working_days.length * teachingSlots(cfg).length * cfg.classrooms.length;
  const scheduled = state.timetable.length;
  const val = state.validation;

  let status;
  if (scheduled === 0) status = alertBox("info", "<strong>Status: Pending Generation.</strong> No timetable has been generated for the active academic term.");
  else if (val && val.is_valid) status = alertBox("success", `<strong>Status: Valid &amp; Conflict-Free.</strong> Successfully scheduled ${scheduled} / ${totalReq} periods across ${cfg.working_days.length} working days with 0 hard constraint violations.`);
  else status = alertBox("error", `<strong>Status: Conflicts Detected.</strong> Schedule contains ${val ? val.conflicts.length : 0} issues or unscheduled sessions requiring administrator resolution.`);

  const health = [
    { Metric: "Scheduled Periods", Value: `${scheduled} / ${totalReq}` },
    { Metric: "Unscheduled Periods", Value: Math.max(0, totalReq - scheduled) },
    { Metric: "Active Conflicts", Value: val ? val.conflicts.length : 0 },
    { Metric: "Solver Execution", Value: state.metrics ? `${state.metrics.execution_time_seconds} s` : "N/A" },
  ];

  return `${header("SmartSlot AI: Academic Dashboard", "Constraint Satisfaction Problem (CSP) Timetable Management System")}
    <div class="row cols-5">
      ${metricCard(cfg.subjects.length, "Subjects")}${metricCard(cfg.faculty.length, "Faculty")}
      ${metricCard(cfg.classrooms.length, "Classrooms")}${metricCard(totalReq, "Required Periods")}${metricCard(capacity, "Slot Capacity")}
    </div>
    <div class="row cols-2-1" style="margin-top:1.5rem">
      <div>
        <h2>Timetable Generation Status</h2>
        ${status}
        <div class="btn-row">
          <button class="btn btn-primary" data-action="solve-default">Generate Conflict-Free Timetable (AI CSP)</button>
          <button class="btn" data-nav="conflicts">View Conflict Report</button>
        </div>
      </div>
      <div><h2>Scheduling Health</h2>${table(health)}</div>
    </div>
    <h2>Assignments</h2>
    <div class="todo">
      <div class="todo-sticker" aria-hidden="true">To do list</div>
      <div class="todo-list">
        <div class="todo-title">today's task</div>
        ${[
          ["Review academic configuration", cfg.subjects.length > 0],
          ["Generate the weekly timetable", scheduled > 0],
          ["Pass independent validation", !!(val && val.is_valid)],
          ["Run the algorithm benchmark", !!state.benchmark],
        ].map(([t, done]) => `<label class="todo-item ${done ? "done" : ""}"><input type="checkbox" disabled ${done ? "checked" : ""}> ${t}</label>`).join("")}
      </div>
    </div>
    <hr>
    <h2>Constraint Satisfaction Problem (CSP) Overview</h2>
    <p>Academic timetabling is an <strong>NP-complete</strong> combinatorial optimization problem modeled formally as a Constraint Satisfaction Problem <strong>𝒫 = ⟨X, D, C⟩</strong>:</p>
    <ul>
      <li><strong>Variables (X):</strong> Individual weekly class sessions required for each academic subject.</li>
      <li><strong>Domains (D):</strong> Feasible triples of <code>(Day, Time Slot, Classroom)</code> pruned by unary constraints (faculty availability, room type compatibility, and capacity).</li>
      <li><strong>Hard Constraints (C):</strong> Zero-overlap guarantees for faculty members, student sections, classrooms, and breaks, plus daily and weekly workload caps.</li>
      <li><strong>Search Engine:</strong> Intelligent Backtracking Search augmented by <strong>Minimum Remaining Values (MRV)</strong> variable ordering, <strong>Least Constraining Value (LCV)</strong> value ordering, and <strong>Forward Checking (FC)</strong> for early dead-end detection.</li>
    </ul>`;
};

views.config = () => {
  const cfg = state.config;
  return `${header("Academic Configuration", "Configure institutional working days, daily period slots, and break periods")}
    <h2>Institution &amp; Term Details</h2>
    <form data-form="institution">
      <div class="row cols-2">
        <div>${text("institution_name", "Institution Name", cfg.institution_name)}${text("department", "Department", cfg.department)}</div>
        <div>${text("academic_term", "Academic Term", cfg.academic_term)}</div>
      </div>
      <button class="btn" type="submit">Save Institution Details</button>
    </form>

    <h2>Working Days</h2>
    <form data-form="working-days">
      ${multiCheck("days", "Select Active Working Days", ALL_DAYS, cfg.working_days)}
      <button class="btn" type="submit">Update Working Days</button>
    </form>

    <h2>Daily Time Slots &amp; Break Schedule</h2>
    ${table(cfg.time_slots)}
    <h3>Add / Configure Time Slot</h3>
    <form data-form="add-slot">
      <div class="row cols-5">
        ${text("slot_id", "Slot ID", "", 'placeholder="e.g. P7"')}${text("name", "Slot Name", "", 'placeholder="e.g. Period 7"')}
        ${text("start_time", "Start Time", "16:00")}${text("end_time", "End Time", "17:00")}
        <div style="padding-top:1.6rem">${check("is_break", "Is Break Period?", false)}</div>
      </div>
      <button class="btn" type="submit">Add Time Slot</button>
    </form>

    <h2>Student Sections</h2>
    ${table(cfg.sections)}`;
};

views.faculty = () => {
  const cfg = state.config;
  const list = cfg.faculty;
  const rows = list.map((f) => ({
    "Faculty ID": f.faculty_id, Name: f.name, Email: f.email || "",
    "Subjects Taught": (f.subjects || []).join(", "), "Max Daily": f.max_daily_sessions ?? 3,
    "Max Weekly Load": f.max_weekly_load ?? 12, "Available Days": (f.available_days || []).join(", "),
    "Unavailable Slots": JSON.stringify(f.unavailable_slots || {}),
  }));
  const opts = list.map((f) => [f.faculty_id, `${f.faculty_id} - ${f.name}`]);

  const addTab = `<form data-form="add-faculty">
      <div class="row cols-2">
        <div>${text("faculty_id", "Faculty ID *", "", 'placeholder="e.g. FAC07"')}${text("name", "Full Name *", "", 'placeholder="e.g. Dr. Donald Knuth"')}${text("email", "Email", "", 'placeholder="e.g. d.knuth@nit.edu"')}</div>
        <div>${num("max_daily", "Max Teaching Periods / Day", 3, 1, 8)}${num("max_weekly", "Max Teaching Periods / Week", 12, 1, 30)}
          ${multiCheck("days", "Available Working Days", cfg.working_days, cfg.working_days)}</div>
      </div>
      <button class="btn" type="submit">Add Faculty</button>
    </form>`;

  if (!list.some((f) => f.faculty_id === ui.editFac)) ui.editFac = list[0]?.faculty_id || "";
  if (!cfg.working_days.includes(ui.editFacDay)) ui.editFacDay = cfg.working_days[0] || "";
  const cur = list.find((f) => f.faculty_id === ui.editFac);
  let editTab = alertBox("info", "No faculty members yet.");
  if (cur) {
    const slotIds = teachingSlots(cfg).map((s) => s.slot_id);
    const unavail = (cur.unavailable_slots || {})[ui.editFacDay] || [];
    editTab = `${select("edit_fac", "Select Faculty Member", opts, ui.editFac, 'data-bind="editFac"')}
      <form data-form="edit-faculty">
        ${text("name", "Name", cur.name)}${text("email", "Email", cur.email || "")}
        <div class="row cols-2">${num("max_daily", "Max Daily Periods", cur.max_daily_sessions ?? 3, 1, 8)}${num("max_weekly", "Max Weekly Load", cur.max_weekly_load ?? 12, 1, 30)}</div>
        ${multiCheck("days", "Available Working Days", cfg.working_days, cur.available_days || [])}
        <div class="field-group-title">Slot-Level Unavailability Restrictions</div>
        ${select("unavail_day", "Restriction Day", pairs(cfg.working_days), ui.editFacDay, 'data-bind="editFacDay"')}
        ${multiCheck("unavail_slots", `Unavailable slots on ${ui.editFacDay}`, slotIds, unavail)}
        <button class="btn" type="submit">Update Faculty Information</button>
      </form>`;
  }

  const delTab = opts.length
    ? `<form data-form="delete-faculty">${select("faculty_id", "Select Faculty to Remove", opts, opts[0][0])}<button class="btn btn-primary" type="submit">Delete Faculty Member</button></form>`
    : alertBox("info", "No faculty members to delete.");

  return `${header("Faculty Management", "Manage teaching faculty, workloads, and day/slot availability restrictions")}
    ${table(rows)}
    ${tabs("faculty", [["Add New Faculty", addTab], ["Edit Faculty", editTab], ["Delete Faculty", delTab]])}`;
};

function subjectFields(cfg, s, isEdit) {
  const facOpts = cfg.faculty.map((f) => [f.faculty_id, `${f.faculty_id} - ${f.name}`]);
  const secOpts = pairs(cfg.sections.map((x) => x.section_id));
  const dur = s.duration_periods ?? 1;
  return `<div class="row cols-2">
      <div>
        ${isEdit ? "" : text("subject_id", "Subject ID *", "", 'placeholder="e.g. CS109"')}
        ${text("name", isEdit ? "Subject Name" : "Subject Name *", s.name || "", isEdit ? "" : 'placeholder="e.g. Machine Learning"')}
        ${select("section_id", "Student Section", secOpts, s.section_id || secOpts[0]?.[0])}
        ${select("faculty_id", "Assigned Faculty Member", facOpts, s.faculty_id || facOpts[0]?.[0])}
      </div>
      <div>
        ${num("sessions_per_week", "Sessions per Week", s.sessions_per_week ?? 3, 1, 6)}
        ${num("duration_periods", "Session Duration (Periods)", dur, 1, 3)}
        ${select("room_type", "Required Room Type", pairs(ROOM_TYPES), s.room_type || "Classroom")}
        ${num("expected_students", "Expected Student Enrollment", s.expected_students ?? 35, 1, 100)}
        ${check("consecutive", "Consecutive Periods Required (Recommended for Labs)", s.consecutive ?? dur > 1)}
      </div>
    </div>`;
}

views.subjects = () => {
  const cfg = state.config;
  const facMap = Object.fromEntries(cfg.faculty.map((f) => [f.faculty_id, f.name]));
  const secMap = Object.fromEntries(cfg.sections.map((s) => [s.section_id, s.name]));
  const rows = cfg.subjects.map((s) => ({
    "Subject ID": s.subject_id, "Course Name": s.name, Section: secMap[s.section_id] ?? s.section_id,
    "Assigned Faculty": facMap[s.faculty_id] ?? s.faculty_id, "Sessions / Week": s.sessions_per_week ?? 1,
    "Duration (Periods)": s.duration_periods ?? 1, "Room Type": s.room_type || "Classroom",
    "Expected Students": s.expected_students ?? 30, Consecutive: s.consecutive ? "Yes" : "No",
  }));
  const opts = cfg.subjects.map((s) => [s.subject_id, `${s.subject_id} - ${s.name}`]);

  const addTab = `<form data-form="add-subject">${subjectFields(cfg, {}, false)}<button class="btn" type="submit">Add Subject</button></form>`;

  if (!cfg.subjects.some((s) => s.subject_id === ui.editSub)) ui.editSub = cfg.subjects[0]?.subject_id || "";
  const cur = cfg.subjects.find((s) => s.subject_id === ui.editSub);
  const editTab = cur
    ? `${select("edit_sub", "Select Subject", opts, ui.editSub, 'data-bind="editSub"')}
       <form data-form="edit-subject">${subjectFields(cfg, cur, true)}<button class="btn" type="submit">Update Subject</button></form>`
    : alertBox("info", "No subjects yet.");

  const delTab = opts.length
    ? `<form data-form="delete-subject">${select("subject_id", "Select Subject to Remove", opts, opts[0][0])}<button class="btn btn-primary" type="submit">Delete Subject</button></form>`
    : alertBox("info", "No subjects to delete.");

  return `${header("Subject & Course Management", "Manage course curricula, assigned faculty, room type requirements, and multi-period sessions")}
    ${table(rows)}
    ${tabs("subjects", [["Add New Subject", addTab], ["Edit Subject", editTab], ["Delete Subject", delTab]])}`;
};

views.classrooms = () => {
  const rooms = state.config.classrooms;
  const opts = rooms.map((r) => [r.room_id, `${r.room_id} - ${r.name} (${r.room_type})`]);

  const addTab = `<form data-form="add-room">
      <div class="row cols-2">
        <div>${text("room_id", "Room ID *", "", 'placeholder="e.g. R204"')}${text("name", "Room Name", "", 'placeholder="e.g. Multimedia Hall"')}</div>
        <div>${num("capacity", "Seating Capacity", 40, 1, 200)}${select("room_type", "Room Classification", pairs(ROOM_TYPES), "Classroom")}${check("available", "Room is Operational / Available", true)}</div>
      </div>
      <button class="btn" type="submit">Add Classroom</button>
    </form>`;

  if (!rooms.some((r) => r.room_id === ui.editRoom)) ui.editRoom = rooms[0]?.room_id || "";
  const cur = rooms.find((r) => r.room_id === ui.editRoom);
  const editTab = cur
    ? `${select("edit_room", "Select Room", opts, ui.editRoom, 'data-bind="editRoom"')}
       <form data-form="edit-room">
         ${text("name", "Room Name", cur.name)}${num("capacity", "Capacity", cur.capacity ?? 40, 1, 200)}
         ${select("room_type", "Room Type", pairs(ROOM_TYPES), cur.room_type || "Classroom")}${check("available", "Available for Scheduling", cur.available ?? true)}
         <button class="btn" type="submit">Update Room</button>
       </form>`
    : alertBox("info", "No classrooms yet.");

  const delTab = opts.length
    ? `<form data-form="delete-room">${select("room_id", "Select Room to Remove", opts, opts[0][0])}<button class="btn btn-primary" type="submit">Delete Room</button></form>`
    : alertBox("info", "No classrooms to delete.");

  return `${header("Classroom & Laboratory Management", "Manage lecture halls, laboratory spaces, seating capacities, and operational availability")}
    ${table(rooms)}
    ${tabs("classrooms", [["Add Classroom", addTab], ["Edit / Toggle Room", editTab], ["Delete Classroom", delTab]])}`;
};

views.generator = () => {
  const m = state.metrics;
  const val = state.validation;
  let results = alertBox("info", "Execute the solver above to inspect real-time search trajectory and heuristic performance metrics.");
  if (m) {
    let stamp = "";
    if (val) {
      stamp = val.is_valid
        ? alertBox("success", "<strong>Independent Timetable Validation Pass:</strong> PASSED with 0 hard constraint violations! Every assignment strictly adheres to faculty availability, room capacity, section independence, and break periods.")
        : alertBox("warning", `<strong>Independent Timetable Validation Pass:</strong> Found ${val.summary_stats.error_count ?? 0} errors and ${val.summary_stats.warning_count ?? 0} warnings.`);
    }
    const trace = (m.trace_events || []).map((t) => ({
      Type: t.type, Variable: t.variable ?? "", Subject: t.subject ?? "", Day: t.day ?? "",
      Period: t.period ?? "", Room: t.room ?? "", Detail: t.reason ?? (t.backtrack_no ? `backtrack #${t.backtrack_no}` : t.depth !== undefined ? `depth ${t.depth}` : ""),
    }));
    results = `<div class="row cols-6">
        ${metric("Variables Scheduled", `${new Set(state.timetable.map((r) => r.session_id)).size} / ${m.sessions_to_schedule ?? 0}`)}
        ${metric("Execution Time", `${m.execution_time_seconds ?? 0} s`)}${metric("Nodes Explored", m.candidate_assignments_explored ?? 0)}
        ${metric("Backtracks", m.backtrack_count ?? 0)}${metric("Constraint Checks", m.constraint_checks ?? 0)}${metric("FC Domain Prunes", m.forward_check_prunes ?? 0)}
      </div>${stamp}
      ${trace.length ? `<h3>Search Trajectory Trace (first ${trace.length} events)</h3>${table(trace)}` : ""}`;
  }

  return `${header("AI Timetable Generator", "Constraint Satisfaction Problem Solver powered by Backtracking Search, MRV, LCV & Forward Checking")}
    <form data-form="solve">
      <div class="row cols-2-1">
        <div>
          <h2 style="margin-top:0">Solver Heuristics &amp; Search Controls</h2>
          <div class="row cols-2">
            <div>
              ${check("use_mrv", "Minimum Remaining Values (MRV) Heuristic", true)}
              ${check("use_lcv", "Least Constraining Value (LCV) Heuristic", true)}
              ${check("use_fc", "Forward Checking (FC)", true)}
            </div>
            <div>
              <label>Search Timeout (Seconds): <strong id="timeout-out">20</strong>
                <input type="range" name="timeout" min="5" max="25" step="5" value="20" oninput="document.getElementById('timeout-out').textContent=this.value"></label>
            </div>
          </div>
          ${num("max_backtracks", "Maximum Backtrack Operations Limit", 15000, 1000, 50000, 1000)}
        </div>
        <div>
          <h2 style="margin-top:0">Run Generator</h2>
          <p>Click below to trigger the CSP Backtracking engine:</p>
          <button class="btn btn-primary btn-block" type="submit">Execute CSP Timetable Solver</button>
        </div>
      </div>
    </form>
    <hr>
    <h2>Execution Metrics &amp; Search Trajectory</h2>
    ${results}`;
};

views.conflicts = () => {
  const val = state.validation;
  let report = alertBox("info", "No timetable has been validated yet. Go to <strong>AI Timetable Generator</strong> and run the solver.");
  if (val) {
    report = `<div class="row cols-4">
        ${metric("Validation Result", val.is_valid ? "VALID" : "INVALID")}
        ${metric("Scheduled Periods", `${val.total_scheduled_periods} / ${val.total_required_periods}`)}
        ${metric("Critical Errors", val.summary_stats.error_count ?? 0)}${metric("Warnings", val.summary_stats.warning_count ?? 0)}
      </div>
      ${val.is_valid
        ? alertBox("success", "<strong>All 10 Hard Constraints Satisfied!</strong> Independent validation verified zero faculty clashes, zero classroom double-bookings, zero student section conflicts, valid room types, sufficient capacities, and zero break period overlaps.")
        : `<h3>Detected Conflicts &amp; Resolution Advice</h3>${val.conflicts.map(conflictCard).join("")}`}`;
  }
  return `${header("Conflict Detection & Diagnostic Engine", "Independent constraint verification pass with root-cause explanations and actionable suggestions")}
    <div id="cfg-conflicts"><div class="alert alert-info">Checking academic configuration…</div></div>
    <h2>Timetable Schedule Verification Results</h2>
    ${report}`;
};

async function loadConfigConflicts() {
  const box = $("#cfg-conflicts");
  try {
    const { conflicts } = await api("/api/config/validate", { config: state.config });
    if (!box.isConnected) return;
    box.innerHTML = conflicts.length
      ? alertBox("error", `Found ${conflicts.length} Pre-Scheduling Configuration Issue(s) in Academic Setup:`) + conflicts.map(conflictCard).join("")
      : alertBox("success", "Academic configuration passed all pre-scheduling checks.");
  } catch (e) {
    if (box.isConnected) box.innerHTML = alertBox("error", esc(e.message));
  }
}

views.viewer = () => {
  const cfg = state.config;
  const tt = state.timetable;
  const head = header("Weekly Timetable Grid", "Interactive weekly schedule grid with multi-dimensional filtering by section, faculty, classroom, and subject");
  if (!tt.length) return head + alertBox("warning", "No timetable generated yet. Please navigate to 'AI Timetable Generator' and click 'Execute CSP Timetable Solver'.");

  const f = ui.viewer;
  const filters = `<div class="row cols-4">
      ${select("section", "Filter by Student Section", [["", "All Sections"], ...pairs(cfg.sections.map((s) => s.section_id))], f.section, 'data-filter="section"')}
      ${select("faculty", "Filter by Faculty", [["", "All Faculty"], ...cfg.faculty.map((x) => [x.faculty_id, x.name])], f.faculty, 'data-filter="faculty"')}
      ${select("room", "Filter by Room", [["", "All Classrooms"], ...pairs(cfg.classrooms.map((r) => r.room_id))], f.room, 'data-filter="room"')}
      ${select("mode", "Display Mode", [["grid", "Weekly Grid View"], ["table", "Structured Table View"]], f.mode, 'data-filter="mode"')}
    </div>`;

  const recs = tt.filter((r) => (!f.section || r.section_id === f.section) && (!f.faculty || r.faculty_id === f.faculty) && (!f.room || r.room_id === f.room));

  if (f.mode === "table") {
    const cols = ["day", "slot_name", "start_time", "end_time", "subject_name", "section_id", "faculty_name", "room_name", "room_type"];
    return `${head}${filters}<h2>Filtered Timetable Records (${recs.length} periods)</h2>${recs.length ? table(recs, cols) : alertBox("info", "No records match the current filter selection.")}`;
  }

  const lookup = {};
  for (const r of recs) (lookup[`${r.day}|${r.slot_id}`] ||= []).push(r);
  const days = cfg.working_days;
  let cells = `<div class="tt-head">Time Slot</div>${days.map((d) => `<div class="tt-head">${esc(d)}</div>`).join("")}`;
  for (const slot of cfg.time_slots) {
    cells += `<div class="tt-slot">${esc(slot.name)}<small>${esc(slot.start_time)} - ${esc(slot.end_time)}</small></div>`;
    for (const day of days) {
      if (slot.is_break) { cells += `<div class="timetable-break">${esc(slot.name)}</div>`; continue; }
      const items = lookup[`${day}|${slot.slot_id}`] || [];
      if (!items.length) { cells += `<div class="timetable-empty">Vacant Slot</div>`; continue; }
      cells += `<div>${items.map((it) => {
        const part = (it.duration_periods || 1) > 1 ? ` (Part ${it.is_consecutive_part}/${it.duration_periods})` : "";
        return `<div class="timetable-cell">
            <div class="top"><strong>${esc(it.subject_id)}</strong><span class="badge ${it.room_type === "Laboratory" ? "badge-lab" : "badge-theory"}">${esc(it.room_type)}</span></div>
            <div class="name">${esc(it.subject_name)}${esc(part)}</div>
            <div class="fac">${esc(it.faculty_name)}</div>
            <div class="room">${esc(it.room_name)} | ${esc(it.section_id)}</div>
          </div>`;
      }).join("")}</div>`;
    }
  }
  return `${head}${filters}<h2>Weekly Schedule Matrix</h2>
    <div class="grid-wrap"><div class="tt-grid" style="grid-template-columns: 1.5fr repeat(${days.length}, 2.2fr)">${cells}</div></div>`;
};

views.benchmark = () => {
  const b = state.benchmark;
  let body = "";
  if (b) {
    const kv = (o) => table(Object.entries(o).map(([k, v]) => ({ Metric: k, Value: v })));
    const summary = [["Basic Backtracking", b.basic], ["Backtracking + Forward Checking", b.forward_checking], ["Full AI (MRV + LCV + Forward Checking)", b.full_ai]].map(([name, m]) => ({
      "Algorithm Configuration": name, "Candidates Explored": m.candidate_assignments_explored, "Constraint Checks": m.constraint_checks,
      Backtracks: m.backtrack_count, "Rejected Choices": m.rejected_assignments, "Execution Time (s)": m.execution_time_seconds,
      "Solved?": m.solution_found ? "Yes" : "No",
    }));
    body = `<div class="row cols-3">
        <div><h3>1. Basic Backtracking</h3><p>Depth-first search with static variable order and no forward pruning.</p>${kv(b.basic)}</div>
        <div><h3>2. Backtracking + FC</h3><p>Forward checking added to prune domain conflicts immediately.</p>${kv(b.forward_checking)}</div>
        <div><h3>3. Full AI (MRV + LCV + FC)</h3><p>MRV fail-first variable ordering + LCV value ordering + Forward Checking.</p>${kv(b.full_ai)}</div>
      </div>
      <hr><h2>Performance Comparison Table</h2>${table(summary)}
      ${alertBox("info", "<strong>Viva Explanation Insight:</strong> Notice how Forward Checking drastically slashes the number of candidate assignments explored and constraint checks by pruning domain options upfront before recursion. MRV ensures the solver addresses the tightest constraints (such as laboratory classes with limited rooms and multi-hour blocks) first!")}`;
  }
  return `${header("CSP Algorithm Performance & Benchmark Analysis", "Empirical comparison between Basic Backtracking, Forward Checking, and Full AI Heuristics (MRV + LCV + FC)")}
    <p>To demonstrate genuine Constraint Satisfaction Problem solving for an AI course, this benchmark executes three solver configurations on the <strong>exact same institutional dataset</strong>:</p>
    <ol>
      <li><strong>Basic Backtracking:</strong> Standard depth-first search without variable or value heuristics.</li>
      <li><strong>Backtracking + Forward Checking (FC):</strong> Prunes conflicting future domain values after each assignment; detects domain wipeouts early.</li>
      <li><strong>Full AI Solver (MRV + LCV + FC):</strong> Minimum Remaining Values for fail-first variable selection, Least Constraining Value for value ordering, and Forward Checking.</li>
    </ol>
    <button class="btn btn-primary" data-action="benchmark">Run Comparative Benchmark on Current Dataset</button>
    ${body}`;
};

views.export = () => `${header("Export & Configuration Reset", "Export generated timetable to CSV, generate validation audit logs, or restore demonstration datasets")}
    <div class="row cols-2">
      <div class="panel">
        <h2 style="margin-top:0">Export Timetable &amp; Audit Report</h2>
        ${state.timetable.length
          ? `<button class="btn btn-block" data-action="export-csv">Download Timetable as CSV</button>`
          : alertBox("warning", "No active timetable available for export. Generate one first.")}
        <div style="height:.6rem"></div>
        <button class="btn btn-block" data-action="export-report">Download Full Audit &amp; Validation Report (.md)</button>
        <div style="height:.6rem"></div>
        <button class="btn btn-block" data-action="export-config">Download Academic Configuration (.json)</button>
      </div>
      <div class="panel">
        <h2 style="margin-top:0">Reset &amp; Demonstration Datasets</h2>
        <p>Quickly reload baseline data or demonstrate failure handling:</p>
        <button class="btn btn-block" data-action="reset-default">Restore Default Northstar Institute Dataset</button>
        <div style="height:.6rem"></div>
        <button class="btn btn-block" data-action="reset-infeasible">Load Infeasible Test Case (Demonstrate Failure Handling)</button>
        <div style="height:.6rem"></div>
        <label>Import Academic Configuration (.json)<input type="file" accept="application/json,.json" data-action="import-config"></label>
      </div>
    </div>`;

views.docs = () => {
  const formulation = `<h3>1. CSP Mathematical Formulation</h3>
    <p>An academic timetable problem is formulated as a Constraint Satisfaction Problem <strong>𝒫 = ⟨X, D, C⟩</strong>.</p>
    <ul>
      <li><strong>Variables (X):</strong> Each required weekly session <em>j</em> of subject <em>i</em> is an individual variable V<sub>i,j</sub>.
        <br><code>X = { V(i,j) | 1 ≤ i ≤ |Subjects|, 1 ≤ j ≤ Sessions(i) }</code></li>
      <li><strong>Domains (D):</strong> Each variable V has domain D(V) ⊆ Days × TeachingSlots × Rooms. A value v = (d, s, r) is in D(V) if and only if:
        <ol><li>RoomType(r) = RoomType(V)</li><li>Capacity(r) ≥ ExpectedStudents(V)</li><li>r is active/available</li>
        <li>Faculty Fac(V) is available on day d and slot s</li><li>For multi-period sessions (k &gt; 1), consecutive slots [s, s+k−1] do not cross breaks.</li></ol></li>
      <li><strong>Hard Constraints (C):</strong>
        <ol><li><strong>Faculty Conflict:</strong> ∀ V<sub>a</sub>, V<sub>b</sub> where Fac(V<sub>a</sub>) = Fac(V<sub>b</sub>) and a ≠ b, assigned slots must not overlap.</li>
        <li><strong>Classroom Conflict:</strong> ∀ V<sub>a</sub>, V<sub>b</sub> where Room(V<sub>a</sub>) = Room(V<sub>b</sub>) and a ≠ b, assigned slots must not overlap.</li>
        <li><strong>Section Conflict:</strong> ∀ V<sub>a</sub>, V<sub>b</sub> where Sec(V<sub>a</sub>) = Sec(V<sub>b</sub>) and a ≠ b, assigned slots must not overlap.</li>
        <li><strong>Faculty Workload:</strong> Daily sessions ≤ MaxDaily and weekly sessions ≤ MaxWeekly.</li>
        <li><strong>Break Constraint:</strong> Zero classes scheduled during designated break periods.</li></ol></li>
    </ul>
    <h3>2. Backtracking Search Algorithm Pseudocode</h3>
    <pre>def BACKTRACKING_SEARCH(csp):
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

    return None  # Trigger backtracking to parent node</pre>`;

  const qa = [
    ["Why is academic timetabling modeled as a CSP instead of using pure machine learning?", "Academic scheduling requires strict satisfaction of hard mathematical constraints (no teacher in two places at once, no room double-booked). Machine learning algorithms (neural networks) are probabilistic and often violate hard constraints. CSP guarantees 100% adherence to all hard constraints and provides verifiable, explainable conflict detection."],
    ["What is the Minimum Remaining Values (MRV) heuristic?", "MRV, also known as the \"Most Constrained Variable\" or \"Fail-First\" heuristic, selects the variable with the smallest number of legal remaining values in its domain. By assigning the most difficult variable first, MRV detects failure early before deep recursion."],
    ["How does the Degree Heuristic complement MRV?", "When multiple variables have the same minimum domain size, the Degree Heuristic breaks ties by selecting the variable involved in the largest number of constraints with other unassigned variables, reducing the branching factor of future choices."],
    ["What is the Least Constraining Value (LCV) heuristic?", "LCV is a value-ordering heuristic that prefers the value that rules out the fewest choices for neighboring unassigned variables in the constraint graph (\"Fail-Last\" for values), leaving maximum flexibility for future assignments."],
    ["What is Forward Checking and how does it prevent thrashing?", "Whenever a variable X is assigned value v, Forward Checking looks ahead to all unassigned variables Y connected to X by constraints and removes values from Y's domain that are inconsistent with v. If any variable's domain becomes empty (domain wipeout), the algorithm immediately backtracks without exploring a futile subtree."],
    ["What happens if an impossible configuration is provided (e.g. 35 periods requested in a 30-period week)?", "Our system uses a two-tier approach: first, a pre-scheduling analytical validator detects mathematical infeasibilities (such as Pigeonhole principle violations and room shortages) before search. Second, if search is attempted, the CSP solver terminates safely at the domain initialization stage or backtrack bound and provides clear diagnostic reasons."],
    ["How are laboratory classes handled differently from theory lectures?", "Laboratory classes have two distinct requirements: (1) Room type restriction (must be assigned to a Laboratory room with required capacity), and (2) Multi-period block allocation (e.g. 2 consecutive hours) that cannot cross break periods."],
    ["What is independent timetable validation?", "Rather than assuming the solver output is valid, the system passes the generated timetable through an independent, decoupled validator (constraints.py) that audits every assignment against all 10 hard constraints."],
    ["What is the time complexity of the Backtracking Search algorithm?", "The worst-case time complexity of CSP backtracking is O(dⁿ), where n is the number of variables (sessions) and d is the maximum domain size. Heuristics like MRV, LCV, and Forward Checking drastically prune the practical search space to polynomial-like efficiency on typical college instances."],
    ["What are future enhancements for SmartSlot AI?", "Incorporating soft constraints (faculty preferred time slots, minimizing student gap hours) via Optimization / Arc-Consistency (AC-3 / AC-4) and Genetic Algorithms for multi-objective optimization."],
  ];
  const qaHtml = `<h3>Comprehensive Viva Examination Q&amp;A</h3>` + qa.map(([q, a], i) => `<p><strong>Q${i + 1}: ${esc(q)}</strong></p><blockquote><em>Answer:</em> ${esc(a)}</blockquote>`).join("");

  const arch = `<h3>Modular System Architecture</h3>
    <pre>+------------------------------------------------------------------+
|          SmartSlot AI - Web Client (public/index.html, app.js)   |
|   - Single-page UI (Vercel CDN)  - Weekly Grid Visualization     |
|   - Heuristic Benchmark Panel    - Config kept in localStorage   |
+---------------------------------+--------------------------------+
                                  | JSON over HTTPS
                                  v
+------------------------------------------------------------------+
|        Serverless API (api/index.py, FastAPI on Vercel)          |
+---------------------------------+--------------------------------+
                                  |
                +-----------------+-----------------+
                |                                   |
                v                                   v
+-------------------------------+   +-------------------------------+
|  Data Manager                 |   |  AI Scheduling Engine         |
|  (data_manager.py)            |   |  (scheduler.py)               |
|  - Input CRUD & Validation    |   |  - CSP Formulation            |
|  - CSV & Report Export        |   |  - Backtracking Search        |
+---------------+---------------+   |  - MRV & Degree Heuristics    |
                |                   |  - LCV Value Ordering         |
                |                   |  - Forward Checking (FC)      |
                v                   +---------------+---------------+
+-------------------------------+                   |
|  Independent Constraint       |<------------------+
|  Validation Engine            |
|  (constraints.py)             |
|  - 10 Hard Constraints Audit  |
|  - Conflict Root-Cause Advice |
+-------------------------------+</pre>`;

  return `${header("Academic Deliverable & Viva Preparation Guide", "Theoretical foundation, CSP mathematical model, pseudocode, and viva examination questions")}
    ${tabs("docs", [["CSP Formulation & Pseudocode", formulation], ["Top 10 Viva Questions & Answers", qaHtml], ["System Architecture", arch]])}`;
};

// ==============================================================================
// Form submissions & actions
// ==============================================================================
const forms = {
  institution: (d) => mutate("update_institution", { institution_name: d.str("institution_name"), department: d.str("department"), academic_term: d.str("academic_term") }),
  "working-days": (d) => mutate("set_working_days", { working_days: ALL_DAYS.filter((x) => d.all("days").includes(x)) }),
  "add-slot": (d) => mutate("add_time_slot", { slot_id: d.str("slot_id"), name: d.str("name"), start_time: d.str("start_time"), end_time: d.str("end_time"), is_break: d.bool("is_break") }),

  "add-faculty": (d) => mutate("add_faculty", {
    faculty_id: d.str("faculty_id"), name: d.str("name"), email: d.str("email"), subjects: [],
    max_daily: d.int("max_daily"), max_weekly: d.int("max_weekly"), available_days: d.all("days"),
  }),
  "edit-faculty": (d) => {
    const cur = state.config.faculty.find((f) => f.faculty_id === ui.editFac);
    const unavail = structuredClone(cur.unavailable_slots || {});
    const slots = d.all("unavail_slots");
    if (slots.length) unavail[ui.editFacDay] = slots;
    else delete unavail[ui.editFacDay];
    return mutate("update_faculty", {
      faculty_id: ui.editFac, name: d.str("name"), email: d.str("email"), subjects: cur.subjects || [],
      max_daily: d.int("max_daily"), max_weekly: d.int("max_weekly"), available_days: d.all("days"), unavailable_slots: unavail,
    });
  },
  "delete-faculty": (d) => confirm(`Delete faculty '${d.str("faculty_id")}'?`) && mutate("delete_faculty", { faculty_id: d.str("faculty_id") }),

  "add-subject": (d) => mutate("add_subject", subjectPayload(d, d.str("subject_id"))),
  "edit-subject": (d) => mutate("update_subject", subjectPayload(d, ui.editSub)),
  "delete-subject": (d) => confirm(`Delete subject '${d.str("subject_id")}'?`) && mutate("delete_subject", { subject_id: d.str("subject_id") }),

  "add-room": (d) => mutate("add_classroom", { room_id: d.str("room_id"), name: d.str("name"), capacity: d.int("capacity"), room_type: d.str("room_type"), available: d.bool("available") }),
  "edit-room": (d) => mutate("update_classroom", { room_id: ui.editRoom, name: d.str("name"), capacity: d.int("capacity"), room_type: d.str("room_type"), available: d.bool("available") }),
  "delete-room": (d) => confirm(`Delete classroom '${d.str("room_id")}'?`) && mutate("delete_classroom", { room_id: d.str("room_id") }),

  solve: (d) => runSolver({ use_mrv: d.bool("use_mrv"), use_lcv: d.bool("use_lcv"), use_fc: d.bool("use_fc"), timeout: d.float("timeout"), max_backtracks: d.int("max_backtracks") }),
};

function subjectPayload(d, subjectId) {
  return {
    subject_id: subjectId, name: d.str("name"), section_id: d.str("section_id"), faculty_id: d.str("faculty_id"),
    sessions_per_week: d.int("sessions_per_week"), duration_periods: d.int("duration_periods"), room_type: d.str("room_type"),
    expected_students: d.int("expected_students"), consecutive: d.bool("consecutive"),
  };
}

async function resetTo(scenario) {
  busy("Loading dataset…");
  try {
    state.config = await api(`/api/config/default?scenario=${scenario}`);
    clearResults();
    saveState();
    toast(scenario === "infeasible"
      ? "Loaded intentionally infeasible test case: 0 available laboratories, section overloaded, and faculty weekly overload."
      : "Configuration reset to fictional Northstar Institute of Technology dataset.", scenario !== "infeasible");
  } catch (e) {
    toast(e.message, false);
  } finally {
    busy();
    render();
  }
}

const actions = {
  "solve-default": () => runSolver(),
  benchmark: async () => {
    busy("Executing empirical benchmark across all 3 search configurations… (may take up to a minute)");
    try {
      state.benchmark = await api("/api/benchmark", { config: state.config });
      saveState();
      toast("Benchmark completed successfully!");
    } catch (e) {
      toast(e.message, false);
    } finally {
      busy();
      render();
    }
  },
  "export-csv": async () => {
    try {
      download("northstar_academic_timetable.csv", await api("/api/export/csv", { config: state.config, timetable: state.timetable }, { text: true }), "text/csv");
    } catch (e) { toast(e.message, false); }
  },
  "export-report": async () => {
    try {
      const md = await api("/api/export/report", { config: state.config, timetable: state.timetable, validation: state.validation, metrics: state.metrics }, { text: true });
      download("timetable_validation_report.md", md, "text/markdown");
    } catch (e) { toast(e.message, false); }
  },
  "export-config": () => download("academic_config.json", JSON.stringify(state.config, null, 2), "application/json"),
  "reset-default": () => resetTo("default"),
  "reset-infeasible": () => resetTo("infeasible"),
};

// ==============================================================================
// Rendering & routing
// ==============================================================================
function currentView() {
  const v = location.hash.replace("#", "");
  return views[v] ? v : "dashboard";
}

function render() {
  const v = currentView();
  const labels = Object.fromEntries(VIEWS);
  $("#nav").innerHTML = NAV_GROUPS.map(([group, ids]) => `<details class="nav-group" open><summary>${group}</summary>${
    ids.map((id) => `<a href="#${id}" class="${id === v ? "active" : ""}">${labels[id]}</a>`).join("")
  }</details>`).join("");
  $("#sb-inst").textContent = state.config.institution_name || "Northstar Institute";
  $("#sb-term").textContent = state.config.academic_term || "Fall 2026";
  $("#view").innerHTML = views[v]();
  if (v === "conflicts") loadConfigConflicts();
}

function bindEvents() {
  window.addEventListener("hashchange", () => {
    $("#sidebar").classList.remove("open");
    render();
    window.scrollTo(0, 0);
  });
  $("#menu-toggle").addEventListener("click", () => $("#sidebar").classList.toggle("open"));

  const view = $("#view");
  view.addEventListener("submit", (e) => {
    const form = e.target.closest("form[data-form]");
    if (!form) return;
    e.preventDefault();
    forms[form.dataset.form]?.(formData(form));
  });
  view.addEventListener("click", (e) => {
    const el = e.target.closest("[data-action], [data-nav], [data-tab]");
    if (!el) return;
    if (el.dataset.nav) location.hash = el.dataset.nav;
    else if (el.dataset.tab !== undefined) { ui.tabs[el.dataset.tabs] = Number(el.dataset.tab); render(); }
    else if (el.tagName !== "INPUT") actions[el.dataset.action]?.();
  });
  view.addEventListener("change", (e) => {
    const el = e.target;
    if (el.dataset.bind) { ui[el.dataset.bind] = el.value; render(); }
    else if (el.dataset.filter) { ui.viewer[el.dataset.filter] = el.value; render(); }
    else if (el.dataset.action === "import-config" && el.files[0]) {
      el.files[0].text().then((t) => {
        const cfg = JSON.parse(t);
        if (!Array.isArray(cfg.subjects) || !Array.isArray(cfg.time_slots)) throw new Error("Not a SmartSlot configuration file.");
        state.config = cfg;
        clearResults();
        saveState();
        render();
        toast("Configuration imported.");
      }).catch((err) => toast(err.message, false));
    }
  });
}

// Drag the sidebar's right edge to resize it; the width is remembered per browser.
const SIDEBAR_WIDTH_KEY = "smartslot_sidebar_width";
const SIDEBAR_MIN = 200;
const SIDEBAR_DEFAULT = 250;
const sidebarMax = () => Math.min(600, Math.floor(window.innerWidth * 0.5));

function setSidebarWidth(px, persist = true) {
  const w = Math.round(Math.max(SIDEBAR_MIN, Math.min(sidebarMax(), px)));
  document.documentElement.style.setProperty("--sidebar-w", `${w}px`);
  if (persist) {
    try { localStorage.setItem(SIDEBAR_WIDTH_KEY, String(w)); } catch (_) { /* storage unavailable */ }
  }
}

function initSidebarResize() {
  const handle = $("#sidebar-resizer");
  try {
    const saved = parseInt(localStorage.getItem(SIDEBAR_WIDTH_KEY), 10);
    if (saved) setSidebarWidth(saved, false);
  } catch (_) { /* storage unavailable */ }

  handle.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    handle.setPointerCapture(e.pointerId);
    document.body.classList.add("resizing");
    const onMove = (ev) => setSidebarWidth(ev.clientX, false);
    const onUp = (ev) => {
      handle.removeEventListener("pointermove", onMove);
      handle.removeEventListener("pointerup", onUp);
      document.body.classList.remove("resizing");
      setSidebarWidth(ev.clientX);
    };
    handle.addEventListener("pointermove", onMove);
    handle.addEventListener("pointerup", onUp);
  });
  handle.addEventListener("dblclick", () => setSidebarWidth(SIDEBAR_DEFAULT));
  handle.addEventListener("keydown", (e) => {
    const step = e.shiftKey ? 50 : 10;
    const current = $("#sidebar").getBoundingClientRect().width;
    if (e.key === "ArrowLeft") setSidebarWidth(current - step);
    else if (e.key === "ArrowRight") setSidebarWidth(current + step);
  });
}

async function init() {
  bindEvents();
  initSidebarResize();
  const saved = loadState();
  if (saved && saved.config) {
    state = { ...state, ...saved };
    render();
    return;
  }
  busy("Loading Northstar Institute dataset…");
  try {
    state.config = await api("/api/config/default");
    saveState();
    render();
  } catch (e) {
    $("#view").innerHTML = alertBox("error", `Could not reach the SmartSlot API: ${esc(e.message)}`);
  } finally {
    busy();
  }
}

init();
