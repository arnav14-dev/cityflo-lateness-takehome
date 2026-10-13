"""
Cityflo ops lateness MCP server.

A small MCP server Priya's agent drives to answer one question:
  which routes were actually late this week, by how much, and which three were worst.

It is a thin wrapper over core.py (all the judgment lives there and in DECISION.md).
Run: python server/lateness_server.py   (stdio transport)

Data paths default to ../data next to this file; override with
CITYFLO_TRIPS / CITYFLO_SCHEDULE / CITYFLO_OPSLOG env vars so the same server
runs against next week's export without code changes.
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

import core

ROOT = Path(__file__).resolve().parent.parent / "data"
TRIPS = os.environ.get("CITYFLO_TRIPS", str(ROOT / "trips.csv"))
SCHEDULE = os.environ.get("CITYFLO_SCHEDULE", str(ROOT / "schedule_v2.csv"))
OPSLOG = os.environ.get("CITYFLO_OPSLOG", str(ROOT / "ops_log.txt"))

mcp = MCPServer(
    name="cityflo-lateness",
    instructions=(
        "Answers 'which routes were actually late this week' from the GPS export. "
        "Lateness is measured against the timetable (REC-114 revised runtimes applied), "
        "the per-route verdict is the MEDIAN (robust to a single bad day), and routes whose "
        "heavy delays collapse onto one calendar day are flagged as events, not chronic offenders. "
        "Start with worst_routes; use route_report to defend any single route; data_quality "
        "explains every row that was dropped or corrected. No phone numbers or verbatim complaint "
        "text is ever returned (REC-114 directive a)."
    ),
)


def _load():
    return core.analyze(TRIPS, SCHEDULE)


@mcp.tool()
def worst_routes(n: int = 3) -> dict:
    """The headline answer: the worst `n` chronically-late routes (ranked), plus any routes
    held out because their lateness was a one-day event. Each route comes with a plain-English
    verdict Priya can read into the review."""
    _, _, _, chronic, events = _load()
    return {
        "measure": "median lateness vs timetable; ranked by share of trips >5 min late",
        "worst_chronic": [
            {
                "rank": i + 1,
                "route": m["route"],
                "verdict": core.verdict_for_route(m),
                "median_lateness_min": m["median_lateness_min"],
                "share_gt5_pct": m["share_gt5_pct"],
                "trips": m["trips"],
            }
            for i, m in enumerate(chronic[:n])
        ],
        "event_flagged_not_counted": [
            {"route": m["route"], "verdict": core.verdict_for_route(m), "event_day": m["event_day"]}
            for m in events
        ],
    }


@mcp.tool()
def rank_table() -> list:
    """One verdict per route for every route, worst first (chronic routes ranked, then event
    routes, then the rest). This is the table Priya pastes into the Friday review."""
    _, _, metrics, chronic, events = _load()
    ranked = chronic + events
    seen = {m["route"] for m in ranked}
    rest = sorted(
        (m for m in metrics.values() if m["route"] not in seen),
        key=lambda m: (m["share_gt5_pct"], m["median_lateness_min"]),
        reverse=True,
    )
    rows = []
    for m in ranked + rest:
        rows.append({
            "route": m["route"],
            "verdict": core.verdict_for_route(m),
            "median_min": m["median_lateness_min"],
            "share_gt5_pct": m["share_gt5_pct"],
            "trips": m["trips"],
            "event_driven": m["event_driven"],
        })
    return rows


@mcp.tool()
def route_report(route: str) -> dict:
    """Everything needed to defend (or attack) one route: median/mean/p90, peak-window median,
    share of trips late, the day its heavy delays fall on, and whether REC-114 changed its
    baseline. Use this when the review pulls on a specific route."""
    trips, _, metrics, _, _ = _load()
    key = route.strip().upper()
    if key not in metrics:
        return {"error": f"route {key!r} not found", "known_routes": sorted(metrics)}
    m = dict(metrics[key])
    # per-day median so a reviewer can see where the lateness lives
    by_day: dict[str, list[float]] = {}
    for t in trips:
        if t.route == key:
            by_day.setdefault(t.day, []).append(t.lateness_min)
    import statistics
    m["verdict"] = core.verdict_for_route(m)
    m["per_day_median_min"] = {
        d: round(statistics.median(v), 1) for d, v in sorted(by_day.items())
    }
    return m


@mcp.tool()
def data_quality() -> dict:
    """What the cleaning did and why -- so the numbers survive someone poking at the raw file.
    Every dropped or corrected row is accounted for by trip id or count."""
    _, dq, _, _, _ = _load()
    return {
        "rows_total": dq.rows_total,
        "clean_rows": dq.clean_rows,
        "dropped_unparseable_timestamp": dq.dropped_unparseable,
        "dropped_arrival_before_departure": dq.dropped_arrival_before_departure,
        "tz_corrected_to_ist": dq.tz_corrected,
        "rec114_revised_runtimes_applied": dq.rec114_routes,
        "note": (
            "Arrival normalised to IST using each device's tz_offset before anything else; "
            "arrival-before-departure rows are physically impossible and removed, not clamped."
        ),
    }


@mcp.tool()
def ops_context() -> list:
    """Operational events from the week, as neutral categories only (weather, crowd, driver-ops).
    Honors REC-114 directive (a): no phone numbers or verbatim complaint text. Use this to separate
    'the route is badly run' from 'the city had a bad day'."""
    cats = [
        ("weather", ["waterlog", "rain", "flood"]),
        ("crowd_event", ["crowd", "festival", "surge"]),
        ("driver_ops", ["driver", "swap", "no-show", "yard", "depot"]),
        ("vehicle", ["ac", "breakdown", "vehicle"]),
    ]
    out = []
    try:
        for line in Path(OPSLOG).read_text().splitlines():
            line = core.redact(line.strip())
            if not line:
                continue
            low = line.lower()
            tags = [name for name, kws in cats if any(k in low for k in kws)]
            out.append({"note": line, "categories": tags or ["other"]})
    except FileNotFoundError:
        return [{"error": "ops log not found"}]
    return out


if __name__ == "__main__":
    mcp.run()
