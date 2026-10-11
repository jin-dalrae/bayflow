# BayFlow implementation and evidence audit

Audit snapshot: October 11, 2026, approximately **1:51 PM Pacific**; deadline remains 5:00 PM Pacific. The clock was checked during this review. This assessment covers the original build instruction and subsequent passenger-intent, authentic-map, typed-rule, autonomous-operation, long-scenario, and history requests. It separates executable functionality, measured evidence, in-progress changes, and human access blockers; it is not a completion percentage.

## Main finding

The recursive loop is real: typed operating configurations/rules change executable behavior, candidates are actually rerun against frozen metrics, and rejected versions retain the incumbent. Historical Event Surge proves real Gemini-plus-Atlas promotion. The new three-hour city loop is measured offline and rejected all three tested hypotheses. It has not yet proved a qualifying city improvement or new official model/database execution.

Backend-triggered review and dedicated history now have actual API-backed preview browser proof. A 720-minute simulation passed conservation, capacity, clock rollover, frozen-intent and four-operator tests. A full autonomous 720-minute evolution has also completed with its actual offline artifact; 1,440 minutes is supported, but no full-day performance result is claimed. Successful current Atlas/model access and a reproducible tested demo take priority over speculative features.

| Requirement | Status | Evidence and limits |
| --- | --- | --- |
| Recursive harness rather than dashboard | Implemented; historical real-model/Atlas cycle verified | Observed failures → typed architecture/policy/rule proposal → executable reruns → independent gate → promotion/rejection. The inspector exposes this backend process. |
| Architecture, tools, context, planning, rules evolve | Implemented; unsupported city capabilities excluded | Agent/context/coordination/replanning/memory and typed policies/rules affect behavior. The audit found unimplemented city forecasting/predictive capabilities; they are now excluded from city planner choices and invalid model proposals are rejected/retried. Feasibility remains deterministic rather than depending on a decorative tool flag. Historical compact-model forecasting remains separately available. |
| Real LLM planner | Historical Event Surge verified; new city check pending | Gemini 3.8 Flash generated promoted v4 in `evaluation-gemini-atlas.json`; a second invalid model response produced a labeled fallback/rejection. Current planner permits one validation repair retry and preserves attempt/error/token metadata. No new city LLM success is inferred from historical proof. |
| Official organizer Atlas | Historical verification passed; current new city run blocked by network access | PyMongo ping/read/write and actual persisted Event Surge records were verified. No substitute cluster exists. New city integration must be verified through the documented terminal command and actual city artifact. |
| Public repository and reproducibility | Working | <https://github.com/jin-dalrae/bayflow>; checkpoint `bfa3fbc` was pushed. MIT software license, source attribution, launcher, CLI, API, tests, and ignored credentials. |
| City-wide connected transit graph | Implemented, measured baseline runs | 3,292 nodes, 8,369 directed transit/walking edges. Actual GTFS stop sequences and branch/service variants form connections; geographically bounded walking transfers and the selected synthetic Caltrain connector remain derived. |
| Broad bus coverage | Implemented operations, not just a map | The city baseline boards passengers on all 82 imported agency service records, including all 58 Muni bus routes; Muni Metro/BART operate; the twelve-hour test additionally boards and delivers 61 Caltrain riders, yielding 83 active service IDs. Service records include variants/bridge buses and do not imply 82 independent fleets. |
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
| Autonomous performance-triggered operation | Implemented; actual API-backed preview verified | Backend monitor checks matured deadlines/crowding every 15 minutes; ≥200 matured intents and two failing checkpoints trigger review. Healthy-run test forbids planner calls. Actual browser tests completed monitored 180-minute and 720-minute runs; the headless twelve-hour artifact records a minute45 trigger and three rejected five-seed evaluations without a separate evolve command. This is a finite monitored run/batch, not a perpetual production controller. |
| Twelve-/24-hour operation | Twelve-hour simulation verified; full-day performance unmeasured | API/UI/CLI default 720 minutes, permitted range 180–1,440. Actual 720-minute tests prove every-frame conservation, capacity, post-180 demand/arrivals, next-day clock, frozen demand/ETA across harnesses, and all four operators. The original three-hour metrics remain unchanged. Overnight calendars are synthetic; no actual agency operating-hours fidelity or verified 24-hour performance is claimed. |
| Dedicated evolution-history page | Implemented and actual API-backed preview verified | Loads real proposals/versions/evaluations with outcome/version filtering. Corrected evaluation-ID joins are exercised after autonomous review and refresh, including actual diffs, five-seed results and rule telemetry. Scenario labels prevent mixed-history misinterpretation; offline records remain process-local. |
| Replay persistence and compression | Implemented | `json-zlib-v1` losslessly stores full city frames while leaving run/minute/time/passenger balance queryable. Application decoding restores full passenger events/flows. |
| User experiment controls | API implemented | `demand_scale` default 1, range .25–3; `advisory_acceptance_rate` default .6, range 0–1. Both are frozen across each paired experiment. Changes are scenario inputs, not harness mutations. |
| Ablations/compliance sweep | Planned, not claimed complete | Supply-only, guidance-only, combined, and 0/30/60/90% acceptance need actually executed results before performance claims. |
| Submission/demo artifacts | Prepared; human actions remain | README, diagram, recording/live scripts, FAQ, historical evidence and actual city offline artifact. New city Atlas artifact remains unverified. No recorded video/uploaded form/cloud deployment claim. |

