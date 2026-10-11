# BayFlow experiment thesis

## The claim to test

People care about completing their intended journey. A less crowded system is useful only if it still gets them where they meant to go, reasonably close to when they expected to arrive.

BayFlow tests whether coordinating **service supply** and **voluntary passenger choices** improves those journeys more than adding vehicles alone, and whether an agent harness that can change its own coordination, tools, context, and planning performs better than an otherwise fixed harness.

The commuter targets are first bus/rail boarding within ten minutes of the requested departure and arrival no later than the original ETA plus ten minutes. These are the current explicit interpretation of the desired journey guarantee. They are experimental targets; BayFlow cannot guarantee them in real transit operations.

## Current evidence and extension status

The original Event Surge experiment is implemented and verified on a compact 21-node model. It includes seeded demand, driver/service disruptions, queue-capacity mechanics, controller traces, executable harness mutation, fixed evaluator gates, real Gemini proposals, and organizer Atlas persistence. The preserved Gemini-plus-Atlas artifact shows a model-generated version promoted and a subsequent labeled fallback rejected. Its 21.33% seed-42 objective improvement uses the historical `objective-v1` formula; it is not a city boarding/arrival result.

The interface also includes imported SFMTA/BART stop/shape data. Those observed schedule snapshots expired in August 2026; they are not current service or live GPS feeds. Passenger demand remains synthetic.

The City Commute extension has a constructed GTFS-connected network with 3,292 nodes and 8,369 directed edges, plus selected derived Caltrain connections. The city simulator, advisory execution, deadline metrics, controls, and paired measurements are still being implemented. This document predefines their hypotheses and scoring before their results exist. No city or ablation performance claim is made yet.

## What the agents may change in the simulated city

| Lever | Intended action | Constraint |
| --- | --- | --- |
| Standby service | Add a departure where observed queues or predicted arrivals justify it | Fixed vehicle/driver pool; reserve until its modeled return cycle |
| Service frequency | Reallocate feasible departures or test bounded low-demand suppression | Minimum service floor, existing route connections, and no illegal cancellation or invented resources |
| Voluntary passenger advice | Offer a connected alternative path that avoids a crowded segment | Same destination; predicted ETA no more than ten minutes beyond the original; seeded acceptance or decline |
| Harness architecture | Change active agents/tools, shared context, coordination, memory, horizon, or replanning | Typed schema and allowlist; cannot edit the simulator, resource limits, or evaluator |

`service_frequency_optimizer` and `passenger_advisory` are the planned bounded tool interfaces. A regional coordinator works with operator agents to select actions. LLM output is an architecture hypothesis; ordinary algorithms calculate capacity, routes, boarding, travel, costs, and scores. A model cannot create a bus or calculate its own improvement.

Suppressing service is a constrained experiment, not permission to cancel arbitrary trips. Savings are meaningful only when the minimum service and journey outcomes hold. The score uses nonnegative net additional cost, so reducing service cost below baseline cannot create an unlimited negative fitness reward.

A sign saying “try this less crowded route” is an advisory in the simulator, not an official route change, crowd-safety warning, or command to a passenger. Acceptance is modeled using a separate seeded random stream. The same people and acceptance draws must be available to both sides of a matched comparison; changing advice cannot inadvertently regenerate easier demand.

## How each passenger is measured

At generation, record the requested origin/destination, departure, initial route, and initial expected arrival on the undisrupted synthetic schedule. Freeze the boarding deadline at departure plus ten minutes and the arrival deadline at original ETA plus ten minutes. The initial ETA is never recalculated to excuse a later route or wait.

Track the person's or cohort's actual queue, movement, first transit boarding, transfer, reroute decision, and final arrival. A walk to another stop is movement but is not first boarding. An accepted detour must be feasible on graph connections and pass the predicted-ETA limit before execution. Its actual arrival is still measured against the original deadline; a favorable forecast is not a successful journey.

Final first-boarding and arrival success rates divide by every generated passenger. Unserved passengers fail the final targets, including those still in a queue or aboard when the simulation ends. In a live frame, distinguish pending targets from already-met or already-missed targets so future departures are not judged prematurely. Preserve conservation: generated = completed + queued + aboard, with any other explicit state included rather than silently dropped.

## Crowding: measure exposure throughout the network

Modeled density is queue passengers divided by the assumed queue area: bus 25 m², Metro 180 m², BART 400 m². Density above 1.5 persons/m² is the experiment's crowding threshold. Neither the areas nor threshold are empirical safety limits. A stop identifier is the queue area; distinct platforms/stop records should not be silently merged.

