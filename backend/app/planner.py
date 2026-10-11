"""Model architecture reviewer, with an explicitly labeled offline rule planner."""

import json
import os
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .models import HarnessConfig, AGENTS, TOOLS


class MutationProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    diagnosis: str = Field(min_length=10, max_length=3000)
    rationale: str = Field(min_length=10, max_length=3000)
    expected_improvement: str = Field(min_length=5, max_length=1500)
    confidence: float = Field(ge=0, le=1)
    candidate: HarnessConfig


def diagnose(run):
    m = run["metrics"]
    return {
        "metrics": m,
        "accounting": run.get("accounting"),
        "observations": run["traces"][-35:],
        "failure_signals": {
            k: v
            for k, v in m.items()
            if any(
                word in k for word in ("missed", "unserved", "queue", "delay", "denial")
            )
        },
    }


def rule_plan(current, failure, history=None):
    candidate = current.model_dump()
    metrics = failure["metrics"]
    rejected_neighbor_policy = any(
        not h.get("accepted")
        and h.get("candidate", {}).get("context_policy") == "transfer_neighbors"
        for h in (history or [])
    )
    rejected_forecasting = any(
        not h.get("accepted")
        and "demand_forecast" in h.get("candidate", {}).get("active_tools", [])
        for h in (history or [])
    )
    has_delay = any(
        float(v) > 0
        for k, v in metrics.items()
        if ("missed" in k or "delay" in k) and isinstance(v, (float, int))
    )
    if (
        current.context_policy == "local_only"
        and has_delay
        and rejected_neighbor_policy
    ):
        candidate.update(
            coordination_mode="regional",
            context_policy="regional_shared",
            optimization_strategy="transfer_aware",
            replanning_interval_minutes=5,
            planning_horizon_minutes=60,
            verification_policy="strict",
        )
        candidate["active_agents"] = sorted(
            set(current.active_agents) | {"regional_coordinator"}
        )
        candidate["active_tools"] = sorted(
            set(current.active_tools)
            | {"regional_coordination", "transfer_optimizer", "feasibility_checker"}
        )
        diagnosis = "Delay remains and a neighbor-only coordination proposal was rejected. The narrow context and slow replanning may miss network-wide queue propagation."
        rationale = "Test regional shared observations and faster replanning, keeping the same physical fleet and frozen evaluator."
    elif current.context_policy == "local_only" and has_delay:
        candidate.update(
            coordination_mode="hub_and_spoke",
            context_policy="transfer_neighbors",
            optimization_strategy="transfer_aware",
        )
        candidate["active_agents"] = sorted(
            set(current.active_agents) | {"regional_coordinator"}
        )
        candidate["active_tools"] = sorted(
            set(current.active_tools)
            | {"regional_coordination", "transfer_optimizer", "feasibility_checker"}
        )
        candidate["verification_policy"] = "strict"
        diagnosis = "Delay and missed connections indicate that local agents cannot observe downstream transfer demand."
        rationale = "Share transfer-neighbor context and authorize a coordinator to synchronize connections within resource limits."
    elif (
        any(
            float(v) > 0
            for k, v in metrics.items()
            if ("unserved" in k or "delay" in k or "queue" in k)
            and isinstance(v, (float, int))
        )
        and "demand_forecast" not in current.active_tools
        and not rejected_forecasting
    ):
        candidate.update(
            coordination_mode="regional",
            context_policy="regional_shared",
            optimization_strategy="regional_predictive",
            planning_horizon_minutes=90,
            replanning_interval_minutes=5,
            memory_window_steps=18,
            verification_policy="strict",
        )
        candidate["active_agents"] = sorted(
            set(current.active_agents) | {"regional_coordinator", "demand_forecaster"}
        )
        candidate["active_tools"] = sorted(
            set(current.active_tools)
            | {
                "regional_coordination",
                "transfer_optimizer",
                "demand_forecast",
                "feasibility_checker",
            }
        )
        diagnosis = "Residual queues and delay persist after reactive dispatch; the controller lacks sufficient advance demand context."
        rationale = "Enable demand forecasting, a longer horizon and more frequent replanning to stage scarce reserves before observed scenario surges."
    else:
        candidate["replanning_interval_minutes"] = min(
            30, current.replanning_interval_minutes + 5
        )
        diagnosis = "The existing tool set already covers detected failures; frequent planning may consume resources without improving service."
        rationale = "Test a lower planning frequency. Independent evaluation will reject this change if passenger outcomes worsen."
    return MutationProposal(
        diagnosis=diagnosis,
        rationale=rationale,
        expected_improvement="Reduce the fixed passenger-delay and missed-transfer objective without violating fleet constraints.",
        confidence=0.65,
        candidate=HarnessConfig(**candidate),
    )


