Mohamad El AJouz - 202401494
Youtube link: https://youtu.be/JB3NeqRcmgs 
# MCP Trip Planner

An MCP toolkit built with **FastMCP** and connected to an agent built with the **OpenAI Agents SDK**.
The agent checks the weather and plans trips by calling three single-purpose MCP tools.

EECE 503P/798S: Agentic Systems, Assignment C5 (Agent Tools)

## The three tools

| Category | Tool | What it does | Failure cases |
|---|---|---|---|
| **Data** | `get_forecast(city, days=3)` | Looks up the daily forecast (max/min °C, rain %) for a city. Read-only. | Unknown city, `days` outside 1–16 |
| **Action** | `save_trip(city, start_date, end_date="", note="")` | Saves a trip to `trips.json`. Does not look up weather. | Bad date format, end date before start date |
| **Orchestration** | `plan_trip(city, start_date, end_date="")` | Gets the forecast for every day of the stay, builds a weather note, then saves the trip. | Past date, more than 15 days ahead, plus any error from the two steps it coordinates |

Every failure raises a clear `ToolError` message instead of failing silently, and that message is passed back to the agent so it can explain the problem to the user.

Weather data comes from [Open-Meteo](https://open-meteo.com/), which is free and needs no API key.

## Architecture

```
User  ->  agent.py (Host, OpenAI Agents SDK + LLM)
              |
              |  MCPServerStdio (MCP Client, stdio)
              v
          server.py (MCP Server, FastMCP)
              |-- get_forecast  -> Open-Meteo API
              |-- save_trip     -> trips.json
              '-- plan_trip     -> get_forecast logic + save_trip logic
```

`agent.py` starts `server.py` as a subprocess, discovers its tools at runtime with `list_tools()`, and lets the model choose which tool to call. Each tool call and result is printed as `[MCP call]` / `[MCP result]` so the full round trip is visible.

## Project structure

```
mcp-trip-planner/
├── server.py          # FastMCP server with the 3 tools
├── agent.py           # OpenAI Agents SDK host/client (interactive chat)
├── test_server.py     # pytest tests, including failure cases
├── pytest.ini         # registers the "network" test marker
├── requirements.txt
├── .env               # your API key (not committed)
└── .gitignore
```

## Setup

Requires Python 3.10+.

```bash
git clone https://github.com/mohamadaj/mcp-trip-planner.git 
cd mcp-trip-planner
python -m venv .venv

# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### API key

The agent uses **Groq** (free) as the LLM provider through its OpenAI-compatible endpoint, with the `openai/gpt-oss-120b` model.

1. Create a key at <https://console.groq.com/keys>.
2. Create a file named `.env` in the project folder:

```
GROQ_API_KEY=gsk_your_key_here
```

## Run the agent

```bash
python agent.py
```

Example queries:

```
What's the weather in Rome for the next 3 days?        -> get_forecast
Save a trip to Beirut from Nov 10 to Nov 12, note: visit family   -> save_trip
Plan a trip to Paris from Nov 4 to Nov 7               -> plan_trip
Plan a trip to Atlantisville tomorrow                  -> plan_trip, "city not found" error
```

Type `exit` to quit.

## Run the tests

```bash
pytest -v                 # all 11 tests
pytest -v -m "not network"  # offline only (skips the 2 tests that call Open-Meteo)
```

The tests use a temporary `trips.json`, so they never change your real trip list. The `plan_trip` tests replace the weather API with fixed fake data, so their results are predictable.

## Challenges and fixes

- **Keeping tools single-purpose:** the real logic lives in plain helper functions (`_get_forecast`, `_save_trip`). The `@mcp.tool` functions only expose them, and `plan_trip` reuses the helpers instead of duplicating code.
- **Hidden tool errors:** by default the Agents SDK replaced tool errors with a generic "An error occurred" message, which hid both bugs and my intended error messages. Fixed with `failure_error_function` on `MCPServerStdio`.
- **Tool call timeouts:** the default 5-second MCP session timeout was too short for a tool that makes two external API calls. Fixed with `client_session_timeout_seconds=30`.
- **LLM provider:** new Google AI Studio keys (`AQ.` format) did not work with the OpenAI-compatible endpoint the SDK uses, so I switched the model provider to Groq. Only the client setup in `agent.py` changed; the MCP server is provider-independent.
