"""
Core lateness logic for the Cityflo ops take-home.

Pure Python, no MCP dependency, so it can be imported, unit-tested, and re-run on
next week's export unchanged. The MCP server (lateness_server.py) is a thin wrapper
over these functions.

The rules encoded here are the committed calls from DECISION.md:

  Baseline   : timetable. late = (actual_arrival - scheduled_departure) - scheduled_runtime,
               with scheduled_runtime overridden by schedule_v2 (REC-114) for the routes it lists.
  Verdict    : median lateness per route (robust to a single bad day).
  Ranking    : share of trips more than LATE_THRESHOLD_MIN late, tiebreak median.
  Cleaning   : drop unparseable timestamps; normalise arrival to IST via tz_offset;
               drop physically impossible trips (arrival before departure).
  Events     : a route whose heavy-late trips collapse onto a single calendar day is
               flagged event-driven and held out of the chronic worst-three.
  Privacy    : REC-114 directive (a) -- no phone numbers or verbatim complaint text is
               ever emitted; ops context is returned as categories only.
"""

from __future__ import annotations

import csv
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# ----- tunable constants (stated so a stranger can re-run and get the same answer) -----
IST_OFFSET_MIN = 330           # +05:30
LATE_THRESHOLD_MIN = 5         # a trip "felt late" to a rider past this
HEAVY_LATE_MIN = 20            # a trip that hurt (refund/ratings territory)
EVENT_DAY_CONCENTRATION = 0.80 # >=80% of a route's heavy-late trips on one day => event, not chronic
MIN_TRIPS_FOR_RANK = 30        # routes with fewer clean trips are reported but not ranked
DT_FMT = "%Y-%m-%d %H:%M"

_PHONE_RE = re.compile(r"(?:\+?\d[\d\-\s]{7,}\d)")


def _parse_dt(s: str):
    try:
        return datetime.strptime(s.strip(), DT_FMT)
    except (ValueError, AttributeError):
        return None


def _parse_offset_min(s: str):
    s = (s or "").strip()
    m = re.fullmatch(r"([+-])(\d{2}):(\d{2})", s)
    if not m:
        return None
    sign = 1 if m.group(1) == "+" else -1
    return sign * (int(m.group(2)) * 60 + int(m.group(3)))


def redact(text: str) -> str:
    """Enforce REC-114 directive (a): never emit phone numbers or raw complaint text."""
    return _PHONE_RE.sub("[redacted-phone]", text or "")


def _is_peak(hour: int) -> bool:
    # Mumbai home<->office commute windows.
    return (6 <= hour <= 11) or (17 <= hour <= 21)


@dataclass
class Trip:
    trip_id: str
    route: str
    dep: datetime
    arr_ist: datetime
    runtime_min: float
    scheduled_runtime_min: int   # the baseline actually used (REC-114 applied)
    scheduled_runtime_raw: int   # what the export shipped
    lateness_min: float
    day: str                     # e.g. "Wed 2026-08-05"


@dataclass
class DataQuality:
    rows_total: int = 0
    dropped_unparseable: int = 0
    dropped_arrival_before_departure: list = field(default_factory=list)
    tz_corrected: list = field(default_factory=list)
    rec114_routes: dict = field(default_factory=dict)
    clean_rows: int = 0


def load_schedule_v2(path: str) -> dict:
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            out[r["route"].strip()] = int(r["revised_runtime_min"])
    return out


def load_trips(trips_path: str, schedule_v2_path: str):
    """Return (list[Trip], DataQuality). This is the single cleaning pipeline."""
    revised = load_schedule_v2(schedule_v2_path)
    dq = DataQuality(rec114_routes=dict(revised))
    trips: list[Trip] = []

    with open(trips_path, newline="") as f:
        for r in csv.DictReader(f):
            dq.rows_total += 1
            dep = _parse_dt(r["scheduled_departure"])
            arr = _parse_dt(r["actual_arrival"])
            if dep is None or arr is None:
                dq.dropped_unparseable += 1
                continue

            off = _parse_offset_min(r["tz_offset"])
            if off is None:
                off = IST_OFFSET_MIN  # unreadable offset: assume the fleet default
            if off != IST_OFFSET_MIN:
                arr = arr + timedelta(minutes=(IST_OFFSET_MIN - off))
                dq.tz_corrected.append(r["trip_id"])

            runtime = (arr - dep).total_seconds() / 60.0
            if runtime < 0:
                # Arrival stamped before scheduled departure: physically impossible, drop.
                dq.dropped_arrival_before_departure.append(r["trip_id"])
                continue

            raw_srt = int(r["scheduled_runtime_min"])
            srt = revised.get(r["route"].strip(), raw_srt)  # REC-114 override
            trips.append(Trip(
                trip_id=r["trip_id"],
                route=r["route"].strip(),
                dep=dep,
                arr_ist=arr,
                runtime_min=runtime,
                scheduled_runtime_min=srt,
                scheduled_runtime_raw=raw_srt,
                lateness_min=runtime - srt,
                day=dep.strftime("%a %Y-%m-%d"),
            ))

    dq.clean_rows = len(trips)
    return trips, dq


