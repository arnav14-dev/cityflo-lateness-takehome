# Route lateness — week of 2026-08-03 → 08-09

**For:** Priya, Ops Lead (Mumbai North) · **For the Friday regional review**
**One line:** Three routes are chronically late and should be flagged. R-35 looks worst on a
naive average but isn't — it had one flooded day, and flagging it would cost you a depot head for
an act of God.

---

## The verdict

**Worst three (chronic, ranked):**

| # | Route | Typical trip | Riders >5 min late | What it is |
|---|-------|-------------|--------------------|------------|
| 1 | **R-33** | **+5 min** | **47% of trips** | Chronically late. Consistent, every day — no single day carries it. |
| 2 | **R-27** | **+5 min** | **47% of trips** | Chronically late, and the biggest total delay burden: 852 rider-late-minutes this week. |
| 3 | **R-26** | **+4 min** | **43% of trips** | Routinely slipping. Edges R-37 for the third slot (see borderline call below). |

**Held out of the ranking on purpose:** **R-35.** By simple average it's the worst route in the
network (+8.05 min). It is not a late route — all 19 of its bad trips are on **Wednesday 08-05**
(waterlogging + festival). Six other days its typical trip is **+1 min**. It belongs on the refund
watch, not the depot-head scorecard. Detail in Call 5.

One verdict per route for all 40 routes: run the `rank_table` tool (top of the list is above;
full table is what the server prints).

---

## The consequential calls

