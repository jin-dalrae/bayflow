# Judge questions

**Why is this recursive harnessing?** Ordinary dispatch actions change resource allocation within an architecture. BayFlow separately changes the architecture's validated configuration: active agents/tools, coordination mode, context policy, planning horizon, replanning interval, memory window, verification, and optimization strategy. It reruns the candidate and independently decides whether to promote it. Inspect a proposal, its configuration diff, and matching evaluation records.

**What does the LLM decide?** When configured and reachable, Gemini or Anthropic receives the current configuration, measured development failures, and proposal outcome history, then proposes a bounded configuration mutation with rationale. Gemini returns structured JSON through Google's official SDK; Pydantic validates it. The model does not calculate passenger movement or fitness. When unavailable, the visibly labeled rule-based planner chooses changes from observed failures. No generated Python is executed. The preserved demonstration evaluation artifacts used the rule-based planner; provider configuration alone does not establish a successful model call.

The real Gemini 3.8 Flash proposal integration test passed. `demo/model-verification.json` contains its actual validated candidate and model/token metadata. This verifies model generation independently from the rule-based measured comparison artifacts; it does not by itself establish that the model candidate improved performance.

The subsequent live Gemini-plus-Atlas run also completed: its model-generated v4 was promoted after a 22.23% reduction in mean promotion-suite objective, and its persisted proposal/evaluation decision was retrieved from Atlas through the API. On iteration two, the model response failed Pydantic validation; the visibly labeled rule-based fallback proposed v5, which worsened the objective 14.26% and was rejected. `demo/evaluation-gemini-atlas.json` preserves this complete model-driven cycle and honest fallback/rejection history. It does not show two valid LLM-generated proposals.

**What is deterministic?** Seeded demand, the interval simulator, queues, paths, capacity limits, disruptions, operational policy execution, metric calculations, and promotion gates. Model proposals can vary; stored configurations make their simulations reproducible.

**How is improvement measured?** Compare static timetable, fixed agents, and evolving agents using identical scenario seeds and immutable objective weights. The README defines reference delay and the score. Report actual results and additional operating cost; an unfavorable candidate is rejected.

In the preserved rule-based offline run, v2 was rejected and v3 was promoted. On seed 42 the evolved objective improved 21.33% relative to fixed agents, with operating cost rising 810 to 990. The promotion suite mean improved 22.23%. Transfer failures did not improve and capacity-denial counts rose. Reusing the suite across adaptive iterations limits generalization claims.

**How do you prevent evaluator gaming?** Evaluator settings are outside the mutable harness schema. Unknown keys and unsupported tools/agents are rejected. A candidate cannot change its scenario, scoring weights, or random seed through its harness configuration. Feasibility and performance gates are separate from proposal generation.

**Why MongoDB?** Atlas is the system of record linking scenarios, traces, proposal inputs, complete candidate versions, evaluation results, and deployment decisions. Version history and rollback require this state; the UI reports real database health. Explicit offline preview is development-only and does not satisfy the hackathon requirement.

The real official Sandbox integration check passed, as did a live persisted recursive run. `demo/evaluation-atlas.json` contains actual Atlas-backed identifiers, measured results, and verification. Persisted proposal/configuration/evaluation joins remain inspectable after browser reload. The separate offline artifact is still labeled correctly and is not Atlas evidence.

**How realistic is the simulator?** Real Bay Area places and transfers anchor a deliberately simplified corridor model. Demand, events, headways, travel times, fleet budgets, and capacities are synthetic. Vehicles are segment departure/capacity abstractions, not a complete physical fleet blocking model. These findings are experimental, not operational transit advice.

**Can it generalize?** The harness/evaluator separation can be reused, but another city needs a valid graph, calibrated demand, realistic constraints, and independent evaluation. BayFlow does not claim empirical transferability from its synthetic scenario.

**How are unsafe changes prevented?** Typed allowlists, bounded numerical fields, required companion agents for tools, deterministic resource limits, and independent feasibility checks constrain candidates. Actions run only in the simulator. There is no connection to real dispatch control.

**What was built today?** The new simulator, validated harness, planner/fallback, evaluation and promotion loop, persistence API, interactive inspector, tests, optional importer, and documentation were authored in this repository during the build. Dependencies are standard open-source libraries; manually chosen real station geography and optional third-party data are identified separately.
