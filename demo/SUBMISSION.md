# Submission evidence checklist

Deadline: Sunday, October 11, 2026, **5:00 PM America/Los_Angeles** (October 12, 00:00 UTC). Leave time for the participant to upload video and complete the organizer's form.

Public source: <https://github.com/jin-dalrae/bayflow>. Backend tests and frontend build passed; actual offline loop results are in `demo/evaluation-offline.json`. Official Atlas Sandbox read/write is still unverified due to restricted build networking. No video has been recorded or uploaded. Run `bash scripts/start.sh` in a local network-enabled terminal to resolve database verification before claiming submission readiness.

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

> BayFlow is an experimental self-evolving transit agent harness. A seeded Bay Area simulation exposes coordination failures. A model-driven or explicitly labeled rule-based architecture planner changes a validated harness configuration, then an independent evaluator reruns candidate architectures on held-out seeds. Automatic promotion/rejection and rollback are audited in the organizer's MongoDB Atlas Sandbox. The interface replays passenger queues and makes agent topology, tools, context, and version decisions inspectable. All transit demand and disruptions in the default demo are synthetic.

Use “model-driven” only when a completed proposal record confirms an actual model call. Replace the final persistence claim if official Sandbox integration is still unverified; an offline demonstration is not the required competition proof.
