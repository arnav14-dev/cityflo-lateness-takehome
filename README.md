# Cityflo ops lateness — AI Engineer take-home

An MCP server that answers one ops question from the week's GPS export:
**which routes were actually late this week, by how much, and which three were worst** —
as a verdict that survives people motivated to poke holes in it.

- **[`DECISION.md`](DECISION.md)** — Priya's deliverable: the verdict, the worst-three, and every
  consequential call (rule / the case it breaks on / the cost and who pays / what would change my mind).
  **Read this first — it is the assignment.**
- **[`decisions.jsonl`](decisions.jsonl)** — the steering ledger (one line per load-bearing decision,
  with the verbatim message and a transcript anchor).
- `server/core.py` — the cleaning + metric logic (pure Python, re-runnable on next week's export).
- `server/lateness_server.py` — the MCP server (5 tools) wrapping core.
- `drive_demo.py` — drives the server over stdio the way an agent does; `drive_demo_output.txt` is its
  captured run (the exact tool calls behind DECISION.md).
- `data/` — the provided export (`trips.csv`, `schedule_v2.csv`, `ops_log.txt`).

## The answer (headline)

Worst three, **chronic**: **R-33** (+5 min typ., 47% of trips >5 min late), **R-27** (+5 min, 47%,
and the biggest total delay burden), **R-26** (+4 min, 43%). **R-35 is deliberately excluded** — by
mean it's the worst route in the network, but all 19 of its bad trips are one flooded Wednesday; it
goes on the refund watch, not the depot-head scorecard. Full reasoning in `DECISION.md`.

## Run it

```bash
python3 -m venv .venv
./.venv/bin/pip install "mcp>=2,<3"

# drive the server end-to-end (spawns it over stdio, calls the tools, prints the answer)
./.venv/bin/python drive_demo.py
```

Point it at next week's export without touching code:

```bash
CITYFLO_TRIPS=/path/trips.csv CITYFLO_SCHEDULE=/path/schedule_v2.csv \
CITYFLO_OPSLOG=/path/ops_log.txt ./.venv/bin/python drive_demo.py
```

### Wire into an MCP client (e.g. Claude Code / Claude Desktop)

```json
{
  "mcpServers": {
    "cityflo-lateness": {
      "command": "/abs/path/.venv/bin/python",
      "args": ["/abs/path/server/lateness_server.py"]
    }
  }
}
```

## The tools

| tool | what it answers |
|------|-----------------|
| `worst_routes(n=3)` | the headline: worst-n chronic routes + any event-flagged routes held out |
| `rank_table()` | one verdict per route, worst first |
| `route_report(route)` | defend/attack one route: median/mean/p90, peak median, per-day medians, REC-114 flag |
| `data_quality()` | every row dropped or corrected, by id/count, and why |
| `ops_context()` | the week's ops notes as neutral categories only (weather/crowd/driver-ops/vehicle) |

## What's deliberately encoded (the calls)

- **Baseline:** lateness vs the **timetable**, with REC-114 revised runtimes applied to R-14/R-27.
- **Verdict:** **median** lateness; ranked by **share of trips >5 min late** — not the mean.
- **Cleaning:** drop unparseable timestamps and arrival-before-departure rows; tz-correct to IST first.
- **Events vs chronic:** a route whose heavy delays are ≥80% on one day is an event (R-35 = flooded Wed),
  reported separately, not ranked.
- **Privacy (REC-114 directive a):** no phone numbers or verbatim complaint text in any output; ops notes
  categorized; everything referenced by id.

Framework/polish is not the point — the judgment in `DECISION.md` is. The server is deliberately small.
