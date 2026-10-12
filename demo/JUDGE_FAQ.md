# Judge questions

## What exactly happens in harness evolution?

**Short answer.** The harness is the typed configuration that decides how the transit operator agents work: active agents and tools, shared context, replanning cadence, dispatch thresholds and declarative operating rules. After a simulated operating window, a service monitor checks whether riders boarded within 10 minutes. If service is below target, Gemini reads the failure telemetry and its memory of past attempts and proposes **one** change. The change is validated, raced against the current version on five held-out days, and promoted only if it wins. Every step is stored in MongoDB Atlas, and the result becomes memory for the next attempt.

**What can change:** active agents/tools (for example a regional coordinator or transfer optimizer), coordination mode and context policy, replanning interval, planning horizon, memory window, 10 bounded policy thresholds, and up to 12 typed rules (signal ≥ threshold on an operator → action). **What cannot:** the evaluator, rider demand, deadlines, fleet, budget or test days. Operator agents are deterministic controllers; the LLM works at the harness level.

**One cycle:**
1. **Operate.** Run the current harness through a simulated commute on the real SF network.
2. **Monitor.** Every 15 simulated minutes, check riders whose 10-minute deadline has passed. Below 80% boarded on time, or 200+ riders in over-crowded queues, at two checks in a row triggers a review; otherwise the harness is kept.
3. **Diagnose.** Summarize worst segments, denied boardings, missed transfers, per-operator pressure and rule firings.
4. **Propose.** Gemini gets the current config, the diagnosis and recent Atlas lessons, and returns structured JSON with one hypothesis that changes at most 3 fields, including companions the schema requires.
5. **Validate.** Pydantic enforces bounds and dependencies. An invalid proposal gets one repair attempt, then a clearly labeled rule-based fallback.
6. **Evaluate.** Candidate and current version run on the same 5 held-out seeds (identical demand) plus a control run, scored with `city-intent-v3` (35% boarding within 10 minutes, 35% arrival by original ETA + 10, 20% crowding, 10% operating cost).
7. **Gate.** Promote only if the mean score improves at least 2%, at least 3 of 5 days win, the control does not regress more than 5%, and all actions are feasible.
8. **Persist and learn.** Proposal, evaluation and decision go to Atlas; a promotion moves the active-harness pointer, and a lesson goes to agent memory either way.
9. **Repeat** up to 3 times per window, building on the active version.

**Example (the demo run):** at 4:45 PM only 70% of riders had boarded within 10 minutes. Gemini, noting that earlier multi-change attempts failed, proposed sending standby buses sooner (local dispatch trigger 1.2 → 0.8). It won 5 of 5 unseen days (+3.04%) and was promoted as v36; held-out boarding within 10 minutes rose 68.9% → 69.9% and on-time arrivals 75.4% → 76.4%. Gemini then tried a lower trigger (v37, +0.25%) and tighter urgent waits (v38, 0%); both were rejected and v36 stayed.

**Rigor:** the planner never sees held-out days or their scores, and the evaluator and gate sit outside its mutation surface. Most of the 37 stored proposals were rejected because they made service worse. The cost weighting moved from `city-intent-v2` to the declared, versioned `v3` during development, because under v2 every extra bus was a net loss; v2 results keep their label.

**Why recursive harnessing?** BayFlow changes the machinery that chooses operational actions: agents/tools, coordination/context, bounded policy parameters, and typed trigger→action rules. It executes candidates on matched seeds and automatically selects or rejects versions. Dispatching a bus alone is an operational action; authoring and evaluating the rule that decides when to dispatch changes the harness.

**What does the model decide?** Gemini or Anthropic proposes a complete typed architecture/policy/rule hypothesis from development telemetry and previous outcomes. Pydantic validates it; Gemini can repair an invalid response once with redacted feedback. Simulation, passenger movement, capacity, scoring and gates use ordinary code. Missing/invalid model output triggers a labeled rule-based fallback. No generated Python runs.