def _percentile(sorted_vals, p):
    if not sorted_vals:
        return float("nan")
    idx = min(len(sorted_vals) - 1, int(len(sorted_vals) * p))
    return sorted_vals[idx]


def route_metrics(trips: list[Trip]) -> dict:
    """Per-route verdict and the diagnostics needed to defend it."""
    by_route: dict[str, list[Trip]] = {}
    for t in trips:
        by_route.setdefault(t.route, []).append(t)

    out = {}
    for route, ts in by_route.items():
        lat = sorted(t.lateness_min for t in ts)
        peak = sorted(t.lateness_min for t in ts if _is_peak(t.dep.hour))
        heavy = [t for t in ts if t.lateness_min > HEAVY_LATE_MIN]

        # Which day owns this route's heavy-late trips?
        heavy_by_day: dict[str, int] = {}
        for t in heavy:
            heavy_by_day[t.day] = heavy_by_day.get(t.day, 0) + 1
        worst_day, worst_day_ct = (None, 0)
        if heavy_by_day:
            worst_day, worst_day_ct = max(heavy_by_day.items(), key=lambda kv: kv[1])
        concentration = (worst_day_ct / len(heavy)) if heavy else 0.0
        event_driven = (len(heavy) >= 5 and concentration >= EVENT_DAY_CONCENTRATION)

        out[route] = {
            "route": route,
            "trips": len(ts),
            "median_lateness_min": round(statistics.median(lat), 2),
            "mean_lateness_min": round(statistics.mean(lat), 2),
            "p90_lateness_min": round(_percentile(lat, 0.90), 1),
            "peak_median_lateness_min": round(statistics.median(peak), 2) if peak else None,
            "share_gt5_pct": round(100 * sum(1 for x in lat if x > LATE_THRESHOLD_MIN) / len(lat), 1),
            "heavy_late_trips": len(heavy),
            "event_driven": event_driven,
            "event_day": worst_day if event_driven else None,
            "event_day_share": round(concentration, 2) if event_driven else None,
            "rec114_applied": route in {t.route for t in ts if t.scheduled_runtime_min != t.scheduled_runtime_raw},
        }
    return out


def verdict_for_route(metrics_row: dict) -> str:
    m = metrics_row
    if m["event_driven"]:
        return (f"NOT chronically late. Typical trip {m['median_lateness_min']:+.0f} min; "
                f"its {m['heavy_late_trips']} heavy delays are concentrated on {m['event_day']} "
                f"({int(m['event_day_share']*100)}% same day) -- an event, not the route.")
    med = m["median_lateness_min"]
    if med >= 5:
        sev = "chronically late"
    elif med >= 3:
        sev = "routinely slipping"
    else:
        sev = "broadly on time"
    return (f"{sev.capitalize()}: typical trip {med:+.0f} min, "
            f"{m['share_gt5_pct']:.0f}% of trips over {LATE_THRESHOLD_MIN} min late.")


def rank_routes(metrics: dict):
    """Return (chronic_ranked, event_flagged). Chronic ranking = share>5min desc, tiebreak median."""
    rankable = [m for m in metrics.values() if m["trips"] >= MIN_TRIPS_FOR_RANK]
    chronic = [m for m in rankable if not m["event_driven"]]
    events = [m for m in rankable if m["event_driven"]]
    chronic.sort(key=lambda m: (m["share_gt5_pct"], m["median_lateness_min"]), reverse=True)
    events.sort(key=lambda m: m["heavy_late_trips"], reverse=True)
    return chronic, events


def analyze(trips_path: str, schedule_v2_path: str):
    trips, dq = load_trips(trips_path, schedule_v2_path)
    metrics = route_metrics(trips)
    chronic, events = rank_routes(metrics)
    return trips, dq, metrics, chronic, events
