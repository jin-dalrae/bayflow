# One-minute recording

**Current video (v36, 79 s):** recorded from the live read-only site <https://bayflow.dalrae-jin-work.workers.dev>, which replays the stored MongoDB Atlas run under `city-intent-v3`. Uploaded at <https://youtu.be/oE6TcyYa9_c>. Narration, every figure from that run: the service monitor triggered at 4:45 PM with 70% of matured riders boarded within ten minutes (target 80%); Gemini 3.8 Flash, citing earlier bundled failures, proposed one change (local dispatch trigger 1.2 → 0.8); it won all five unseen days (+3.04%) and was promoted as v36; held-out boarding within ten minutes rose 68.9% → 69.9% and on-time arrivals 75.4% → 76.4%; Gemini's next two changes were rejected.

**Earlier video (64 s, superseded):** recorded before the planner, demand and evaluator fixes; its rule-based candidates were all rejected and v1 stayed active.

The table below is the earlier recording plan.

Use the actual completed `demo/evaluation-city-rules-offline.json`, labeled rule-based/offline, until a real city Gemini-plus-Atlas artifact exists. Historical Event Surge external proof is `demo/evaluation-gemini-atlas.json`; its promotion is not a city result.

| Time | Screen | Exact narration |
| --- | --- | --- |
| 0–10 s | City map / passenger inspector | “BayFlow tests how to help commuters board within ten minutes and arrive near their original ETA. The geography is imported GTFS; passengers and operations are synthetic.” |
| 10–20 s | First boarding / frozen ETA / crowding | “We measure actual boarding, arrivals, and crowd exposure. Service changes and voluntary detours must respect destinations, deadlines, consent, and fixed resources.” |
| 20–35 s | Evolve / typed rule diff / action telemetry | “The harness rewrites its coordination, policies, and typed rules. This candidate really held departures: seventy-four holds, ninety-seven minutes. Ordinary code simulates every consequence.” |
| 35–50 s | Three candidates / paired-seed gate | “Five paired seeds rejected the hold and another service policy. Faster planning won four seeds, but its one-point-two-percent mean gain missed the unchanged two-percent gate. The original version stayed active.” |
| 50–60 s | Evidence / planner and persistence labels | “This completed city result is offline and rule-based. Historical Event Surge records separately prove real Gemini mutation and Atlas persistence. BayFlow tests how it learns to optimize.” |

If the city Atlas/model run finishes before recording, replace the final sentence only with its **actual** planner, result and persisted readback. Do not invent a promotion or describe a fallback as model-generated.

Recording checklist:

- Pre-run the genuine evaluation; show real results and disclose edited/time-compressed waiting.
- Keep metric text, rule diffs and planner/store labels readable.
- Show the original ETA remains fixed after advice; distinguish predictions from arrivals.
- Avoid terminals or UI panels containing credentials.
- Include the failed hypotheses and unchanged gate; rejection demonstrates automatic version selection.
- If showing Atlas, identify whether records belong to the new city run or historical Event Surge.
- Keep raw footage, export approximately 60 seconds, upload manually, and supply the actual video link.
