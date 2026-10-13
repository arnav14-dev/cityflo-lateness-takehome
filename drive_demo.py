"""
Drive the MCP server the way an agent would: spawn it over stdio, list its tools,
then call them to answer Priya's question. Prints a transcript of the exchange.

Run: python drive_demo.py   (uses the repo's own .venv python for the server)
"""

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "server", "lateness_server.py")


def show(title, result):
    print(f"\n=== {title} ===")
    # MCP tool results carry their payload as JSON text in content blocks.
    blocks = [c.text for c in result.content if getattr(c, "type", None) == "text"]
    for b in blocks:
        try:
            print(json.dumps(json.loads(b), indent=2, default=str))
        except json.JSONDecodeError:
            print(b)


async def main():
    params = StdioServerParameters(command=sys.executable, args=[SERVER])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools exposed by cityflo-lateness:")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description.splitlines()[0]}")

            # 1. The headline question.
            show("worst_routes(3)", await session.call_tool("worst_routes", {"n": 3}))
            # 2. Defend the call we were least sure of.
            show("route_report('R-35')  (the mean trap)", await session.call_tool("route_report", {"route": "R-35"}))
            show("route_report('R-14')  (REC-114 cleared it)", await session.call_tool("route_report", {"route": "R-14"}))
            # 3. Show the cleaning is defensible.
            show("data_quality()", await session.call_tool("data_quality", {}))
            # 4. Separate 'badly run' from 'bad day in the city'.
            show("ops_context()", await session.call_tool("ops_context", {}))


if __name__ == "__main__":
    asyncio.run(main())
