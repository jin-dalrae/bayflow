# BayFlow implementation and evidence audit

Audit date: October 11, 2026. This assessment separates executable functionality, measured offline evidence, historical external-integration proof, and outstanding new integration checks. It is not a completion percentage.

| Requirement | Status | Evidence and limits |
| --- | --- | --- |
| Recursive harness rather than dashboard | Implemented; historical real-model/Atlas cycle verified | Observed failures → typed architecture/policy/rule proposal → executable reruns → independent gate → promotion/rejection. The inspector exposes this backend process. |
| Architecture, tools, context, planning, rules evolve | Implemented | Validated agent/tool lists, topology, context, horizon, replanning, memory, strategy, bounded controller parameters, and up to 12 declarative rules. Rules are interpreted actions, not generated Python. |
| Real LLM planner | Historical Event Surge verified; new city check pending | Gemini 3.8 Flash generated promoted v4 in `evaluation-gemini-atlas.json`; a second invalid model response produced a labeled fallback/rejection. Current planner permits one validation repair retry and preserves attempt/error/token metadata. No new city LLM success is inferred from historical proof. |
| Official organizer Atlas | Historical verification passed; current new city run blocked by network access | PyMongo ping/read/write and actual persisted Event Surge records were verified. No substitute cluster exists. New city integration must be verified through the documented terminal command and actual city artifact. |
| Public repository and reproducibility | Working | <https://github.com/jin-dalrae/bayflow>; checkpoint `3889648` was pushed. MIT software license, source attribution, launcher, CLI, API, tests, and ignored credentials. |
| City-wide connected transit graph | Implemented, measured baseline runs | 3,292 nodes, 8,369 directed transit/walking edges. Actual GTFS stop sequences and branch/service variants form connections; geographically bounded walking transfers and the selected synthetic Caltrain connector remain derived. |
| Broad bus coverage | Implemented operations, not just a map | The city baseline boards passengers on all 82 imported agency service records, including all 58 Muni bus routes; Muni Metro, BART, and selected Caltrain also operate. Service records include variants/bridge buses and do not imply 82 independent fleets. |
| Authentic geographic display | Working | Leaflet/OpenStreetMap streets, real agency stop/shape coordinates, route controls/search, and geographically matched moving simulation indicators. Vehicles are not live GPS. |
| Source provenance/currentness | Explicit limitations | Official agency downloads are observed schedule snapshots expiring August 28/30, 2026. They are not valid current-service predictions. Synthetic demand, operations, areas, disruptions, and resource assumptions are separately identified. |
| 511 regional feed | Optional importer implemented | ZIP parsing/archive/provenance supported; current graph comes from official agency feeds, not an imported regional 511 feed. No 511 or empirical demand integration is falsely claimed. |
| Ridership calibration | Outstanding | BART OD and Muni/Caltrain demand calibration are not imported. All generated commute and event riders remain seeded synthetic. |
| Event Surge and disruptions | Historical compact model implemented | Original 21-node scenario includes driver gap, service delay, and stadium surges; commuter and accident scenarios remain available. City commute uses separate synthetic disruption/intent parameters. |
| Passenger journeys and capacity | Implemented | Cohorts have requested origins/destinations, original paths/ETA, actual queue/boarding/transfer/arrival states, and conservation. Vehicle capacity and reserve limits apply. Segment calendars approximate operations rather than reproducing physical fleet blocks/signaling. |
| City journey targets | Implemented fixed evaluator | First transit boarding within ten minutes; arrival by frozen initial ETA plus ten minutes; unserved passengers remain failed final targets. Walking is not first boarding; reroutes do not reset intent deadlines. |
| Crowding measurement | Implemented synthetic model | Queue exposure passenger-minutes plus peak density, with assumed bus/Metro/BART queue areas 25/180/400 m² and threshold 1.5 persons/m². These are model assumptions, not surveyed areas or safety standards. |
| Supply and voluntary demand guidance | Implemented bounded actions | Standby dispatch, limited low-load service suppression, and connected alternative routes within original ETA allowance. Advice acceptance is seeded separately from demand; passengers may decline. Forecasts are distinct from realized outcomes. |
| Fixed city resources and cost | Implemented | 12 bus, four Metro, two BART, one Caltrain standby vehicle/driver pairs; gross supplemental budget 12,000 model units, not dollars. An overspending development candidate worsened the score despite some improved passenger outcomes; fixed budget/weights apply to all benchmark versions. |
| Typed operating-rule execution | Implemented, telemetry available | Signals: queue ratio, oldest wait, incoming transfer riders, and unboarded-intent age. Actions: dispatch, transfer priority, or bounded hold ≤5 minutes. Incoming riders are projected through explicit walking transfer links; a hold defers a real existing departure without inventing fleet/capacity. Tool/context authorization is validated. |
| Diagnosis and trace audit | Implemented | Top ten queue/denial edges, separately ranked transfer-wait edges, exact cohort denial counts, operator summaries, rule triggers/actions/hold minutes/riders, configuration diffs, and persistent accept/reject lessons. Observation deduplication does not discard legitimate cohort denial events. |
| Evaluator independent of planner | Implemented | Historical `objective-v1` retained unchanged. New predefined `city-intent-v2` weights: .35 boarding success, .35 arrival success, .20 crowd exposure, .10 nonnegative net additional cost, plus 1,000 per unsafe/infeasible violation. Scoring and physical/consent inputs cannot be mutated. |
| Fair multi-seed promotion | Implemented and offline city loop completed | Five fixed paired seeds 1043/2045/3043/4049/5051; separate development seed and regression seed 5003. ≥2% mean improvement, ≥3/5 seed wins, zero safety/capacity violations, and ≤5% control regression required. Three city proposals were evaluated and rejected, retaining v1. Distribution/per-seed metrics are stored. Parallel pure workers do not write Atlas. |
| Iteration, history, memory, rollback | Implemented | City defaults to three iterations. Prior diffs, gate reasons, and lessons enter bounded planner memory. Rejected configurations cannot be activated by rollback. Reused promotion seeds limit generalization claims. |
| Replay persistence and compression | Implemented | `json-zlib-v1` losslessly stores full city frames while leaving run/minute/time/passenger balance queryable. Application decoding restores full passenger events/flows. |
| User experiment controls | API implemented | `demand_scale` default 1, range .25–3; `advisory_acceptance_rate` default .6, range 0–1. Both are frozen across each paired experiment. Changes are scenario inputs, not harness mutations. |
| Ablations/compliance sweep | Planned, not claimed complete | Supply-only, guidance-only, combined, and 0/30/60/90% acceptance need actually executed results before performance claims. |
| Submission/demo artifacts | Prepared; human actions remain | README, diagram, recording/live scripts, FAQ, historical evidence and actual city offline artifact. New city Atlas artifact remains unverified. No recorded video/uploaded form/cloud deployment claim. |