**Is the current city result model-driven?** No. The completed three-iteration city artifact is explicitly offline and rule-based. New city Gemini-plus-Atlas verification is pending network access. Historical Event Surge separately has actual Gemini-generated v4 promotion and Atlas readback in `evaluation-gemini-atlas.json`; it is genuine proof of the mechanism but not a city performance result.

**What happened in the city experiment?** The two-minute hold worsened mean objective 4.201133%, winning 0/5 seeds. Regional service allocation/urgent wait worsened it 5.844837%, winning 0/5. Five-minute regional replanning improved it 1.206022%, winning 4/5, but failed the unchanged 2% mean gate. All were rejected and v1 retained. The loop worked; it did not find a qualifying city champion.

**Did rules actually execute?** Yes. The hold candidate recorded 5,107 evaluations, 233 triggers, 74 executed holds, 97 hold minutes and 5,181 affected-rider event counts. Counts of affected riders can include repeated effects. Calendar/resource/arrival constraints explain why a trigger need not execute an action. A hold defers one existing directed segment departure, not a complete physical vehicle schedule; downstream calendars stay fixed.

**What is a successful journey?** First bus/rail boarding within ten minutes of requested departure and final arrival by the frozen original ETA plus ten minutes. Walking does not count as boarding. A detour preserves destination and cannot reset the initial ETA. Final rates divide by all generated passengers, including unserved requests as failures. Actual arrivals are distinct from predicted ETA.

**How is crowding measured?** Passenger-minutes queued above modeled density 1.5 persons/m², plus peaks/distribution. Assumed queue areas are bus 25, Metro 180 and BART 400 m². These are synthetic modeling parameters, not surveyed dimensions or a safety standard. Inspect global exposure so an intervention cannot claim success by moving congestion elsewhere.

**What can agents manipulate?** Limited standby dispatch, bounded low-load service suppression, transfer priorities/holds and voluntary valid-route alternatives. Advice acceptance has its own fixed seeded randomness. City limits are 12 bus/four Metro/two BART/one Caltrain standby pairs and 12,000 gross model-cost units. The harness cannot create resources or change demand, consent, deadlines, density assumptions, scoring or budgets.

**How do you prevent score manipulation?** `city-intent-v2` is predefined: .35 boarding target, .35 arrival target, .20 normalized crowd exposure, .10 nonnegative net additional cost, plus strong unsafe-action penalties. Five fixed paired seeds require ≥2% mean improvement, ≥3 wins, no safety/capacity violations and ≤5% control regression. Original Event Surge's `objective-v1` and earlier three-seed results remain historical rather than being rescored.

**Does it generalize?** The promotion suite is reused and aggregate outcome lessons feed the planner. It supports selection within this simulation, not an independent generalization claim. Freeze a champion, evaluate untouched seeds, calibrate empirical demand, and execute supply/guidance ablations plus compliance sweeps before stronger claims.

**How realistic is the network?** The 3,292-node, 8,369-edge city graph uses actual GTFS stop sequences and service variants; all 82 imported agency service records, including all 58 Muni bus routes, carry modeled passengers. August-expired snapshots are not current schedules. Headways/speeds/capacities/demand are synthetic, nearby walking links are estimated, and Caltrain is a selected connector. There are no GPS feeds, real passengers, full vehicle blocks or real dispatch control.

**Why MongoDB?** Atlas links configuration diffs, proposals, simulations, full losslessly compressed frames, telemetry, per-seed evaluations, decisions, memory and rollback. Historical official Sandbox read/write is verified. The new city run must receive its own actual verification; offline storage is labeled and not substituted for Atlas.

**What was built?** New simulator/controller code, real-GTFS graph/map integration, passenger-intent instrumentation, validated architecture/policy/rule schema, planner and fallback, parallel paired evaluation, version gating/history/memory, persistence/API, UI, tests and documentation. Standard libraries and agency datasets retain attribution. Latest local tests passed 42 with three external checks skipped, alongside TypeScript and Vite build.