Each call below is stated as a **rule** (re-runnable on next week's data), the **case it breaks
on**, the **cost and who pays**, and **what would change my mind**. These are the calls the review
will pull at.

### Call 1 — "Late" is measured against the timetable, not the route's own usual time

- **Rule:** `lateness = (actual_arrival − scheduled_departure) − scheduled_runtime`, where
  `scheduled_runtime` is the published timetable (REC-114 revised runtimes applied — Call 3).
  We only have `actual_arrival`, so this is arrival-vs-promise; it folds any departure delay into
  the number, which is correct — the rider feels total lateness, not its cause.
- **Breaks on:** a route with a genuinely too-tight timetable looks "late" even when the crew drives
  it as fast as is safe. If R-27's 45-min schedule is physically undrivable at peak, this rule still
  books it as late. I keep the rule because the review, the depot incentive, and the rider's
  expectation are all set against the *published* time — measuring a route against its own slow self
  would hide exactly the routes that disappoint riders.
- **Cost / who pays:** if a schedule is the real problem, the depot head wears a planning failure.
  Mitigation: Call 1's number plus the timetable-review flag, not a crew penalty.
- **Changes my mind:** evidence that a worst-three route is at its safe physical floor at peak
  (e.g. GPS speed at the road limit the whole run) — then it's a scheduling fix, not a lateness flag.

### Call 2 — The verdict is the median + share of trips >5 min late, never the mean

- **Rule:** per route, report **median lateness** as the verdict and rank by the **share of trips
  more than 5 minutes late** (tiebreak: median). The mean is reported only for contrast.
- **Breaks on:** **R-35.** Mean = +8.05 min (worst in the network); median = +2 min (unremarkable).
  The mean is one flooded Wednesday; the median is the truth about the route. A pure-median view
  also *under*-weights a route that is reliably 4–5 min late but never spikes — which is why I add
  "share >5 min late" so chronic-but-undramatic routes (R-33, R-26) still surface.
- **Cost / who pays:** rank on the mean and you flag R-35 and clear a route like R-26 that quietly
  makes **44 trips/week** late — the refund queue and app-store rating keep bleeding on the route you
  cleared, while a depot head loses his incentive over weather.
- **Changes my mind:** if a route's lateness were roughly symmetric and spike-free, mean ≈ median and
  the choice stops mattering. It isn't, here.

### Call 3 — REC-114 revised runtimes are applied (R-14, R-27)

- **Rule:** for routes listed in `schedule_v2.csv`, use `revised_runtime_min` as the baseline instead
  of the export's `scheduled_runtime_min`. Signed off, and it keeps the numbers consistent with what
  the review already has. (The handoff calls this the "4xx series"; in this export each route maps 1:1
  to its vehicle series, and the only routes `schedule_v2` actually reconciles are R-14 and R-27.)
- **Breaks on / why it matters most:** **R-14.** On the raw export runtime it is the **#1 worst route
  in the network** (mean +8.07 min). Apply REC-114 (53-min runtime) and it is **broadly on time**
  (median 0, mean +0.32). Honoring the directive single-handedly moves R-14 from "worst in the city"
  to "fine." (R-27 is listed "no change" at 45 min — it stays chronically late on its own merits.)
- **Cost / who pays:** *not* applying REC-114 flags R-14's depot head as the worst in the region over
  a reconciliation that was already signed off — the precise "flag a route that wasn't really late and
  lose the depot head" failure in your handoff.
- **Changes my mind:** if REC-114 were rescinded or its effective date (2026-08-05) fell mid-week such
  that only part of the week should use the revised runtime. It's effective before the window, so the
  whole week uses it.

### Call 4 — Cleaning: drop the impossible, correct the knowable, keep the rest

- **Rule:** (a) drop rows whose timestamps don't parse (**24**); (b) normalize every `actual_arrival`
  to IST using its device `tz_offset` *before* computing anything (**1 row**, T1-02864, stamped
  `+00:00`); (c) drop rows where corrected arrival is still **before** scheduled departure (**18**) —
  physically impossible, not a late trip. 5,250 of 5,292 rows survive (99.2%). Full ledger: the
  `data_quality` tool.
- **Breaks on:** T1-02864 (R-23) — raw, it reads −332 min (arrival "before" departure by 5+ hours);
  the `+00:00` offset says the device clock was in UTC, so corrected it's a normal +48-min run. I
  *correct* it rather than drop it, because the offset column tells us exactly how. If an offset were
  missing instead of wrong, I assume the fleet default (+05:30) and let the impossible-runtime filter
  catch anything that implies.
- **Cost / who pays:** clamping negatives to zero (instead of dropping) would silently credit 18
  broken rows as "on time" and flatter every route they touch; keeping the −332 row would wreck R-23's
  mean. Dropping 0.8% of rows costs us almost no coverage and buys numbers that survive scrutiny.
- **Changes my mind:** if the 24 unparseable rows clustered on one route or one depot, they'd be a
  signal (a bad device fleet), not noise — I'd investigate before dropping. They don't; they're scattered.

### Call 5 — R-35 is a one-day event, reported separately, not in the worst-three

- **Rule:** a route is **event-driven** (held out of the chronic ranking) when it has ≥5 heavy-late
  trips (>20 min) **and ≥80% of them fall on a single calendar day.** R-35: 19 heavy trips, **100% on
  Wed 08-05.** Its per-day median that day is **52 min**; every other day is **0–2 min**.
- **Breaks on:** this rule would also excuse a route that is genuinely collapsing *if* the collapse
  happens to land on one day. I keep it because `ops_log` independently corroborates Wed 08-05
  (SV Road waterlogged, western corridor diverted ~35 min AM; festival surge PM) — the cause is the
  city, not the route. If there were no corroborating event, I'd treat a one-day spike as a route
  problem to investigate, not an exception to grant.
- **Cost / who pays — both sides, split on purpose:**
  - Put R-35 in the worst-three and its depot head loses his on-time incentive for a flood. That's the
    error you flagged: *"if I flag a route that wasn't really late… I lose the depot head."*
  - Ignore Wednesday entirely and the **975 rider-late-minutes** on R-35 that day — riders who stood in
    the rain for ~52 min — go unowned, and the refund queue and ratings eat it.
  - So: **R-35 off the incentive scorecard, onto the Wed refund/ratings watch.** Two different owners,
    two different costs.
- **Changes my mind:** if R-35 spiked again next week with no ops_log event behind it, the "one bad day"
  story is dead and it's a chronic flag.

### Call 6 — The borderline third slot: R-26 over R-37

- **Rule:** third place goes to the higher share-of-trips->5-min-late. R-26 = **42.7%**, R-37 = **40.0%**
  — both median +4 min, both ~104 trips. R-26 takes it by 2.7 points.
- **Breaks on:** this is the softest call in the memo. 2.7 points is ~3 trips; a different week flips it.
  I would not die on R-26-vs-R-37 — I'd tell the review "the third-worst is R-26, with R-37 a hair
  behind and functionally its twin," and treat any fix as applying to both.
- **Cost / who pays:** naming only R-26 lets R-37's depot head off a near-identical problem. Cheap
  insurance: flag both as the joint third.
- **Changes my mind:** basically anything — one more bad day on R-37, or a week of data, reorders them.
  This is the call I'm least sure of and the one I'd re-check first.

---

## Privacy (REC-114 directive a)

No rider phone numbers or verbatim complaint text appear in any tool output, trace, or this memo.
The `ops_context` tool returns ops notes as neutral categories (weather / crowd_event / driver_ops /
vehicle) and runs a phone-number redactor over every line before emitting it. Routes and trips are
referenced by id only.

## The tool

Five MCP tools drive this, over the week's export: `worst_routes` (the headline), `rank_table`
(verdict per route), `route_report` (defend one route — median/mean/p90/per-day), `data_quality`
(every dropped/corrected row), `ops_context` (redacted event categories). Run instructions in
`README.md`; the exact calls that produced this memo are in `drive_demo_output.txt`.