## Actual city evidence so far

The [completed city offline artifact](evaluation-city-rules-offline.json) preserves all three actually executed proposals. The two-minute transfer-hold v2 worsened mean objective **4.201133%**, winning zero of five seeds. Regional frequency/urgent-wait v3 worsened it **5.844837%**, winning zero. Regional frequency/five-minute replanning v4 improved it **1.206022%**, winning four, but failed the unchanged 2% improvement gate. All were rejected and v1 retained.

The transfer rule recorded 5,107 evaluations, 233 triggers, 74 executed holds, 97 hold minutes, and 5,181 affected-rider event counts. These establish actual rule execution, not improvement or unique affected-person counts. The final artifact contains distinct cadence hypotheses after a repeated-fallback proposal issue was found and fixed during investigation.

The hold defers one directed segment departure; downstream segment calendars stay fixed. It does not shift a whole physical vehicle block. Later missed legs are a plausible tradeoff to investigate, not an established causal explanation for its worse objective. Final local validation passed 43 tests with three external checks skipped, TypeScript checking and Vite build; the publishable-file credential scan passed.

The retained seed-42 city result remains objective **0.445556**, first-boarding success **52.6688%**, arrival-by-original-ETA-plus-ten success **58.3239%**, **2,380 unserved**, and **615 missed transfers**, from 9,761 generated passengers. This is an honest negative recursive city result: the mechanism works, but no tested candidate qualifies as a better champion. It must not be presented as a city promotion.

Historical `evaluation-gemini-atlas.json` establishes real model-driven architecture evolution and required Atlas persistence for Event Surge. It does not establish that the expanded city experiment has already completed official database/model verification. To create that new evidence:

```bash
.venv/bin/python scripts/evaluate.py --scenario city_commute --seed 42 --iterations 3 --output demo/evaluation-city-rules-atlas.json
```

Use the organizer's original Sandbox. Inspect artifact `database_verification`, proposal planner metadata, per-seed comparisons, configuration diffs, rule telemetry, and deployment decisions. A failed connection or invalid model response remains a visible failure/fallback, not success.

## Remaining work before stronger claims

1. Investigate the rejected city hypotheses and retain their actual target/crowding/cost tradeoffs; do not relax the gate to manufacture promotion.
2. Verify the new city loop against the official Atlas and configured Gemini in a network-enabled terminal; inspect readback.
3. Complete meaningful ablations and acceptance sweeps; test untouched final seeds rather than treating the adaptive promotion suite as generalization proof.
4. Obtain valid current GTFS and empirically calibrate demand, capacities, queue areas, and vehicle/driver resources.
5. Model complete vehicle blocks and more realistic service/accessibility constraints before operational use.
6. Record/upload the demo and complete the participant's submission.

The core recursive-harness mechanism is real. The city extension expands executable coverage and makes individual journey intent explicit; its completed offline hypotheses were rejected. A new positive performance claim needs an actually qualifying candidate, and new city external-persistence proof remains outstanding.