Crowding exposure adds queued passengers × elapsed minutes whenever that queue area exceeds the threshold. Report total exposure, peak density/queue, duration, and operator/neighborhood distribution. Also inspect vehicle occupancy and boardings. Reducing one highlighted queue while crowding grows elsewhere is insufficient evidence. Never infer low crowding from a station whose passengers were omitted or abandoned.

The interface must distinguish measured current queues/occupancy and completed arrival events from predicted future demand or ETA. Animated vehicle indicators show simulation movement, not GPS observations.

## Frozen city evaluator

Lower is better:

```text
J_city = 0.35 × (1 − boarding success fraction)
       + 0.35 × (1 − arrival success fraction)
       + 0.20 × exposure passenger-minutes / (generated passengers × 30)
       + 0.10 × max(0, net additional operating cost) / 20,000
       + 1,000 × unsafe/infeasible violations
```

Boarding success means first bus/rail boarding within ten minutes. Arrival success means final arrival by original ETA plus ten minutes. Zero generated demand must be handled explicitly rather than dividing by zero or presenting a fictitious success rate. Cost units and queue-area sizes remain documented synthetic assumptions.

This proposed `city-v2` evaluator is separate from Event Surge's preserved `objective-v1`. New scope warrants a new predefined experiment; it does not justify changing the historical evaluator or relabeling its improvement. Every run must store its evaluator version, weights, scenario, seed, controls, and complete harness configuration.

The fixed proposed city standby pool is 12 bus, four Metro, two BART, and one Caltrain vehicle/driver pairs. No architecture mutation can enlarge it, relax a deadline, increase advice compliance, reduce demand, change density assumptions, or alter scoring.

## Experiments that can support the claim

Run static timetable, operational agents with a fixed harness, and recursively evolving agents against identical city scenarios, demand scale, advice acceptance, random seeds, resources, and evaluation rules. Use separate development seeds for diagnosis and three predetermined promotion seeds plus a regression scenario for comparison. Keep the promotion gate independent from planner generation. Preserve rejected candidates and explain their actual measured reason.

Where runtime permits, isolate supply-only, guidance-only, and combined intervention. Sweep advice acceptance at 0%, 30%, 60%, and 90% while keeping all other inputs fixed. At 0%, advice cannot itself improve realized routes; this is a useful check that predictions are not being counted as completed outcomes. Supply-only performance helps distinguish architectural coordination benefits from merely deploying more vehicles.

Report the boarding and arrival target rates, their joint success, crowding exposure and distribution, served/unserved accounting, cost and resources, actual advice acceptance, and unsafe/infeasible actions. Show per-seed results as well as aggregates. An improved weighted score can hide a worsened outcome, so report every component.

The current adaptive loop reuses its promotion suite across iterations and shares acceptance/rejection history with the planner. That benchmark can support operational selection inside the experiment, but is not an independent final generalization test. Freeze the selected champion and evaluate untouched seeds before claiming that it generalizes. No ablation or compliance-sweep result is reported until actually executed.

## Verification before calling the city experiment complete

- Fixed seeds reproduce demand, acceptance, actions, and metrics.
- Every generated passenger remains explicitly accounted for.
- Vehicle occupancy and simultaneous reserves remain within limits.
- Supply suppression respects minimum service and availability.
- First boarding ignores walking, and rerouting never resets the original ETA/deadline.
- Advice alternatives use real graph edges, preserve destination, and satisfy the predicted detour bound.
- Zero acceptance executes no voluntary reroutes; matched runs retain the same underlying demand draws.
- Unserved passengers remain in final success denominators; pending live-frame targets are labeled correctly.
- Global crowding exposure includes all queues and cannot be improved by simply hiding a stop.
- Harness mutations change executable coordination/tool behavior; invalid configurations are rejected.
- An unfavorable candidate retains the incumbent, and the evaluator is unchanged across candidates.
- UI controls set inputs before a paired experiment and display real backend-generated events/metrics.
- Atlas readback preserves the scenario parameters, proposal, runs, evaluation, and decision.

## What a successful demonstration would show

Choose a commute load and voluntary-advice acceptance before starting. Watch where queues actually form, pick a passenger/cohort, and inspect original intent plus actual progress. Run fixed agents, evolve their harness, and replay the candidate with the same people. Show whether more people board within ten minutes and meet their original arrival allowance, where crowd exposure changed, and what resources/cost it required. End with the saved configuration difference and independent promotion/rejection in Atlas.

The thesis survives a rejection: an architecture hypothesis was made executable and tested against fixed journey outcomes. A credible positive result requires better measured outcomes without hidden changes to demand, deadlines, consent, or resources.
