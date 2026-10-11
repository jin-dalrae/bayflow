# BayFlow audit against the original build instruction

Audit date: October 11, 2026. This is a feature-by-feature assessment, not a fabricated completion percentage. "Working" means executable code and recorded verification exist. "Partial" identifies a material simplification or outstanding work.

| Original requirement | Status | Current implementation / remaining gap |
|---|---|---|
| Genuine recursive harness, not dashboard-only | Working | Failure traces → architecture proposal → strict configuration validation → actual simulation reruns → independent gate → accepted/rejected versions. |
| Rules, context, tools, coordination and planning evolve | Working | Schema permits agent/tool sets, topology, context, horizon, frequency, memory and strategy. These affect executable observations and decisions. No generated-code execution. |
| Real LLM mutation planner | Working with fallback | Gemini 3.8 Flash generated v4; actual held-out evaluation promoted it. A later invalid model response triggered a labeled rule-based fallback which was evaluated and rejected. |
| Organizer MongoDB Atlas, official driver, actual read/write | Working | Official PyMongo, ping and write/read probe, persisted runs/frames/traces/versions/proposals/evaluations/deployment decisions, indices and visible counts. User supplied the organizer credential. No substitute cluster was created. |
| Public open-source repository and reproducible README | Working | https://github.com/jin-dalrae/bayflow; MIT software license, ignored credentials, exact launch/test commands. Agency data has separate provider terms. |
| Muni Bus, Muni Metro, BART and Caltrain operations | Working, compact model | All four modes participate in the 21-node/46-directed-edge simulator. Bus operation covers selected route 22 connections; other reference routes are not simulated. |
| Real San Francisco geography | Working after map revision | Leaflet/OpenStreetMap street map with actual agency stop coordinates, pan/zoom, regional bounds, route selection and stop search. Previously the default was a schematic with invented coast background; that did not meet the user's geographic preference. |
| Broad Muni/BART map coverage, including buses | Working reference coverage | Imported GTFS includes 3,238 Muni stop records, 50 BART parent stations, 58 Muni bus routes, 7 tram/Metro routes and 3 cable-car routes. BART has 14 directional/service records, including two bridge-bus records. All trip-referenced shape variants are rendered. These are reference layers, not full-region simulated operations. |
| Authentic 511 regional GTFS | Partial | Optional 511 ZIP importer exists. Current visible broad geometry comes directly from official agency GTFS downloads; no 511 key is needed. The simulator graph is still manually curated, not generated from the regional feed. |
| Current schedules/live feeds | Partial / optional | Download URLs returned snapshots ending August 28 (Muni) and August 30 (BART), 2026. Dates are explicitly visible. No claim of current service; no real-time vehicles imported. |
| BART hourly OD and Muni/Caltrain demand calibration | Missing optional data integration | Passenger demand remains seeded synthetic. No empirical OD calibration or real ridership figures are claimed. |
| Event Surge timeline and three required disruption types | Working | 16:00–23:00, driver shortage, BART delay, Chase 20:45 surge and Oracle 21:30 surge; fictional events. Separate commuter and accident scenarios exist. |
| Lightweight transportation simulation | Working with simplifications | Cohorts, queues, boarding/alighting, segment vehicle capacity, travel, transfers, delayed/canceled trips, limited shared Muni standby vehicles/drivers. Directed segments use independent service calendars, not continuous vehicle blocks or complete agency constraints. |
| Reference-based passenger delay and fixed evaluator | Working | Earliest undisrupted journey reference on the selected path, terminal unserved penalty, frozen objective-v1 weights and feasibility/capacity penalties. |
| Static / fixed-agent / evolving comparisons | Working | Identical scenario/seed three-way measured reruns, plus three preselected held-out seeds and a commuter regression gate. Demo objective 0.305224 fixed → 0.240118 evolved (21.33% lower). Modeled extra cost 810 → 990; missed-transfer rate unchanged; denied boarding count worsened. Benefits are not claimed for every metric. |
| Independent promotion gate and failed-candidate rejection | Working | ≥2% held-out improvement, no feasibility/capacity violations, ≤5% commuter regression. Rejection retains the incumbent. Evaluator cannot be mutated by planner. |
| Repeated loop, version history and rollback | Working | Two iterations per default evolution; persisted history, active pointer and rollback only to accepted versions. Reused held-out suite is a hackathon limitation, not proof of out-of-sample generalization indefinitely. |
| Living simulation, topology and mutation inspector | Working | Backend-generated frames, geographic moving vehicles/queues/events, active agents/tools/policies, progress history, actual proposal rationale, before/after metrics, audit history and rollback. |
| Full functional API and long-job state | Working | Health/network/scenarios/runs/frames/jobs/current/versions/proposals/evaluations/evolve/rollback/database status. UI actions call backend. |
| Tests and no secrets in source | Working | Determinism, conservation, occupancy/resource limits, disruptions, executable mutation, invalid schemas, rejection, API, Atlas write/read and model integration checks. Live browser checks include geographic tiles and reference network. |
| Submission materials | Prepared, human submission remains | README/architecture, three-minute script, one-minute narration/screen checklist, FAQ, evidence artifacts. No recorded video, uploaded submission or hosted deployment is claimed. |
| What was built during hackathon | Documented | New code for simulation, agents, recursive engine, persistence, UI, tests and docs. Standard libraries and agency datasets are attributed, not claimed as original work. |

## Highest-value remaining work

1. Obtain fresher GTFS feeds or a 511 key; preserve calendar dates and verify actual service validity.
2. Generate the operational graph and timetables from GTFS rather than only drawing reference geography.
3. Calibrate synthetic demand against BART OD/SFMTA ridership and test new held-out disruptions.
4. Add selected operational corridors incrementally; rendering 3,288 reference stops does not establish full-region optimization.
5. Record the submission video and submit before the deadline.

The core recursive-harness acceptance test is met by actual Gemini-plus-Atlas evidence in evaluation-gemini-atlas.json. The prototype's major remaining limitation is realism/coverage of the operational simulation, not whether the evolution loop exists.