## Actual city evidence so far

The [completed city offline artifact](evaluation-city-rules-offline.json) preserves all three actually executed proposals. The two-minute transfer-hold v2 worsened mean objective **4.201133%**, winning zero of five seeds. Regional frequency/urgent-wait v3 worsened it **5.844837%**, winning zero. Regional frequency/five-minute replanning v4 improved it **1.206022%**, winning four, but failed the unchanged 2% improvement gate. All were rejected and v1 retained.

The transfer rule recorded 5,107 evaluations, 233 triggers, 74 executed holds, 97 hold minutes, and 5,181 affected-rider event counts. These establish actual rule execution, not improvement or unique affected-person counts. The final artifact contains distinct cadence hypotheses after a repeated-fallback proposal issue was found and fixed during investigation.

The hold defers one directed segment departure; downstream segment calendars stay fixed. It does not shift a whole physical vehicle block. Later missed legs are a plausible tradeoff to investigate, not an established causal explanation for its worse objective. Current full local validation passed 56 tests with three external checks skipped. Three API-backed preview browser tests passed, with the Atlas browser check skipped; TypeScript checking/Vite build and the publishable-file credential scan passed.

The retained seed-42 city result remains objective **0.445556**, first-boarding success **52.6688%**, arrival-by-original-ETA-plus-ten success **58.3239%**, **2,380 unserved**, and **615 missed transfers**, from 9,761 generated passengers. This is an honest negative recursive city result: the mechanism works, but no tested candidate qualifies as a better champion. It must not be presented as a city promotion.

Historical `evaluation-gemini-atlas.json` establishes real model-driven architecture evolution and required Atlas persistence for Event Surge. It does not establish that the expanded city experiment has already completed official database/model verification. To create that new evidence:

```bash
.venv/bin/python scripts/evaluate.py --scenario city_commute --horizon-minutes 180 --seed 42 --iterations 3 --output demo/evaluation-city-rules-atlas.json
```

Use the organizer's original Sandbox. Inspect artifact `database_verification`, proposal planner metadata, per-seed comparisons, configuration diffs, rule telemetry, and deployment decisions. A failed connection or invalid model response remains a visible failure/fallback, not success.

## Verified twelve-hour autonomous experiment

[The actual twelve-hour offline artifact](autonomous-city-12h-offline.json) records backend-triggered review without a separate evolve command. The monitor found persistent failure at **16:45 (minute 45)**: the preceding checkpoints contained 1,979 and 2,852 matured intents, boarding success 62.0515% and 59.0813%, and 286/315 modeled crowded waiting riders. Its decision used checkpoint observations, not future passenger outcomes.

The three candidate hypotheses were actually evaluated on five matched seeds and all rejected:

| Hypothesis | Mean objective improvement | Seeds improved | Decision |
| --- | ---: | ---: | --- |
| Neighbor context and incoming-transfer hold | −13.252378% | 0 / 5 | Retain v1 |
| Regional frequency and earlier urgent wait | −16.931192% | 0 / 5 | Retain v1 |
| Regional frequency and faster replanning | −8.277596% | 0 / 5 | Retain v1 |

The hold executed 173 times for 237 hold minutes, from 586 triggers/9,796 evaluations, affecting 8,388 rider events. Seed42 generated **18,315 passengers** across 83 active service IDs; the selected Caltrain connector delivered all 61 synthetic riders over 183 directed-leg boardings. Fixed and retained evolved v1 both scored **0.581732**, served **18,004**, left **311 unserved**, met first-boarding targets for **41.5070%** and arrival targets for **65.5856%**, and incurred **11,970 model cost units**. Static service scored 0.761241, served 16,848, and left 1,467 unserved. The fixed agents help, but recursive candidates added no qualifying benefit in this experiment. All runs preserved capacity/feasibility limits.

