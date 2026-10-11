# Three-minute live presentation

Start with `bash scripts/start.sh` and open `http://127.0.0.1:5175`. City Commute is the primary experiment. Its saved three-iteration result is **offline, rule-based** in `demo/evaluation-city-rules-offline.json`; new city Gemini-plus-Atlas verification is pending network access. Label the actual planner/store mode. Historical real-model/Atlas Event Surge evidence remains available separately. Public code: <https://github.com/jin-dalrae/bayflow>.

**0:00–0:25 — The journey.** “A commuter wants to board promptly and reach the same destination near their original ETA. BayFlow tests whether changing service and offering voluntary alternatives can improve those journeys.” Show the city map, 3,292 nodes and 8,369 links. Explain actual GTFS topology, August-expired schedule snapshots, and synthetic demand/operations; the moving indicators are simulation, not GPS.

**0:25–0:55 — The baseline.** Run or replay fixed City Commute, demand scale 1 and advice acceptance 60%. Inspect an actual passenger/cohort: origin, destination, frozen initial ETA, queue, first transit boarding, and arrival. Walking does not count as boarding. Show all 58 Muni bus routes participating and the measured 52.6688% boarding / 58.3239% arrival target rates.

**0:55–1:20 — What can change.** “Operational agents can dispatch limited standby vehicles or offer a valid optional detour. The harness can change how they coordinate, observe, prioritize, and plan.” Show tools, policy parameters and the declarative `incoming_transfer_hold` rule: observed incoming riders, threshold one, maximum two minutes. Resources, passenger deadlines, consent and scoring remain fixed.

**1:20–2:15 — Recursive testing.** Click **Evolve Harness** or inspect the actual completed artifact/history if runtime is too long. Show top failure edges and transfer waits, diagnosis, typed configuration diff, candidate execution, five paired seeds and fixed gate. “The first candidate really held departures: 233 triggers produced 74 holds totaling 97 minutes. The evaluator counted the consequences rather than accepting the planner's prediction.” Show rule/action telemetry and rejection. Explain that a hold changes one segment departure; downstream calendars remain fixed.

**2:15–2:45 — Actual decisions.** “The transfer hold worsened the mean objective 4.20%. The second hypothesis worsened it 5.84%. Faster regional replanning improved four of five seeds, but its mean gain was only 1.21%, below our unchanged 2% gate. All were rejected; v1 stayed active.” Show three distinct diffs, per-seed comparisons and retained champion. This is a working selection loop, not a manufactured win.

**2:45–3:00 — Audit proof.** If the new city Atlas run has actually completed, show its saved proposal/evaluation/deployment identifiers and live readback. Otherwise identify city evidence as offline and show **historical Event Surge** Gemini-plus-Atlas proof separately: model-generated v4 promoted 22.23% on its earlier three-seed suite, with a later labeled fallback rejected. Do not attribute that improvement to City Commute.

Keep the full evaluation recorded before presenting and disclose time compression. Inspect actual job stages rather than simulating progress. Do not show credentials. Never claim city LLM/Atlas deployment from a configured key or historical artifact alone.
