# One-minute recording

Only record after the real backend evaluation finishes and the Atlas indicator confirms read/write. Use the displayed measured values; do not substitute target improvements. If a mutation is rejected, show the rejection and explain its gate.

The public repository is <https://github.com/jin-dalrae/bayflow>. No video has been recorded or uploaded yet. Actual official Atlas integration and a persisted evolution run passed; inspect `demo/evaluation-atlas.json` and recheck the live indicator before recording. The separate `demo/evaluation-offline.json` remains an explicitly labeled reproducibility artifact.

`demo/evaluation-gemini-atlas.json` provides the strongest completed proof: real Gemini generated and promoted v4, while the second invalid model response triggered a labeled fallback whose v5 was rejected. Show the actual planner labels. The champion's seed-42 objective improved 21.33%, at operating cost 810 → 990; the mean promotion-suite improvement was 22.23%.

| Time | Screen | Exact narration |
| --- | --- | --- |
| 0–10 s | Transit network and project name | “BayFlow is an AI transit operations system that learns to redesign how it manages a city. Interconnected services need more than isolated dispatch decisions.” |
| 10–20 s | Fixed-agent replay; scrub to event surge | “This seeded, synthetic Bay Area evening combines fictional stadium crowds, a driver shortage, and a BART delay. Passenger queues and missed transfers come from a running simulator.” |
| 20–35 s | Click Evolve Harness; show proposal/configuration diff | “The planner reviews failure traces and proposes changes to the harness itself: its coordination, context, tools, and planning policy. A schema limits what can change.” |
| 35–50 s | Completed evaluation and adoption decision | “The backend reruns the candidate on matched seeds. An independent, fixed evaluator measures delay, transfers, congestion, and operating cost. The actual result determines whether the version is promoted or rejected.” |
| 50–60 s | Version history and Atlas records | “MongoDB Atlas preserves the proposal, simulations, evaluation, and decision for audit and rollback. BayFlow doesn't just optimize transit. It learns how to optimize.” |

Recording checklist:

- Use the organizer's Sandbox; show a successful persistence indicator and an actual Atlas document.
- Set browser zoom so proposal text and results are readable; hide terminals containing secrets.
- Record the complete evolution beforehand if model latency exceeds the shot; disclose edits/time compression.
- Mention the planner label shown by the UI: model-driven or rule-based fallback.
- Read only the actual result. Do not promise an accepted mutation before its gate completes.
- Keep raw footage, record screen plus voice, export approximately 60 seconds, and manually upload before submission.
- Confirm public repository URL and submission link manually; this file is a recording plan, not an uploaded video.
