import json
from datetime import date as Date
from pathlib import Path

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

mcp = FastMCP("trip-planner")

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TRIPS_FILE = Path(__file__).parent / "trips.json"
MAX_DAYS_AHEAD = 15  # Open-Meteo gives 16 days: today + 15


# ---------- shared helper ----------

def _parse_date(value: str, label: str = "date") -> Date:
    """Turn 'YYYY-MM-DD' into a date, or raise a clear error."""
    try:
        return Date.fromisoformat(value)
    except ValueError:
        raise ToolError(f"Invalid {label} '{value}'. Use YYYY-MM-DD, e.g. 2026-11-05.") from None


# ---------- DATA tool ----------

def _get_forecast(city: str, days: int) -> dict:
    if not 1 <= days <= MAX_DAYS_AHEAD + 1:
        raise ToolError(f"days must be between 1 and {MAX_DAYS_AHEAD + 1}.")

    # 1) City name -> coordinates
    geo = httpx.get(GEO_URL, params={"name": city, "count": 1}, timeout=10).json()
    if not geo.get("results"):
        raise ToolError(f"City '{city}' not found. Check the spelling.")
    place = geo["results"][0]

    # 2) Coordinates -> daily forecast
    data = httpx.get(FORECAST_URL, params={
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "forecast_days": days,
        "timezone": "auto",
    }, timeout=10).json()["daily"]

    return {
        "city": place["name"],
        "country": place.get("country"),
        "days": [
            {"date": d, "max_c": hi, "min_c": lo, "rain_chance_pct": rain or 0}
            for d, hi, lo, rain in zip(
                data["time"], data["temperature_2m_max"],
                data["temperature_2m_min"], data["precipitation_probability_max"])
        ],
    }


@mcp.tool
def get_forecast(city: str, days: int = 3) -> dict:
    """Get the daily weather forecast for a city, starting today (1-16 days).
    Read-only: does not save or change anything.
    Returns max/min temperature (°C) and rain chance (%) per day."""
    return _get_forecast(city, days)


# ---------- ACTION tool ----------

def _save_trip(city: str, start_date: str, end_date: str = "", note: str = "") -> dict:
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date") if end_date else start
    if end < start:
        raise ToolError("end_date cannot be before start_date.")

    trips = json.loads(TRIPS_FILE.read_text()) if TRIPS_FILE.exists() else []
    trip = {
        "id": len(trips) + 1,
        "city": city,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "note": note,
    }
    trips.append(trip)
    TRIPS_FILE.write_text(json.dumps(trips, indent=2, ensure_ascii=False))
    return {"saved": True, "trip": trip}


@mcp.tool
def save_trip(city: str, start_date: str, end_date: str = "", note: str = "") -> dict:
    """Save a planned trip to the user's trip list.
    Dates are YYYY-MM-DD. end_date is optional (defaults to start_date).
    note is optional free text.
    This changes stored data; it does not look up weather."""
    return _save_trip(city, start_date, end_date, note)


# ---------- ORCHESTRATION tool ----------

def _plan_trip(city: str, start_date: str, end_date: str = "") -> dict:
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date") if end_date else start

    today = Date.today()
    if start < today:
        raise ToolError("start_date is in the past.")
    if end < start:
        raise ToolError("end_date cannot be before start_date.")
    if (end - today).days > MAX_DAYS_AHEAD:
        raise ToolError(f"Forecasts only go {MAX_DAYS_AHEAD} days ahead. "
                        "Pick an earlier end_date.")

    # Step 1: Data tool logic -> forecast from today until the last day of the trip
    forecast = _get_forecast(city, (end - today).days + 1)
    stay = [d for d in forecast["days"]
            if start.isoformat() <= d["date"] <= end.isoformat()]

    # Turn the weather for the whole stay into a short note
    low = min(d["min_c"] for d in stay)
    high = max(d["max_c"] for d in stay)
    rainy = [d["date"] for d in stay if d["rain_chance_pct"] >= 50]
    note = f"{len(stay)} day(s), {low}–{high}°C."
    if rainy:
        note += f" Rain likely on {', '.join(rainy)}. Bring an umbrella."
    else:
        note += " No rain expected."

    # Step 2: Action tool logic -> save the trip with that note
    saved = _save_trip(forecast["city"], start.isoformat(), end.isoformat(), note)
    return {"forecast": stay, **saved}


@mcp.tool
def plan_trip(city: str, start_date: str, end_date: str = "") -> dict:
    """Plan a trip: look up the weather for every day of the stay, then save
    the trip with a weather summary note.
    Dates are YYYY-MM-DD, within the next 15 days. end_date is optional
    (defaults to a one-day trip).
    Use this when the user wants to plan or book a trip, not just check weather."""
    return _plan_trip(city, start_date, end_date)


if __name__ == "__main__":
    mcp.run()