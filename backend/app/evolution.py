"""Recursive architecture loop. Frozen evaluator and held-out gates never enter planner."""
from statistics import mean
from uuid import uuid4
from .models import HarnessConfig
from .simulator import simulate, EVALUATOR
from .planner import propose
from .store import now


def execute_run(store, config, seed, mode='fixed', scenario='event_surge'):
    result = simulate(config, seed=seed, mode=mode, scenario=scenario)
    result.update(run_id=str(uuid4()), harness_version=config.version, started_at=now(), mode=mode,
                  persistence='offline_preview' if store.offline else 'atlas')
    store.save_run(result)
    return result


def initialize(store):
    if not store.get('control', 'active_harness'):
        config = HarnessConfig()
        store.put('harness_versions', config.version, {'version': config.version, 'config': config.model_dump(), 'parent_version': None, 'mutation_summary': 'Initial decentralized functional harness', 'eligible': not store.offline})
        store.put('control', 'active_harness', {'version': config.version})


def current_config(store):
    initialize(store)
    pointer = store.get('control', 'active_harness')
    return HarnessConfig.model_validate(store.get('harness_versions', pointer['version'])['config'])


def aggregate(runs):
    metrics = [run['metrics'] for run in runs]
    return {k: round(mean(float(m[k]) for m in metrics), 6) for k in metrics[0] if isinstance(metrics[0][k], (int, float))}


def objective(metrics):
    for key in ('objective', 'objective_score', 'fitness', 'score'):
        if key in metrics:
            return metrics[key]
    raise ValueError('Simulator did not report fixed evaluator objective')


def promotion_gate(before, after, candidate_runs, control_before, control_after):
    improvement = (objective(before) - objective(after)) / max(objective(before), 1e-9)
    violations = sum(r['metrics'].get('feasibility_violations', r['metrics'].get('unsafe_actions', 0)) + r['metrics'].get('capacity_violations', 0) for r in candidate_runs)
    safe = violations == 0
    regression = objective(control_after) <= objective(control_before) * 1.05 + 1e-9
    accepted = improvement >= .02 and safe and regression
    reason = ('Promoted: held-out objective improved by at least 2%, feasibility passed and commuter regression stayed within 5%.' if accepted else
              'Rejected: ' + '; '.join(x for test, x in [(improvement >= .02, 'held-out improvement below 2%'), (safe, 'feasibility violation'), (regression, 'commuter objective regression exceeds 5%')] if not test))
    return accepted, reason, improvement * 100


def evolve(store, seed=42, iterations=2, use_llm=True, progress=lambda stage: None):
    current = current_config(store)
    original = current
    decisions = []
    # Development seed is disjoint from fixed evaluation suite, chosen before any proposal.
    eval_seeds = [seed + 1001, seed + 2003, seed + 3001]
    for iteration in range(iterations):
        progress(f'Analyzing failure traces · iteration {iteration + 1}')
        development = execute_run(store, current, seed, 'evolving')
        progress('Proposing architecture mutation')
        history = [{'candidate': h['candidate'], 'accepted': h.get('accepted', False)} for h in store.list('mutation_proposals', limit=1000) if h.get('status') in ('promoted', 'rejected')][-current.memory_window_steps:]
        proposal, planner = propose(current, development, use_llm, history)
        versions = store.list('harness_versions', limit=10000)
        version = 'v' + str(max(int(v['version'][1:]) for v in versions) + 1)
        candidate = HarnessConfig.model_validate(dict(proposal.candidate.model_dump(), version=version))
        mutation_id = str(uuid4())
        record = {'mutation_id': mutation_id, 'proposal': proposal.model_dump(), 'candidate': candidate.model_dump(), 'parent_version': current.version, 'planner': planner, 'development_run_id': development['run_id'], 'status': 'validated', 'evaluation_seeds': eval_seeds, 'evaluator': EVALUATOR}
        record['proposal']['candidate'] = candidate.model_dump()
        store.put('mutation_proposals', mutation_id, record)
        progress('Validating candidate configuration and safety envelope')
        before_runs, after_runs = [], []
        for index, held_seed in enumerate(eval_seeds):
            progress(f'Running held-out evaluation · seed {index + 1}/{len(eval_seeds)}')
            before_runs.append(execute_run(store, current, held_seed, 'evolving'))
            after_runs.append(execute_run(store, candidate, held_seed, 'evolving'))
        control_before = execute_run(store, current, seed + 5003, 'evolving', 'commuter')
        control_after = execute_run(store, candidate, seed + 5003, 'evolving', 'commuter')
        before, after = aggregate(before_runs), aggregate(after_runs)
        progress('Comparing results against frozen promotion gates')
        accepted, reason, improvement = promotion_gate(before, after, after_runs + [control_after], control_before['metrics'], control_after['metrics'])
        evaluation = {'evaluation_id': mutation_id, 'before': before, 'after': after, 'accepted': accepted, 'reason': reason, 'improvement_percent': improvement, 'evaluation_seeds': eval_seeds, 'control_before': control_before['metrics'], 'control_after': control_after['metrics'], 'run_ids': [r['run_id'] for r in before_runs + after_runs + [control_before, control_after]], 'evaluator': EVALUATOR}
        store.put('evaluation_results', mutation_id, evaluation)
        store.put('harness_versions', version, {'version': version, 'config': candidate.model_dump(), 'parent_version': current.version, 'mutation_summary': proposal.rationale, 'accepted': accepted, 'evaluation_id': mutation_id, 'eligible': not store.offline})
        progress('Promoting candidate' if accepted else 'Rejecting candidate; retaining current harness')
        # Audit writes precede pointer activation; never promote an unevaluated candidate.
        record.update(status='promoted' if accepted else 'rejected', accepted=accepted, reason=reason)
        store.put('mutation_proposals', mutation_id, record)
        store.put('deployment_decisions', mutation_id, {'version': version, 'parent_version': current.version, 'accepted': accepted, 'reason': reason, 'evaluation_id': mutation_id})
        if accepted:
            store.put('control', 'active_harness', {'version': version, 'evaluation_id': mutation_id})
            current = candidate
        store.put('agent_memory', mutation_id, {'failure_summary': proposal.diagnosis, 'architecture_rationale': proposal.rationale, 'accepted': accepted, 'source_run_id': development['run_id']})
        decisions.append(dict(record, **{k: evaluation[k] for k in ('before', 'after', 'improvement_percent')}))
    progress('Running three-way comparison on identical scenario and seed')
    static = execute_run(store, HarnessConfig(), seed, 'static')
    fixed = execute_run(store, HarnessConfig(), seed, 'fixed')
    final = execute_run(store, current, seed, 'evolving')
    return {'current': current.model_dump(), 'initial': original.model_dump(), 'decisions': decisions,
            'comparison': {'static': static['metrics'], 'fixed': fixed['metrics'], 'evolved': final['metrics']},
            'run_ids': {'static': static['run_id'], 'fixed': fixed['run_id'], 'evolved': final['run_id']},
            'replay': final, 'evaluation_seeds': eval_seeds, 'evaluator': EVALUATOR,
            'persistence': 'offline_preview' if store.offline else 'atlas'}
