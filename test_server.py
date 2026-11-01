"""Tests for the three MCP tools (run with: pytest -v)."""
import json
from datetime import date, timedelta

import pytest
from fastmcp.exceptions import ToolError

import server

TODAY = date.today()


def day(n: int) -> str:
    """Date n days from today as YYYY-MM-DD."""
    return (TODAY + timedelta(days=n)).isoformat()


@pytest.fixture(autouse=True)
def temp_trips_file(tmp_path, monkeypatch):
    """Use a temporary trips.json so tests never touch the real one."""
    monkeypatch.setattr(server, "TRIPS_FILE", tmp_path / "trips.json")


@pytest.fixture
def fake_forecast(monkeypatch):
    """Replace the weather API with fixed data so tests run offline."""
    def _fake(city, days):
        return {
            "city": city,
            "country": "Testland",
            "days": [
                {"date": day(i), "max_c": 10 + i, "min_c": 2,
                 "rain_chance_pct": 80 if i == 2 else 0}
                for i in range(days)
            ],
        }
    monkeypatch.setattr(server, "_get_forecast", _fake)


# ---------- Data tool: get_forecast ----------

def test_forecast_invalid_days():
    with pytest.raises(ToolError, match="days must be between"):
        server._get_forecast("Beirut", 0)


@pytest.mark.network
def test_forecast_real_city():
    result = server._get_forecast("Beirut", 2)
    assert result["city"] == "Beirut"
    assert len(result["days"]) == 2


@pytest.mark.network
def test_forecast_unknown_city():
    with pytest.raises(ToolError, match="not found"):
        server._get_forecast("Xyzabcqq", 2)


# ---------- Action tool: save_trip ----------

def test_save_trip_writes_file():
    result = server._save_trip("Beirut", day(3), day(5), "visit family")
    assert result["saved"] is True
    saved = json.loads(server.TRIPS_FILE.read_text())
    assert saved[0]["city"] == "Beirut"
    assert saved[0]["end_date"] == day(5)


def test_save_trip_end_defaults_to_start():
    trip = server._save_trip("Beirut", day(3))["trip"]
    assert trip["end_date"] == trip["start_date"]


def test_save_trip_bad_date_format():
    with pytest.raises(ToolError, match="Invalid start_date"):
        server._save_trip("Beirut", "5/11/2026")


def test_save_trip_end_before_start():
    with pytest.raises(ToolError, match="cannot be before"):
        server._save_trip("Beirut", day(5), day(3))


# ---------- Orchestration tool: plan_trip ----------

def test_plan_trip_checks_every_day_and_saves(fake_forecast):
    result = server._plan_trip("Paris", day(1), day(3))
    assert len(result["forecast"]) == 3            # all days of the stay
    assert result["saved"] is True                 # action step ran
    assert "Bring an umbrella" in result["trip"]["note"]  # day 2 is rainy
    assert len(json.loads(server.TRIPS_FILE.read_text())) == 1


def test_plan_trip_past_date():
    with pytest.raises(ToolError, match="in the past"):
        server._plan_trip("Paris", day(-1))


def test_plan_trip_too_far_ahead():
    with pytest.raises(ToolError, match="15 days ahead"):
        server._plan_trip("Paris", day(2), day(20))


def test_plan_trip_does_not_save_on_failure(fake_forecast):
    with pytest.raises(ToolError):
        server._plan_trip("Paris", day(5), day(2))
    assert not server.TRIPS_FILE.exists()
