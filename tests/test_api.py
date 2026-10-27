"""
Tests for the stateless serverless API (api/index.py) deployed on Vercel.
"""

import pytest
from fastapi.testclient import TestClient

from api.index import app

client = TestClient(app)


@pytest.fixture
def config():
    return client.get("/api/config/default").json()


def test_default_and_infeasible_configs():
    default = client.get("/api/config/default").json()
    infeasible = client.get("/api/config/default", params={"scenario": "infeasible"}).json()
    assert default["subjects"]
    assert default != infeasible


def test_validate_config(config):
    r = client.post("/api/config/validate", json={"config": config})
    assert r.status_code == 200
    assert not any(c["severity"] == "ERROR" for c in r.json()["conflicts"])


def test_mutate_add_and_duplicate_classroom(config):
    payload = {"room_id": "R999", "name": "Test Hall", "capacity": 50, "room_type": "Classroom", "available": True}
    r = client.post("/api/config/mutate", json={"config": config, "action": "add_classroom", "payload": payload}).json()
    assert r["ok"] is True
    assert any(room["room_id"] == "R999" for room in r["config"]["classrooms"])

    dup = client.post("/api/config/mutate", json={"config": r["config"], "action": "add_classroom", "payload": payload}).json()
    assert dup["ok"] is False


def test_mutate_rejects_unknown_action(config):
    r = client.post("/api/config/mutate", json={"config": config, "action": "drop_everything", "payload": {}})
    assert r.status_code == 400


def test_solve_returns_valid_timetable(config):
    r = client.post("/api/solve", json={"config": config, "options": {}}).json()
    assert r["success"] is True
    assert r["validation"]["is_valid"] is True
    assert len(r["timetable"]) == r["validation"]["total_required_periods"]


def test_solve_infeasible_reports_errors():
    infeasible = client.get("/api/config/default", params={"scenario": "infeasible"}).json()
    r = client.post("/api/solve", json={"config": infeasible}).json()
    assert r["success"] is False
    assert r["timetable"] == []
    assert r["validation"]["conflicts"]


def test_exports(config):
    solved = client.post("/api/solve", json={"config": config}).json()
    csv = client.post("/api/export/csv", json={"config": config, "timetable": solved["timetable"]})
    assert csv.status_code == 200
    assert "subject_name" in csv.text.splitlines()[0]

    report = client.post("/api/export/report", json={
        "config": config, "timetable": solved["timetable"],
        "validation": solved["validation"], "metrics": solved["metrics"],
    })
    assert "VALID (CONFLICT-FREE)" in report.text


def test_missing_config_is_rejected():
    assert client.post("/api/solve", json={}).status_code == 400
