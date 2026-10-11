"""Backend-owned failure monitor. Trigger thresholds are outside the editable harness."""
from uuid import uuid4
from .evolution import current_config,execute_run,evolve
from .store import now

MONITOR={"version":"journey-monitor-v1","window_minutes":30,"check_interval_minutes":15,
         "minimum_matured_intents":200,"boarding_success_floor":.80,
         "density_threshold":1.5,"crowded_queue_minimum":200,"consecutive_failures":2}


def detect_failure(run):
    """Find first persistent failure using only observations available at each check.

    The monitor looks at completed ten-minute boarding deadlines, not brand-new
    requests. Groups can split across vehicles; first-boarding event counts sum.
    """
    if run.get('scenario') in {'event_surge','commuter','accident'}:
        metrics=run['metrics']
        bad=metrics.get('average_passenger_delay',0)>10 or metrics.get('unserved_passengers',0)/max(1,metrics.get('generated_passengers',1))>.05
        if not bad:return None
        return dict(source='backend_failure_monitor',monitor_version='compact-delay-monitor-v1',minute=run['frames'][-1]['minute'],reason='Measured compact-scenario average delay exceeds ten minutes or more than five percent of passengers remain unserved.',source_run_id=run['run_id'],harness_version=run['harness_version'],observations=[dict(average_passenger_delay=metrics.get('average_passenger_delay'),unserved_passengers=metrics.get('unserved_passengers'))])
    catalog={g['cohort_id']:g for g in run.get('passenger_groups',[])}
    boarded={};consecutive=0;observations=[]
    for frame in run['frames']:
        minute=frame['minute']
        for event in frame.get('passenger_events',[]):
            if event.get('action')=='boarded' and event.get('first_boarding'):
                group=catalog[event['cohort_id']]
                if event['minute']<=group['born']+10:
                    boarded[event['cohort_id']]=boarded.get(event['cohort_id'],0)+event['count']
        if minute<30 or minute%MONITOR['check_interval_minutes']:continue
        matured=[g for g in catalog.values() if minute-40<g['born']<=minute-10]
        count=sum(g['count'] for g in matured)
        if count<MONITOR['minimum_matured_intents']:consecutive=0;continue
        rate=sum(min(g['count'],boarded.get(g['cohort_id'],0)) for g in matured)/count
        crowded=frame.get('passenger_service',{}).get('crowded_locations',[])
        crowd_failure=sum(c['count'] for c in crowded if c['density']>MONITOR['density_threshold'])>=MONITOR['crowded_queue_minimum']
        bad=rate<MONITOR['boarding_success_floor'] or crowd_failure
        consecutive=consecutive+1 if bad else 0
        observation=dict(minute=minute,matured_intents=count,boarding_within_10_rate=round(rate,6),crowded_waiting_riders=sum(c['count'] for c in crowded),failure=bad)
        observations.append(observation)
        if consecutive>=MONITOR['consecutive_failures']:
            return dict(source='backend_failure_monitor',monitor_version=MONITOR['version'],minute=minute,reason='Riders missed the 10-minute boarding target or faced crowding at two consecutive checks.',observations=observations[-2:],monitor=MONITOR,source_run_id=run['run_id'],harness_version=run['harness_version'])
    return None


def operate(store,seed=42,iterations=3,use_llm=True,progress=lambda stage:None,scenario='city_commute',benchmark_scope=None,**parameters):
    scope=benchmark_scope or (scenario if parameters.get("city_profile","standard")=="standard" else f"{scenario}:{parameters["city_profile"]}")
    config=current_config(store,scenario=scope)
    progress('Monitoring passenger journeys with the current harness')
    observed=execute_run(store,config,seed,'evolving',scenario,**parameters)
    progress('Checking mature boarding deadlines and persistent crowding')
    trigger=detect_failure(observed)
    record=dict(benchmark_scope=scope,operation_id=str(uuid4()),scenario=scenario,scenario_parameters=parameters,observed_run_id=observed['run_id'],harness_version=config.version,automatic_trigger=trigger,monitor=MONITOR,created_at=now(),status='triggered' if trigger else 'healthy')
    store.put('automation_events',record['operation_id'],record)
    if trigger:
        progress(f"Automatic review triggered at simulation minute {trigger['minute']}")
        result=evolve(store,seed,iterations,use_llm,progress,scenario=scenario,automatic_trigger=trigger,benchmark_scope=scope,**parameters)
        record.update(status='completed',mutation_ids=[d['mutation_id'] for d in result['decisions']],final_harness_version=result['current']['version'])
    else:
        progress('Monitor passed; retaining harness without a mutation request')
        result=dict(current=config.model_dump(),decisions=[],replay=observed,run_ids={'observed':observed['run_id']},persistence=observed['persistence'])
    store.put('automation_events',record['operation_id'],record)
    return dict(result,automatic_trigger=trigger,operations=record,observed_run_id=observed['run_id'])
