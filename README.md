# BayFlow

**An AI transit operations system that learns to redesign how it manages a city.**

Public source: [jin-dalrae/bayflow](https://github.com/jin-dalrae/bayflow).

BayFlow is an experimental recursive agent harness for San Francisco transit. Its city experiment runs synthetic commutes over imported GTFS stop connections; the original compact corridor remains available for Event Surge demonstrations. Operational agents respond to measured queues and disruptions. A mutation planner diagnoses their failures, changes validated architecture, policy parameters, or declarative rules, reruns the candidate, and independently promotes or rejects it.

The technical contribution is the executable architecture evolution loop. The React interface makes that loop inspectable through a transit replay, agent topology, configuration changes, and recorded decisions.

## The thesis: preserve the journey, change how the city serves it

A commuter starts with an origin, a destination, a departure time, and an expected arrival. BayFlow's next experiment asks: **can coordinated service changes and voluntary route suggestions reduce crowding while helping more people board within ten minutes and arrive within ten minutes of their original ETA?**

The supply side can place limited standby vehicles where queues need them and adjust modeled service frequency within a fixed resource budget. The demand side can suggest a less crowded valid route to a willing passenger. A suggestion must preserve the destination and predict arrival no more than ten minutes later than the original ETA. A passenger may decline; the system cannot force their route or redefine their deadline after they accept. Crowding labels are model indicators, not real safety alerts.

The recursive part changes how the agents make those choices: which agents/tools they use, which stops and neighboring services they can observe, how far they plan ahead, and how often they reconsider. A fixed agent might repeatedly add a bus to the longest queue. An evolving harness can test a different coordination/context policy that considers downstream transfers and passenger alternatives, then retain it only if the measured journeys improve.

**Implemented City Commute:** 3,292 nodes and 8,369 directed transit/walking edges, using actual GTFS stop sequences and service variants plus the selected derived Caltrain connector. A measured baseline exercises all 82 imported agency service records, including all 58 Muni bus routes. Demand, segment calendars, speeds, capacities, queue areas, consent, and resources remain synthetic. The one-minute simulator executes provider service changes, voluntary alternatives, and typed rules with passenger/queue/vehicle accounting. Its completed three-iteration offline evolution generated distinct hypotheses, executed and rejected all three, and retained v1; no qualifying city improvement is claimed. Real Gemini-plus-Atlas evidence below is historical Event Surge evidence, not proof of the new city run.

The full hypothesis, manipulation limits, measurement definitions, and test plan are in [the experiment thesis](demo/THESIS.md). The two ten-minute targets are the current interpretation of the commuter goal; they are explicit experiment parameters, not a claim that all real journeys can meet them.

## What counts as success in the City Commute experiment

The city evaluator separates three outcomes: whether passengers start their **first bus/rail ride within ten minutes** of departure; whether they arrive by their **original ETA plus ten minutes**; and how many passenger-minutes they spend queuing at modeled crowded stops. Walking does not count as first boarding. The original ETA is frozen before any intervention; accepting a different path does not reset it. Final rates divide by all generated passengers, including unserved passengers as failed targets. Playback distinguishes progress/observed outcomes from the final all-passenger rates.

Crowding uses a transparent model: queue length divided by an assumed stop queue area (bus 25 m², Metro 180 m², BART 400 m²). A density above 1.5 persons/m² triggers modeled crowding exposure. These areas and the threshold are synthetic assumptions, **not surveyed platform dimensions or a safety standard**. Global exposure and queue peaks must be inspected together: moving people to a different crowded stop does not establish success.

The City Commute objective is a separately predefined `city-intent-v2` experiment; it does not replace or retrospectively alter the existing `objective-v1` results:

```text
J_city = 0.35 × (1 − fraction first boarding within 10 minutes)
       + 0.35 × (1 − fraction arriving by original ETA + 10 minutes)
       + 0.20 × (crowding exposure passenger-minutes / (generated × 30))
       + 0.10 × (max(0, net additional operating cost) / 20,000)
       + 1,000 × unsafe or infeasible violations
```

The city candidate cannot change scoring weights, demand, deadline, compliance, density assumptions, or resource limits. Before a paired experiment, select `demand_scale` (default 1.0, range 0.25–3.0) and `advisory_acceptance_rate` (default 0.6, range 0–1). These request parameters remain identical across baseline and candidate runs. The fixed standby pool is 12 Muni bus, four Muni Metro, two BART, and one Caltrain vehicle/driver pairs, with a gross supplemental-service budget of **12,000 model cost units**, not dollars. An early development candidate improved journey metrics but overspent and worsened the objective; that finding motivated the fixed budget before the new benchmark. No candidate may expand it or change the frozen weights.

### Architecture, controller policies, and operating rules

Mutations can change agent/tool/context configuration, bounded numerical policies, and up to 12 typed operating rules. A rule contains a stable ID, operator scope, signal, comparison, threshold, action, and priority. Signals are queue/capacity ratio, oldest wait, incoming transfer riders, and time since an unboarded intent began. Supported actions are standby dispatch, transfer boarding priority, and a connection hold of at most five minutes. Rule actions require their tools; incoming-transfer rules require shared context. Unknown keys, arbitrary code, duplicate IDs, incompatible tools, and out-of-bounds values are rejected.

Incoming-transfer forecasts project already-moving riders through explicit walking-transfer edges between platforms, then test whether they can reach the departing service in time. A hold postpones one existing departure; it creates no vehicle or capacity. Actual evaluation counts delayed riders as well as helped transfers. Telemetry records rule evaluations, triggers, executed holds/dispatches, hold minutes, and affected riders. Diagnosis ranks actual denied-boardings and transfer waits by edge/operator, with queue-observation deduplication separate from real cohort denial counts. A small two-minute hold is a testable hypothesis, not a preselected winner.

Rule thresholds are bounded to 0–1,000, priority to 0–10, operator scopes to the four modeled transit types, and hold duration to 1–5 minutes. Examples of mutable policy bounds are urgent wait 3–15 minutes, upstream lookahead 0–60 minutes, advisory ETA allowance 0–10 minutes, regional dispatch pressure 0.1–3.0, and low-load hold fraction 0–0.3. Original journey deadlines remain immutable even if a policy adopts a stricter advice allowance. A typed candidate rule can look like this:

```json
{
  "id": "incoming_transfer_hold",
  "description": "Test a short wait for incoming transfer riders",
  "signal": "incoming_transfer_riders",
  "comparator": ">=",
  "threshold": 1,
  "scope_operators": ["Muni Bus"],
  "action": "hold_for_transfer",
  "max_hold_minutes": 2,
  "priority": 1,
  "enabled": true
}
```

This requires the `transfer_optimizer` tool and nonlocal context. It defers **one directed segment departure**; downstream segment calendars stay fixed, so riders can miss a later leg. The model does not shift a physical vehicle's entire schedule. That is a plausible timing tradeoff to investigate after the measured hold rejection, not a verified causal explanation of its score.

The planner receives configuration diffs, accept/reject reasons, and persistent lessons within its memory window. Gemini is asked for focused typed changes, receives a 16,384-token output limit, and can repair an invalid structured response once using redacted validation feedback. Actual attempts, errors, provider/model, and token usage are audited; unsuccessful generation still produces a visibly labeled fallback.

## Run locally

Requirements: Python 3.11+, Node.js 20+, npm, and the **organizer-provided MongoDB Atlas Sandbox URI**. Do not substitute a personal or newly created cluster for the official demo.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Edit .env locally; never commit credentials.
cd frontend
npm install
cd ..
```

Set `MONGODB_URI` to the official Sandbox connection string. `MONGODB_DB` defaults to `bayflow`. The model planner supports Gemini through Google's official `google-genai` SDK and Anthropic through its official SDK. The default configuration is `LLM_PROVIDER=gemini`, `GEMINI_API_KEY`, and `GEMINI_MODEL=gemini-3.8-flash`; `GOOGLE_API_KEY` is accepted as an alias. For Anthropic, set `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, and `ANTHROPIC_MODEL`. A missing key, provider failure, or invalid response triggers the visibly labeled rule-based planner, with its actual fallback reason recorded. `TRANSIT_511_API_KEY` is only needed for the optional GTFS importer.

Gemini generation uses JSON Schema structured output, followed by application validation; see [Google's structured-output documentation](https://ai.google.dev/gemini-api/docs/generate-content/structured-output). A **real Gemini 3.8 Flash proposal call passed** the opt-in model test and produced a validated candidate. [Its preserved artifact](demo/model-verification.json) records `planner.kind=llm`, provider/model, 8,852 input tokens, 659 output tokens, and 1,566 thinking tokens. This proves model-driven proposal generation; candidate improvement still requires a separate measured simulation evaluation. The optional Anthropic credential encountered an insufficient-credit error during verification, so it is not used as evidence of successful model planning.

A subsequent **real Gemini-plus-Atlas evolution run** proposed and promoted v4 with **22.23% lower mean promotion-suite objective**. Its proposal metadata confirms Gemini `gemini-3.8-flash`; the decision and before/after evaluations were read back through the persisted proposal-history endpoint. On iteration two, Gemini's response failed strict Pydantic validation, so the explicitly labeled rule-based fallback proposed v5. Its objective worsened **14.26%**, and the gate rejected it, retaining v4. [The complete actual artifact](demo/evaluation-gemini-atlas.json) includes job history/results, persisted proposal readback, and verified database state. This establishes model-driven mutation, executable candidate evaluation, automatic promotion/rejection, schema enforcement, and actual Sandbox auditability together; it does not claim two valid LLM proposals.

After configuring `.env`, the single launcher verifies actual Atlas ping/read/write, seeds the database, and starts both services:

```bash
bash scripts/start.sh
```

The launcher serves the interface at <http://127.0.0.1:5175> and the API at <http://127.0.0.1:8000>. If Atlas verification fails, it still starts the interface, but official operations remain blocked until access works; offline preview requires explicit selection. To verify database access separately:

```bash
.venv/bin/python scripts/verify_atlas.py
```

**Verified Atlas integration:** The official Sandbox ping/read/write and live recursive evaluation have passed. [The actual Atlas evaluation artifact](demo/evaluation-atlas.json) records `persistence=atlas`, measured decisions, matching run identifiers, and database verification. A live snapshot contained 21 runs, 1,785 frames, 5,516 traces, three versions, two proposals, two evaluations, and two deployment decisions; these counts grow with further runs. Recheck database status before presenting.

Manual launch, if preferred:

Start the backend from the repository root:

```bash
.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd frontend
npm run dev -- --port 5175
```

Open <http://127.0.0.1:5175>. API documentation is at <http://127.0.0.1:8000/docs>. Check `/database/status` before presenting: a successful connection alone is insufficient; the backend must also confirm a real write/read round trip.

For an explicitly noneligible development preview, set `BAYFLOW_OFFLINE=1`. Offline state is not Atlas persistence and cannot meet the competition acceptance criteria. Return to `BAYFLOW_OFFLINE=0` with the official URI before the hackathon demo.

## Architecture and recursive harnessing

```mermaid
flowchart LR
    UI[React transit replay / harness inspector] --> API[FastAPI jobs and history]
    API --> SIM[Seeded deterministic transit simulator]
    SIM --> TRACES[Metrics and failure traces]
    TRACES --> PLANNER[Gemini / Anthropic planner / labeled rules fallback]
    PLANNER --> SCHEMA[Pydantic harness safety envelope]
    SCHEMA --> CANDIDATE[Candidate architecture]
    CANDIDATE --> SIM
    SIM --> EVAL[Independent fixed evaluator]
    EVAL --> GATE[Promotion / rejection gate]
    GATE --> VERSION[Version history and rollback]
    API --> ATLAS[(Organizer MongoDB Atlas Sandbox)]
    TRACES --> ATLAS
    GATE --> ATLAS
    VERSION --> ATLAS
```

Harness v1 has independent Muni, BART, and Caltrain agents, local dispatch tooling, a 30-minute horizon, a 15-minute replanning interval, local-only context, six memory steps, basic verification, and local-greedy optimization. It is functional but has limited regional coordination.

The schema permits only known agents and tools, bounded horizon/replanning/memory parameters, and enumerated coordination/context/verification/strategy values. Companion-agent requirements constrain regional coordination and forecasting. The planner changes this configuration rather than generating executable code. Evaluator weights and scenario parameters are outside the harness mutation surface.

Every iteration diagnoses measured failures, creates a proposal, validates it, evaluates the candidate against its incumbent on matched scenarios/seeds, and records the resulting acceptance or rejection. A favorable prediction from a planner never counts as measured improvement. Historical versions can be inspected and explicitly rolled back.

The current loop uses fixed promotion seeds **1043, 2045, 3043, 4049, and 5051**, plus regression seed **5003**. The development seed must be disjoint from that suite. Promotion requires **at least 2% lower mean objective**, improvement on **at least three of five paired seeds**, **zero feasibility/capacity violations**, and **no more than 5% regression** on the control. Pure simulations run in parallel worker processes; only the parent writes persistence in fixed specification order. Mean, standard deviation, min/max, and each paired seed's metrics are retained. City evolution defaults to three iterations. The final three-way replay uses the development seed and is distinct from promotion-suite evidence. Historical artifacts below used the earlier three-seed gate and remain labeled historical results.

The planner receives development failures and prior evaluated proposal outcomes, configuration diffs, gate reasons, and persistent lessons. Outcome memory can include measured aggregate improvement and seed-win counts, so it is evaluation feedback. The same promotion suite is reused across adaptive iterations; it is a selection benchmark, not an untouched statistical test of generalization. A fresh final test suite would be needed for that claim.

## Scenario and data provenance

**The Bay Area Event Surge** is a seeded, fictional weekday evening from 4:00–11:00 PM. It includes a driver gap at 5:20, a BART delay at 6:10, Chase Center demand at 8:45, Oracle Park demand at 9:30, and possible cascading queues afterward. These are scenario parameters, not historical event claims.

The compact topology uses approximate real station coordinates and actual interagency transfer geography around Oracle Park, 4th & King, Mission Bay, downtown BART, Balboa Park, and Millbrae. Muni Bus, Muni Metro, BART, Caltrain, and walking connections are represented. Intermediate stops are compressed into directed corridor segments; no full regional GTFS reconstruction is claimed.

| Data | Classification | Default runtime use |
| --- | --- | --- |
| Selected Caltrain and compact-corridor places/transfers | Manually curated/derived | Caltrain connector / historical Event Surge |
| Headways, travel minutes, segment capacities, fleet/driver constraints | Synthetic assumptions | Yes |
| Passenger OD demand and fictional disruptions | Seeded synthetic | Yes |
| SFMTA/BART GTFS stops, route sequences, shapes and variants | Imported agency snapshots | City graph and geographic map; city demand is separately synthetic |
| 511 GTFS schedules | Optional published observations | Import/archive only; not automatically used by simulator |
| BART hourly OD ridership | Potential calibration source | Not imported or used in the default demo |
| SFMTA/Caltrain empirical ridership | Potential calibration source | Not imported or used in the default demo |

Official [511 transit documentation](https://511.org/open-data/transit) describes bulk GTFS feeds and the `operator_id=RG` regional feed. Access requires a token; see [511 FAQs](https://511.org/open-data/faqs). Optional feed use is governed by the [511 Data Disseminator Agreement](https://511.org/sites/default/files/2026-04/511_Data_Agreement_Final_2026.pdf), not this repository's MIT license. Imported views must display **“data provided by 511.org”** with a link near the data. No transit agency logos are required or supplied. [BART ridership reports](https://www.bart.gov/about/reports/ridership) are identified as a future calibration source, not evidence that the synthetic demand matches observed ridership.

Optional importer:

```bash
# Parse a previously downloaded GTFS ZIP without database writes.
.venv/bin/python scripts/import_gtfs.py --zip /path/to/feed.zip --dry-run
# Download official RG feed using TRANSIT_511_API_KEY and persist a corridor slice.
.venv/bin/python scripts/import_gtfs.py
```

The importer reads stops, routes, trips, stop times, calendars, shapes, and available transfers, handles optional missing files, and stores SHA-256, timestamp, source, bounding box, transformation, and row counts in `gtfs_imports`. Associated records use `gtfs_*` collections. It does not overwrite the curated runtime graph or claim demand calibration. A supplied ZIP must have its publisher verified by the participant. No raw feed is distributed in this repository.

## MongoDB evidence

Use the official PyMongo driver. The backend creates collection indexes and persists scenarios/network, runs, agent observations/actions, harness versions, proposals, evaluations, memory, and deployment decisions. The UI database indicator reflects actual backend status; it must not infer persistence from an animation.

In Atlas Data Explorer, select the configured database and inspect `simulation_runs`, `agent_traces`, `harness_versions`, `mutation_proposals`, and `evaluation_results`. Match run/version/proposal identifiers from the UI. Refresh after an evolution and verify new documents and the active-version decision. Never show a URI, `.env`, or token on screen.

`GET /harness/proposals` joins persisted proposals with candidate configurations and before/after evaluation history. The inspector can reload this audit trail after a browser refresh instead of depending on the last in-memory job result.

City replay frames use lossless `json-zlib-v1` storage: each document keeps searchable run/minute/time and passenger balance alongside the compressed full JSON payload. Application reads decode the original complete frame, including passenger flows/events. This reduces shared-Sandbox storage without replacing evidence with a summary or fabricated animation.

## Evaluation and reproducibility

The three comparison modes are static timetable (no intelligent intervention), fixed agents (operational actions with unchanged v1), and recursive harness (operational actions plus evaluated architecture mutations). Matching seeds and a fixed objective distinguish ordinary operational improvement from recursive improvement.

The historical compact Event Surge simulator advances in five-minute intervals. Seeded OD cohorts follow a shortest expected-time path; queues board up to each modeled departure's capacity, and arrivals advance to their next segment. Walking links connect distinct station/operator nodes. Its Muni standby interventions share three vehicle/driver pairs, each reserved for a modeled turn cycle. Driver gaps cancel alternate bus departures; the BART disruption cancels alternate departures and adds five minutes to travel. City Commute instead advances at one-minute intervals and uses the separately described city resources, phased GTFS-derived segment connections, typed policies/rules, and `city-intent-v2` objective.

Passenger delay is arrival time minus the earliest journey on **the same selected path** with undisrupted synthetic headways and unlimited capacity, clipped at zero. The reference is synthetic, not an observed published agency schedule. Unfinished journeys receive an explicit terminal charge `max(0, 420 - reference_arrival_minute + 30)` per passenger. This discourages leaving passengers unserved to improve the reported score. Average delay divides all completed and terminal charges by generated passengers. Transfer failures include capacity denial or waiting longer than a modeled connection headway; denied-boardings congestion counts can include repeated denial of the same passenger.

The historical Event Surge lower-is-better objective is:

```text
J = 0.50 × (average passenger delay / 30 minutes)
  + 0.20 × missed transfer rate
  + 0.20 × (unserved passengers / generated passengers)
  + 0.10 × (additional operating cost / 20,000)
  + 1,000 × (capacity violations + feasibility violations)
```

Congestion, queue peaks, wait time, occupancy violations, feasibility, and served/queued/onboard accounting are reported alongside the objective. Operating costs are synthetic scenario units, not quoted agency budgets. Evaluator `objective-v1` and its weights are stored with runs and cannot be changed by a harness proposal.

Run isolated tests, opt-in integration checks, and the frontend build:

```bash
npm test -- -q
# Real official Sandbox integration; requires its configured URI.
npm test -- --atlas -q
# Real configured model call; requires an available provider/model and key.
npm test -- --llm -q
# Both external integration checks.
npm test -- --atlas --llm -q
cd frontend
npm run build
```

Latest local validation passed **43 tests with three external checks skipped**, TypeScript checking, and the Vite build. The publishable-file scan found no actual credentials; `.env` remains untracked. Historical milestones additionally verified real Event Surge Atlas write/read, a real Gemini 3.8 Flash proposal, and live browser integration. Those historical external checks do not establish new city integration. Live UI checks default to port 5175 and accept `BAYFLOW_UI_URL` to override the address. Provider configuration alone is not proof of a model call: inspect the proposal's `planner.kind`, provider/model, and token metadata.

Run the entire recursive loop without a browser (official Sandbox required):

```bash
.venv/bin/python scripts/evaluate.py --scenario city_commute --seed 42 --iterations 3 --output demo/evaluation-city-rules-atlas.json
# Reproducible rule-based planner; still uses Atlas by default.
.venv/bin/python scripts/evaluate.py --scenario city_commute --rule-based --seed 42 --iterations 3
# Explicit isolated preview, with no database eligibility claim.
.venv/bin/python scripts/evaluate.py --scenario city_commute --offline --rule-based --seed 42 --iterations 3 --output demo/evaluation-city-rules-offline.json
# Preserve the historical compact scenario when that is what you intend to evaluate.
.venv/bin/python scripts/evaluate.py --scenario event_surge --seed 42 --iterations 2
```

The CLI prints real stage updates to stderr and measured results to stdout. `--output` saves the summary, not a video or proof of external publication. Repeated Atlas runs start from the current persisted harness; inspect version history or roll back to v1 when you need a fresh v1 comparison. Rollback records a decision; rejected candidates cannot be activated.

## API

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Process status, Atlas status, configured-model indicator |
| `GET /network` / `GET /scenarios` | Curated graph and scenario definitions |
| `POST /simulation/run` | Enqueue real simulation (`mode`, `seed`, `scenario`) |
| `GET /jobs/{job_id}` | Actual job status, stage history, result or failure |
| `GET /simulation/{run_id}` | Persisted summary, frames, and traces |
| `GET /simulation/{run_id}/frames` | Replay frames from persistence |
| `GET /harness/current` / `GET /harness/versions` | Active configuration and version history |
| `POST /harness/evolve` | Enqueue candidate planning and independent evaluations |
| `GET /harness/evaluations` | Persisted evaluation/gate results |
| `GET /harness/proposals` | Persisted proposal/configuration/evaluation audit history |
| `POST /harness/rollback` | Activate a prior accepted version and audit the decision |
| `GET /database/status` | Ping/read-write status and collection counts |

Example requests while the backend is running:

```bash
curl -sS http://127.0.0.1:8000/database/status
curl -sS -X POST http://127.0.0.1:8000/simulation/run \
  -H 'Content-Type: application/json' \
  -d '{"mode":"fixed","seed":42,"scenario":"city_commute","demand_scale":1.0,"advisory_acceptance_rate":0.6}'
curl -sS -X POST http://127.0.0.1:8000/harness/evolve \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"city_commute","seed":42,"iterations":3,"use_llm":true,"demand_scale":1.0,"advisory_acceptance_rate":0.6}'
# Substitute the actual returned job_id; poll until completed or failed.
curl -sS http://127.0.0.1:8000/jobs/ACTUAL_JOB_ID
curl -sS -X POST http://127.0.0.1:8000/harness/rollback \
  -H 'Content-Type: application/json' -d '{"version":"v1"}'
```

Long-running operations return HTTP 202 with a job ID. Polling `/jobs` reflects backend progress rather than cosmetic frontend stages. Only one evolution/rollback can run at once. An explicit request `offline:true` selects in-memory preview; historical query endpoints accept `?offline=true` for that store. Preview data disappears when the process exits. Job results are available in the running process; after restart inspect persisted run/evaluation endpoints instead.

## City evidence and verification status

The [completed city offline artifact](demo/evaluation-city-rules-offline.json) preserves three actual rule-based proposals, complete configuration diffs, paired metrics/distributions, and rule telemetry. All three were rejected by the unchanged gate:

| Candidate hypothesis | Mean promotion-suite improvement | Seeds improved | Decision |
| --- | ---: | ---: | --- |
| v2: neighbor context and two-minute incoming-transfer hold | −4.201133% | 0 / 5 | Rejected: objective worsened |
| v3: regional frequency coordination, urgent wait at six minutes | −5.844837% | 0 / 5 | Rejected: objective worsened |
| v4: regional frequency coordination, five-minute replanning | +1.206022% | 4 / 5 | Rejected: below the 2% mean-improvement gate |

The hold was executable rather than decorative: recorded candidate telemetry includes **5,107 rule evaluations, 233 triggers, 74 actual holds, 97 hold minutes, and 5,181 affected-rider event counts**. Trigger counts differ from executed holds because calendars, transfer arrival windows, and physical constraints still apply. Affected-rider counts can include repeated effects on a person; they are not unique passenger counts. The hypothesis's measured harm is retained.

All modes generated **9,761 passengers**. The selected champion remains v1, so its result equals fixed agents:

| Seed-42 city metric | Static timetable | Fixed agents / retained v1 |
| --- | ---: | ---: |
| Objective | 0.466728 | 0.445556 |
| First transit boarding within ten minutes | 49.9232% | 52.6688% |
| Arrival by original ETA plus ten minutes | 55.5066% | 58.3239% |
| Unserved passengers | 2,736 | 2,380 |
| Missed transfers | 689 | 615 |
| Crowd exposure, passenger-minutes | 198,733 | 152,755 |
| Additional operating cost, model units | 0 | 5,940 |

These are synthetic-model measurements, not observed San Francisco performance. The recursive mechanism worked, but the tested city mutations did **not** clear its promotion gate. An earlier trial exposed a repeated-fallback proposal bug; the final artifact reflects the corrected distinct hypotheses. New city Gemini-plus-Atlas verification is currently blocked by network access in this session; run the documented Atlas command in a network-enabled terminal. Do not relabel historical Event Surge database/model proof as a successful city evaluation. Supply/guidance ablations and acceptance sweeps are not claimed complete.

## Historical Event Surge results

[The preserved evaluation artifact](demo/evaluation-offline.json) contains actual rule-based planner results from a fresh offline seed-42, two-iteration run. Its UUIDs identify the executed offline runs; they are not Atlas document evidence. Both candidates were rerun under the fixed evaluator: neighbor coordination v2 improved mean promotion-suite objective only **0.83%** and was rejected; a subsequent regional shared-context v3 with 60-minute horizon and five-minute replanning improved it **22.23%** and was promoted. The planner selected this second mutation after observing residual failures and the previous rejection.

| Seed-42 demonstration metric | Static timetable | Fixed agents v1 | Promoted harness v3 |
| --- | ---: | ---: | ---: |
| Objective, lower is better | 0.403408 | 0.305224 | 0.240118 |
| Average delay, minutes | 20.235 | 15.131 | 11.563 |
| Served passengers | 3,394 | 3,827 | 3,992 |
| Unserved passengers | 1,651 | 1,218 | 1,053 |
| Additional operating cost, synthetic units | 0 | 810 | 990 |
| Missed-transfer rate | 0.00354 | 0.00354 | 0.00354 |
| Repeated capacity denials | 7,156 | 4,681 | 6,334 |

All modes generated the same **5,045** passengers. The evolved seed-42 objective is **21.33% lower** than fixed agents, at **22.22% higher additional operating cost**. Some metrics did not improve: transfer failures were unchanged and repeated boarding denials increased. These measured tradeoffs are preserved rather than hidden. Promotion uses the mean matched held-out suite, not this single demonstration percentage. The [Atlas-backed run](demo/evaluation-atlas.json) reproduced this three-way comparison and persisted its proposals, evaluations, and decisions. Both preserved evaluation artifacts used the rule-based planner. Future runs, model proposals, and persisted starting versions may produce different results.

The later [Gemini-plus-Atlas run](demo/evaluation-gemini-atlas.json) retained model-generated champion v4 and reproduced the same seed-42 comparison shown above. Its first mutation used the real LLM and was promoted; its second iteration used the labeled fallback after an invalid model response and was rejected. Read each decision's planner metadata rather than assigning one provider label to the whole run.

## Limitations

This is a simplified interval simulator, not a calibrated transport digital twin. Capacities refer to modeled segment departures; it does not reproduce physical fleet circulation, signaling, complete timetables, traffic, accessibility constraints, or actual dispatch systems. Demand and resource assumptions need empirical calibration. Regional low-threshold standby dispatch is enabled only during observed Muni overload, so low-load commuter demand does not consume the same reserve policy. Results demonstrate behavior in selected synthetic scenarios rather than proven real-city benefits. The system controls no real transit equipment. Reused promotion seeds and a short hackathon evaluation cannot establish broad generalization or long-term stability of architectural evolution.

## Demo and submission

Use [the three-minute live script](demo/LIVE_DEMO.md), [one-minute video plan](demo/VIDEO.md), [judge FAQ](demo/JUDGE_FAQ.md), and [submission evidence checklist](demo/SUBMISSION.md). Main flow: run baseline → inspect failure → evolve harness → inspect evaluated diff and acceptance/rejection → replay → inspect Atlas records.

The [public repository](https://github.com/jin-dalrae/bayflow) has been created and official Sandbox persistence has been verified. A submission video has not been recorded or uploaded; the included video file is a recording script. Video recording/upload and the participant's submission form remain required before the 5:00 PM Pacific deadline.

## What We Built During the Hackathon

The implementation authored for this build comprises the seeded transit simulator; operational agents; validated runtime harness schema; architecture mutation planner and explicit deterministic fallback; independent candidate evaluation and promotion/rollback; MongoDB persistence and APIs; React simulation replay and harness inspector; tests; optional GTFS importer; and demo/documentation artifacts. This section describes the new code's scope, not a claim that every external integration has been verified. Verification results and any incomplete requirements must be reported from actual execution.

Python/React and other dependencies are existing open-source libraries. Real place names and geography are identified separately from new software. Default scenario data is newly generated synthetic data. Optional imported datasets retain their providers' terms.

## License

New project code is [MIT licensed](LICENSE). Third-party libraries retain their own licenses; imported transportation data retains its provider terms. BayFlow is independent of the named transit agencies and does not imply their endorsement.

## Geographic map and requirement audit

The default transit view now uses a real, interactive San Francisco street map with OpenStreetMap attribution. Official agency GTFS reference layers include **3,238 Muni stop records, 50 BART parent stations, 58 Muni bus routes, 7 tram/Metro routes and 3 cable-car routes**. The map provides bus/rail/BART visibility controls, route inspection, station/stop search, and San Francisco/corridor/Bay Area zoom presets. Bus stops appear at neighborhood zoom to keep the map readable. Muni/BART simulated vehicles follow matching GTFS shape segments where available; Caltrain remains a simplified connector.

The city simulator now derives directed operating connections from actual GTFS stop sequences, including route shape/service variants, and adds bounded estimated walking interchanges plus selected Caltrain links. Its 3,292-node/8,369-edge graph receives explicitly synthetic neighborhood and route-local commute demand; the compact Event Surge graph remains separate. The current agency downloads returned feeds with validity ending August 28 and August 30, 2026; those dates are visible and the data is not advertised as current or live service. Route headways, departure phases, speeds, and capacities are modeled rather than today's full GTFS calendar. Source URLs, timestamps, SHA-256 checksums and transformations are embedded in the JSON. See [data attribution and provider terms](frontend/public/data/ATTRIBUTION.md). Agency data is excluded from the MIT software license.

Rebuild the map dataset after downloading fresh agency ZIP files:

```bash
.venv/bin/python scripts/build_map_reference.py --muni /path/muni.zip --bart /path/bart.zip
```

The [requirement audit](demo/REQUIREMENT_AUDIT.md) compares the working version with every major original requirement and records remaining gaps, including empirical demand calibration, GTFS-driven operational schedules and full-region simulation.
