import asyncio
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents import Agent, Runner, OpenAIChatCompletionsModel, set_tracing_disabled
from agents.mcp import MCPServerStdio

load_dotenv()
set_tracing_disabled(True)  # tracing uploads to OpenAI; we don't use OpenAI

# Point the OpenAI Agents SDK at Groq's OpenAI-compatible endpoint
groq = AsyncOpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1",
)
model = OpenAIChatCompletionsModel(model="openai/gpt-oss-120b", openai_client=groq)


SERVER_FILE = Path(__file__).parent / "server.py"


def show_tool_calls(result):
    """Print which MCP tools the agent called, so the round trip is visible."""
    for item in result.new_items:
        if item.type == "tool_call_item":
            raw = item.raw_item
            print(f"  [MCP call]   {raw.name}({raw.arguments})")
        elif item.type == "tool_call_output_item":
            print(f"  [MCP result] {str(item.output)[:150]}")


async def main():
    # Host/Client: launch our FastMCP server as a subprocess and connect over stdio
    async with MCPServerStdio(
        name="trip-planner",
        params={"command": sys.executable, "args": [str(SERVER_FILE)]},
        cache_tools_list=True,
         failure_error_function=lambda ctx, e: f"Tool error: {e}",
         client_session_timeout_seconds=30,
    ) as server:
        tools = await server.list_tools()
        print("Connected. Tools discovered:", [t.name for t in tools])

        agent = Agent(
            name="Trip Planner",
            instructions=(
                f"You help users check weather and plan trips. Today is {date.today()}. "
                "Convert relative dates like 'this weekend' to YYYY-MM-DD. "
                "Use get_forecast to only check weather, save_trip to save a trip "
                "the user already decided on, and plan_trip to plan a new trip with weather. "
                "If a tool returns an error, explain it to the user simply."
            ),
            model=model,
            mcp_servers=[server],
        )

        history = []
        while True:
            user = input("\nYou: ").strip()
            if user.lower() in {"exit", "quit", ""}:
                break
            result = await Runner.run(agent, history + [{"role": "user", "content": user}])
            show_tool_calls(result)
            print(f"Agent: {result.final_output}")
            history = result.to_input_list()  # keep the conversation going


if __name__ == "__main__":
    asyncio.run(main())