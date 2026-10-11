# How to show BayFlow is moving passengers and evolving its harness

BayFlow tracks simulated passengers, not real people or live agency vehicles. The real map and imported route shapes provide geographic context. Passenger accounting and journey events prove what the backend simulated.

## What the two buttons do

**Run baseline:** Execute the selected synthetic scenario with fixed agents (default). Their v1 architecture stays unchanged. Agents can dispatch within their resource envelope, so this is an intelligent operational baseline, not the no-intervention baseline. Select "Static timetable" in the policy control for the no-agent baseline.

**Evolve harness:** Diagnose development-run failures, ask Gemini for a schema-constrained architecture proposal (or a visibly labeled fallback), rerun candidate and incumbent on matched evaluation seeds, apply the frozen promotion and safety gates, record acceptance/rejection and activate only a passing candidate. A rejected mutation is useful evidence that the gate is working. A proposal's predicted improvement is not a result.

## Show movement in 45 seconds

1. Run a fresh fixed-agent baseline with the Event Surge scenario and seed 42. Pause the replay.
2. Point to **Passenger movement / simulation evidence**. At every frame, generated = waiting + walking + riding + arrived. All five counts come from backend state.
3. Click **Follow event crowd**. This selects the first Chase Center group and seeks to its actual creation time, 8:45 PM. The group contains 95 simulated people.
4. Click **Next journey step**. The timeline records walking to UCSF/Chase Center, walking to the route-22 bus stop, boarding Muni bus, alighting/walking to 16th Street BART, boarding BART, and arriving at Balboa Park. The map highlights this group's route; its occupied vehicles get white outlines. Vehicle occupancy and the tracked group's count are available on hover.
5. Continue stepping until **95/95 arrived**. In the seed-42 fixed baseline, the first group boards route 22 at 9:00 PM, transfers to BART at 9:30 PM, and arrives at 9:40 PM. Boarding is split across modeled scheduled and standby vehicles; the timeline shows the number of recorded vehicles rather than pretending the group fits into one bus.
6. Open **Origin → destination ledger** to show generated, waiting, traveling, and arrived counts for each demand pair. Scrub backward: the counts and events revert to that frame, rather than remaining at final totals.

Exact counts/times are scenario- and harness-dependent. Only use these fixed seed-42 values for that particular baseline. Runs created before passenger instrumentation need to be rerun.

## Show recursive improvement in 60 seconds

1. Click **Evolve harness** and show actual backend stages.
2. Show the old and candidate configuration. Look for changed coordination, context sharing, tools, replanning frequency, horizon or memory. A bus dispatch alone is not harness evolution.
3. Show the paired before/after objective and safety/regression gate. The candidate must improve the mean promotion-suite objective at least 2%, have no feasibility/capacity violations, and stay within the 5% commuter regression bound.
4. State whether the actual proposal was Gemini or rule-based. Show acceptance/rejection and active version. Do not promise that every proposal wins.
5. Replay the resulting simulation. Compare the objective, passenger delay and unserved counts against the fixed baseline; also mention operating cost and metrics that worsened.

The preserved verified run promoted Gemini's v4: 22.23% lower promotion-suite objective and 21.33% lower seed-42 demo objective than fixed agents. Modeled cost rose 810 → 990. The second model response failed validation; its labeled fallback was evaluated and rejected. These are recorded results, not guaranteed results for every later run.

## Prove persistence and correctness

In Atlas Data Explorer, select the configured `bayflow` database:

- `simulation_runs`: match the displayed run ID, completed status, metrics, and passenger-group catalog.
- `simulation_frames`: filter `{ "run_id": "DISPLAYED_RUN_ID" }`, sort by `minute`, and inspect `passenger_balance`, `passenger_flows`, and `passenger_events`.
- `mutation_proposals` / `evaluation_results` / `deployment_decisions`: match mutation ID and candidate version, confirm model metadata, measured scores, decision and active pointer.

The same data can be retrieved through `GET /simulation/{run_id}`. Do not expose the connection URI or API key.

Tests check conservation at every frame and OD pair, nonnegative state counts, boarding before leg arrival, group counts never exceeding their generated population, and arrival totals matching served metrics. The observability changes preserve the original seed-42 baseline objective 0.305224.