def propose(current, run, use_llm=True, history=None):
    failure = diagnose(run)
    provider = os.getenv("LLM_PROVIDER", "auto").lower()
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if provider == "auto":
        provider = "gemini" if gemini_key else "anthropic"
    if use_llm and provider == "gemini" and gemini_key:
        try:
            from google import genai
            from google.genai import types

            model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
            system = "You are the architecture reviewer for a transit multi-agent harness. Propose a full validated harness configuration based on measured development failures and prior proposal outcomes. Change architecture, tools, context, memory, horizon, replanning or strategy. Never modify evaluator weights, seeds, demand, physical constraints or executable code. Do not repeat rejected proposals. Explain a falsifiable hypothesis; do not describe expected gains as measured results."
            payload = {
                "current": current.model_dump(),
                "development_failure": failure,
                "mutation_history": history or [],
                "available_agents": sorted(AGENTS),
                "available_tools": sorted(TOOLS),
                "constraints": "Three shared Muni standby vehicle/driver pairs; no extra BART or Caltrain fleet. Regional coordination needs regional_coordinator, demand_forecast needs demand_forecaster. Held-out scores unavailable to planner.",
            }
            with genai.Client(
                api_key=gemini_key,
                http_options=types.HttpOptions(
                    timeout=45000, retry_options=types.HttpRetryOptions(attempts=1)
                ),
            ) as client:
                response = client.models.generate_content(
                    model=model,
                    contents=json.dumps(payload),
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        response_mime_type="application/json",
                        response_json_schema=MutationProposal.model_json_schema(),
                        max_output_tokens=4096,
                    ),
                )
            proposal = MutationProposal.model_validate_json(response.text)
            usage = response.usage_metadata
            return proposal, {
                "kind": "llm",
                "provider": "gemini",
                "model": response.model_version or model,
                "requested_model": model,
                "input_tokens": usage.prompt_token_count if usage else None,
                "output_tokens": usage.candidates_token_count if usage else None,
                "thinking_tokens": usage.thoughts_token_count if usage else None,
            }
        except Exception as exc:
            message = str(getattr(exc, "message", ""))[:600]
            for name in (
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "ANTHROPIC_API_KEY",
                "MONGODB_URI",
            ):
                secret = os.getenv(name)
                if secret:
                    message = message.replace(secret, "[redacted]")
            return rule_plan(current, failure, history), {
                "kind": "rule_based",
                "requested_provider": "gemini",
                "fallback_reason": f"Gemini unavailable or invalid response ({type(exc).__name__})",
                "provider_error": message,
            }
    if use_llm and provider == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
        try:
            import anthropic

            client = anthropic.Anthropic(timeout=45, max_retries=0)
            response = client.messages.create(
                model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
                max_tokens=2400,
                system="You review an agent harness architecture for a simplified transit simulator. Propose configuration changes based only on measured development-run failures. Change agent topology, tools, context, memory, planning or verification. Never change evaluation weights, scenario demand, seeds, safety constraints or code. Return a full valid candidate configuration using the provided tool. Model v1 is functional. Avoid gratuitous changes. Do not claim improvements as measured before evaluation.",
                messages=[
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "current": current.model_dump(),
                                "development_failure": failure,
                                "mutation_history": history or [],
                                "available_agents": sorted(AGENTS),
                                "available_tools": sorted(TOOLS),
                                "constraints": "Shared pool of three Muni standby vehicle/driver pairs; no additional BART or Caltrain standby capacity. Resources remain enforced by simulator; held-out scores not available to planner. Do not repeat rejected proposals.",
                            }
                        ),
                    }
                ],
                tools=[
                    {
                        "name": "propose_harness",
                        "description": "Propose a schema-constrained harness architecture mutation for independent evaluation.",
                        "input_schema": MutationProposal.model_json_schema(),
                    }
                ],
                tool_choice={"type": "tool", "name": "propose_harness"},
            )
            blocks = [
                block
                for block in response.content
                if block.type == "tool_use" and block.name == "propose_harness"
            ]
            if len(blocks) != 1:
                raise ValueError("Expected exactly one proposal")
            proposal = MutationProposal.model_validate(blocks[0].input)
            return proposal, {
                "kind": "llm",
                "provider": "anthropic",
                "model": response.model,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
        except Exception as exc:
            detail = getattr(exc, "body", {})
            message = (
                detail.get("error", {}).get("message", "")
                if isinstance(detail, dict)
                else ""
            )
            if not message and isinstance(detail, dict):
                message = detail.get("message", "")
            message = str(message)[:600]
            for name in ("ANTHROPIC_API_KEY", "MONGODB_URI"):
                secret = os.getenv(name)
                if secret:
                    message = message.replace(secret, "[redacted]")
            return rule_plan(current, failure, history), {
                "kind": "rule_based",
                "fallback_reason": f"Model unavailable or invalid response ({type(exc).__name__})",
                "provider_error": message,
            }
    return rule_plan(current, failure, history), {
        "kind": "rule_based",
        "fallback_reason": "No model API key, or deterministic planner explicitly selected.",
    }
