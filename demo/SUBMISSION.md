# Submission evidence checklist

Deadline: Sunday, October 11, 2026, **5:00 PM America/Los_Angeles** (October 12, 00:00 UTC). Leave time for the participant to upload video and complete the organizer's form.

Public source: <https://github.com/jin-dalrae/bayflow>. The 22 isolated backend tests, real official Atlas integration check, frontend build, and two live browser checks passed. Actual offline and Atlas loop artifacts are `demo/evaluation-offline.json` and `demo/evaluation-atlas.json`. Official Sandbox read/write is verified. The current 79-second video is <https://youtu.be/oE6TcyYa9_c>. Live read-only demo: <https://bayflow.dalrae-jin-work.workers.dev>. Run `bash scripts/start.sh`, recheck live database status, record/upload the video, and complete the organizer's form.

A real Gemini 3.8 Flash proposal call also passed the opt-in model test; its actual output and token metadata are preserved in `demo/model-verification.json`. Distinguish this model-generation evidence from the preserved rule-based evaluated loop results.

The completed live Gemini-plus-Atlas run promoted model-generated v4 with 22.23% lower mean promotion-suite objective; the persisted decision and evaluation were retrieved through the history API. Iteration two encountered an invalid model response, used the explicitly labeled rule-based fallback, and rejected its v5 after a 14.26% objective regression. `demo/evaluation-gemini-atlas.json` preserves the actual job, decisions, database verification, and history readback. The champion's seed-42 objective improves 21.33% relative to fixed agents, with operating cost 810 → 990. Do not claim that both proposals came from the LLM.

- Confirm the URI is the organizer's Atlas Sandbox. Connectivity to another Atlas cluster does not establish eligibility.
- Verify `/database/status` reports `mode=atlas`, `connected=true`, and verified read/write.
- Run the default fixed-agent scenario, then evolve; preserve actual proposals, evaluation scores, and adopted/rejected decisions.
- Inspect an Atlas run document, trace, candidate version, evaluation, and deployment decision with matching identifiers.
- Verify UI actions call the backend and replay actual returned frames.
- Run Python tests and the frontend production build; record failures honestly.
- Check tracked files for secrets before public publication; `.env` and raw credentials must remain untracked.
- Verify the published repository URL opens without authentication. Include README, MIT license, reproducible commands, and synthetic-data labels.
- Record and upload the one-minute video. Include its actual URL, not the recording script's path.
- Add the actual public repository and video links to the submission form; do not imply this checklist submits it.

Suggested short submission description:

> BayFlow is a self-improving agent system for San Francisco transit. Operator agents for Muni, BART and Caltrain run a simulated commute on the real GTFS network. Harness agents (a service monitor, a Gemini planner, a validator, an evaluator and a promotion gate) watch whether riders board within ten minutes, propose one focused change to how the operators work, test it on five days it has never seen, and keep it only if it measurably wins. In our latest MongoDB Atlas run, Gemini proposed dispatching standby buses sooner; it won all five unseen days and was promoted, while the two changes Gemini tried next were rejected. Every agent message, version and decision is stored in Atlas, and the interface shows the live map beside a diagram of who told whom what. Rider demand is synthetic.

Use “model-driven” only when a completed proposal record confirms an actual model call. Replace the final persistence claim if official Sandbox integration is still unverified; an offline demonstration is not the required competition proof.