This is an explicitly **offline rule-based** experiment. It proves executable monitoring, mutation, evaluation and safe rejection; it does not prove a new city Gemini call or Atlas write. Twelve-hour playback also passed an actual API-backed browser check. Supported 24-hour duration remains an unmeasured performance setting, with synthetic overnight operations.

## Three critical code findings sent for repair

1. **Advertised city features must execute.** At review time city execution did not consume the forecasting tool/agent or distinguish predictive optimization, and the feasibility-tool flag did not gate a distinct action. This can make a real model proposal look architectural while changing nothing. Add measured execution/telemetry tests or omit those capabilities from the city planner.
2. **Lessons and champions need experiment scope.** Prior proposal/memory retrieval mixed scenarios, and the active-version pointer was global. A historically accepted Event Surge configuration is not a validated City Commute champion under a different evaluator. Scope useful lessons/current selection by scenario/evaluator, or clearly present cross-scope application as an unevaluated starting configuration.
3. **Primary actions must match the live API.** New frontend controls send `horizon_minutes` and `/operations/start`; at the initial audit snapshot the old backend schema/route could return 422/404. In-flight API changes need an actual browser/API check, including job stages, measured automatic triggers, result readback, and history refresh. UI labels alone are insufficient evidence.

**Repairs and checks:** City planner capability filtering now excludes the nonexecuting forecasting/predictive choices; the rule fallback no longer adds the unused city feasibility tool. Scenario-specific champion pointers and lesson retrieval prevent accidental Event Surge champion inheritance, with an isolated test proving the separation. Actual frontend/API tests now exercise `/operations/start`, the 180-minute trigger, three evaluations and refreshed joined history. The 720-minute kernel tests independently prove long-horizon behavior. These repairs address the reported gaps; they do not establish new Atlas/model access.

## Modeling and interpretation limits

- Actual GTFS topology is not actual current service: downloaded calendars expired in August; headways, phase offsets, travel speeds, capacities, demand, compliance and queue areas are synthetic. There are no live passenger/GPS observations.
- Autonomous operation completes its observation run, finds the first failure using only checkpoint-available data, then evaluates full matched reruns. It does not hot-swap architectures during a passenger journey or run an unbounded live dispatcher.
- Representative route variants and independent segment calendars do not implement complete physical fleet blocks, signaling, staffed agency dispatch, surveyed pedestrian accessibility or actual road traffic.
- Density measures queues per assumed area; “crowded” is a modeled threshold, not an official safety warning. No real transit equipment is controlled.
- Advisories are voluntary predictions constrained by the original ETA allowance; actual arrivals are separately scored. They do not guarantee boarding or arrival.
- The original three-hour saved baseline serves 82 imported Muni/BART records. The twelve-hour extension adds three seeded Caltrain commute cohorts at minutes 125/155/185; verified seed42 boardings deliver all 61 riders over three directed legs (183 boarding events). This is a synthetic connector, not imported Caltrain GTFS/ridership.
- The adaptive planner receives aggregate outcome lessons and reuses five promotion seeds. Untouched final tests and empirical calibration are needed for generalization; none of the city ablation/compliance sweeps has been claimed run.
- Official Atlas/model access in this new phase is blocked by session networking. Historical proof remains valid for its stated scenario, and explicit offline preview does not satisfy new external integration.

## Remaining work before stronger claims

1. Investigate the rejected city hypotheses and retain their actual target/crowding/cost tradeoffs; do not relax the gate to manufacture promotion.
2. Verify the new city loop against the official Atlas and configured Gemini in a network-enabled terminal; inspect readback.
3. Complete meaningful ablations and acceptance sweeps; test untouched final seeds rather than treating the adaptive promotion suite as generalization proof.
4. Obtain valid current GTFS and empirically calibrate demand, capacities, queue areas, and vehicle/driver resources.
5. Model complete vehicle blocks and more realistic service/accessibility constraints before operational use.
6. Record/upload the demo and complete the participant's submission.

The core recursive-harness mechanism is real. The city extension expands executable coverage and makes individual journey intent explicit; its completed offline hypotheses were rejected. A new positive performance claim needs an actually qualifying candidate, and new city external-persistence proof remains outstanding.
