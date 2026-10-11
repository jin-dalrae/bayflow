"""Run monitored operations and automatically review failures without an evolve command."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.store import Store
from backend.app.main import seed_store
from backend.app.automation import operate

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--offline',action='store_true')
    p.add_argument('--rule-based',action='store_true')
    p.add_argument('--horizon-minutes',type=int,default=720)
    p.add_argument('--iterations',type=int,default=3)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--output',type=Path)
    args=p.parse_args();store=Store(offline=args.offline);store.ensure();seed_store(store)
    r=operate(store,seed=args.seed,iterations=args.iterations,use_llm=not args.rule_based,horizon_minutes=args.horizon_minutes,progress=lambda stage:print(stage,file=sys.stderr,flush=True))
    summary={k:v for k,v in r.items() if k!='replay'}
    summary['database_verification']=store.status()
    summary['observed_metrics']=store.get('simulation_runs',r['observed_run_id'])['metrics']
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
