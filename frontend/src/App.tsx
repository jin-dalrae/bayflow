import { useEffect, useMemo, useRef, useState } from "react";
import TransitMap from "./TransitMap";
import EvolutionHistory from "./EvolutionHistory";
import PassengerInspector from "./PassengerInspector";
import { Rulebook, MutationDiff } from "./Rulebook";
import AgentFlow, { buildLoopMessages } from "./AgentFlow";
import AgentDiagram from "./AgentDiagram";
import { narrate, agentName } from "./narrate";
import { STATIC, endpoint } from "./snapshot";
type Data = Record<string, any>;
const colors: Record<string, string> = {
  muni: "#e9b168",
  muni_bus: "#e9b168",
  muni_metro: "#b6a4ef",
  bart: "#75c7f2",
  caltrain: "#df8290",
  walk: "#637b75",
  walking: "#637b75",
};
const color = (s: string = "") =>
  colors[s.toLowerCase().replace(/ /g, "_")] || "#96b5a9";
const num = (v: any, d = 0) => (Number.isFinite(Number(v)) ? Number(v) : d);
const fmt = (v: any) =>
  v === undefined || v === null
    ? "—"
    : num(v).toLocaleString(undefined, { maximumFractionDigits: 1 });
const time = (m: any) => {
  const elapsed = 960 + num(m), day = Math.floor(elapsed / 1440), t = ((elapsed % 1440) + 1440) % 1440;
  return `${Math.floor(t / 60) % 12 || 12}:${String(Math.floor(t % 60)).padStart(2, "0")} ${t >= 720 ? "PM" : "AM"}${day > 0 ? ` · day +${day}` : ""}`;
};
async function api(path: string, body?: Data) {
  if (STATIC && body) throw Error("This is a static snapshot of stored Atlas records. Run BayFlow locally to start new simulations.");
  const r = await fetch(
    endpoint(path),
    body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : undefined,
  );
  let d: any;
  try { d = await r.json(); } catch { throw Error(`Backend response unavailable for ${path}. Restart the backend with scripts/start.sh, then reload this page.`); }
  if (STATIC && !r.ok) throw Error(`Not included in this static snapshot: ${path.split("?")[0]}`);
  if (r.status === 404 || r.status === 405) throw Error(`This backend does not support ${path.split("?")[0]}. Restart the backend with scripts/start.sh to load the current API, then reload this page.`);
  if (!r.ok)
    throw Error(
      typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail || d),
    );
  return d;
}
function Icon({ name }: { name: string }) {
  return (
    <span aria-hidden="true" className="icon">
      {name === "play"
        ? "▶"
        : name === "pause"
          ? "Ⅱ"
          : name === "evolve"
            ? "✧"
            : name === "back"
              ? "↶"
              : name === "arrow"
                ? "↗"
                : "◈"}
    </span>
  );
}
export default function App() {
  const [network, setNetwork] = useState<Data>({ nodes: [], edges: [] }),
    [db, setDb] = useState<Data>({ connected: false }),
    [harness, setHarness] = useState<Data>({}),
    [versions, setVersions] = useState<Data[]>([]),
    [historicalDecisions, setHistoricalDecisions] = useState<Data[]>([]),
    [run, setRun] = useState<Data | null>(null),
    [result, setResult] = useState<Data | null>(null),
    [job, setJob] = useState<Data | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [harnessError,setHarnessError] = useState(""),
    [offline, setOffline] = useState(() => new URLSearchParams(window.location.search).get("offline") === "true"),
    [frameIndex, setFrameIndex] = useState(0),
    [playing, setPlaying] = useState(false),
    [selected, setSelected] = useState<string | null>(null),
    [trackedPassenger, setTrackedPassenger] = useState<string | null>(null),
    [mode, setMode] = useState("fixed"),
    [seed, setSeed] = useState(42),
    [demandScale, setDemandScale] = useState(1),
    [advisoryAcceptance, setAdvisoryAcceptance] = useState(.6),
    [scenarios, setScenarios] = useState<Data[]>([]),
    [scenario, setScenario] = useState("city_commute"),
    [useLlm, setUseLlm] = useState(true),
    [horizonMinutes,setHorizonMinutes] = useState(720),
    [action,setAction] = useState(""),
    [candidate,setCandidate] = useState<Data | null>(null),
    [historyPage,setHistoryPage] = useState(window.location.hash === "#history");
  useEffect(()=>{const change=()=>setHistoryPage(window.location.hash === "#history");window.addEventListener("hashchange",change);return()=>window.removeEventListener("hashchange",change);},[]);
  const alive = useRef(true);
  const requestGeneration = useRef(0);
  const previewPath = (p: string) => (offline ? `${p}${p.includes("?") ? "&" : "?"}offline=true` : p);
  const refresh = async () => {
    const generation = ++requestGeneration.current;
    const requests = [
      [`/network?scenario=${encodeURIComponent(scenario)}&horizon_minutes=${horizonMinutes}`, setNetwork],
      [previewPath("/database/status"), setDb],
      [previewPath(`/harness/current?scenario=${encodeURIComponent(scenario)}`), (d: Data) => {setHarness(d.config || d);setHarnessError(d.persisted===false ? "The active harness could not be verified in persistence. Check Atlas connectivity before running an official experiment." : "");}],
      [previewPath(`/harness/versions?scenario=${encodeURIComponent(scenario)}`), (d: any) => setVersions(Array.isArray(d) ? d : d.versions || [])],
      ["/scenarios", (d: any) => setScenarios(Array.isArray(d) ? d : d.scenarios || [])],
      [previewPath("/harness/proposals"), (d: any) => setHistoricalDecisions(Array.isArray(d) ? d : d.proposals || [])],
    ] as const;
    await Promise.allSettled(requests.map(async ([path, apply], index) => {
      try {
        const data = await api(path);
        if (alive.current && generation === requestGeneration.current) apply(data);
      } catch {
        if(index === 2 && alive.current && generation === requestGeneration.current) setHarnessError("Active harness unavailable. Check the backend and Atlas connection, then reload. Displayed controls are defaults until a persisted configuration is retrieved.");
        if (index === 0 && alive.current && generation === requestGeneration.current)
          setError("Backend unavailable. Start the FastAPI server on port 8000.");
      }
    }));
  };
  useEffect(() => {
    alive.current = true;
    setHistoricalDecisions([]);
    setResult(null);
    setRun(null);
    setCandidate(null);
    setJob(null);
    setPlaying(false);
    setFrameIndex(0);
    setTrackedPassenger(null);
    void refresh().then(async () => {
      // Start with the latest stored operating window so the map is moving on arrival.
      if (STATIC) {
        try {
          const operation = await api(`/snapshot-operation?scenario=${encodeURIComponent(scenario)}`);
          if (!alive.current) return;
          setResult(operation);
          setAction("operations");
          if (operation.current) setHarness(operation.current.config || operation.current);
          setRun(operation.replay);
          setFrameIndex(0);
          setPlaying(true);
          return;
        } catch {}
      }
      try {
        const events: Data[] = await api(previewPath("/operations/history"));
        const latest = (Array.isArray(events) ? events : []).filter(e => e.scenario === scenario && e.observed_run_id).slice(-1)[0];
        if (!latest || !alive.current) return;
        const stored = await api(previewPath(`/simulation/${latest.observed_run_id}`));
        if (!alive.current) return;
        setRun(current => current || stored);
        setFrameIndex(0);
        setPlaying(true);
      } catch {}
    });
    const t = setInterval(() => {
      const generation = requestGeneration.current;
      void api(previewPath("/database/status")).then(data => {
        if (alive.current && generation === requestGeneration.current) setDb(data);
      }).catch(() => {});
    }, 10000);
    return () => {
      alive.current = false;
      requestGeneration.current++;
      clearInterval(t);
    };
  }, [offline, scenario, horizonMinutes]);
  const shown: Data | null = candidate?.run || run;
  const trackedPath: string[] = useMemo(()=>shown?.passenger_groups?.find((group:Data)=>group.cohort_id===trackedPassenger)?.path || [],[shown,trackedPassenger]);
  const frames: Data[] = shown?.frames || [];
  const frame = frames[frameIndex] || {};
  const recordedTraces: Data[] = useMemo(() => (shown?.traces || []).filter((trace: Data) => num(trace.minute) <= num(frame.minute)), [shown, frame.minute]);
  const interventions = recordedTraces.filter(trace => trace.action !== "observe" && trace.action !== "boarding_denied").slice(-6).reverse();
  const activeDispatchEdges = new Set(recordedTraces.filter(trace => trace.action === "standby_dispatch" && trace.tool !== "operating_rule" && num(trace.minute) === num(frame.minute)).map(trace => trace.edge_id));
  useEffect(() => {
    if (!playing || !frames.length) return;
    const t = setInterval(
      () =>
        setFrameIndex((i) => {
          if (i >= frames.length - 1) return 0;
          return i + 1;
        }),
      100,
    );
    return () => clearInterval(t);
  }, [playing, frames.length]);
  async function launch(path: string, body: Data) {
    setError("");
    setBusy(true);
    setTrackedPassenger(null);
    setCandidate(null);
    setAction(path.includes("operations") ? "operations" : path.includes("evolve") ? "evolve" : path.includes("rollback") ? "rollback" : "baseline");
    setJob({ status: "pending", stage: "Starting real backend evaluation", history: [] });
    try {
      let d = await api(path, { ...body, offline });
      if (d.job_id) {
        const jobId = d.job_id;
        for (;;) {
          await new Promise((r) => setTimeout(r, 650));
          d = await api(`/jobs/${jobId}`);
          setJob(d);
          if (d.status === "failed")
            throw Error(d.error || "Evaluation failed");
          if (d.status === "completed" || d.status === "complete") {
            d = d.result;
            break;
          }
          if (!alive.current) return;
        }
      }
      if (path.includes("rollback")) {
        setHarness(d.config || d.current || d);
        setJob({ status: "completed", stage: "Historical harness restored" });
      } else if ((path.includes("evolve") || path.includes("operations/start"))) {
        setResult(d);
        if (d.current) setHarness(d.current.config || d.current);
        if (d.replay || d.run || d.evolved_run) {
          setRun(d.replay || d.run || d.evolved_run);
          if(scenario === "city_commute") setTrackedPassenger((d.replay || d.run || d.evolved_run).passenger_groups?.[0]?.cohort_id || null);
          setFrameIndex(0);
          setPlaying(true);
        }
      } else {
        setRun(d);
        if(scenario === "city_commute") setTrackedPassenger(d.passenger_groups?.[0]?.cohort_id || null);
        setResult(null);
        setFrameIndex(0);
        setPlaying(true);
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setJob((previous) => ({
        ...previous,
        status: "failed",
        stage: "Stopped — inspect error",
      }));
    } finally {
      setBusy(false);
    }
  }
  const nodes: Data[] = network.nodes || [];
  const edges: Data[] = network.edges || network.connections || [];
  const queues: Data = frame.queues || frame.node_queues || {};
  const selectedNode = nodes.find((n) => (n.id || n.node_id) === selected);
  const comparisons = result?.comparison || {};
  const metrics = run?.metrics || {};
  const agents: string[] = harness.active_agents || [
    "muni_agent",
    "bart_agent",
    "caltrain_agent",
  ];
  const isCoordinated =
    !!harness.coordination_mode &&
    harness.coordination_mode !== "decentralized";
  const operationalAgents = isCoordinated
    ? agents.filter((a) => a !== "regional_coordinator")
    : agents;
  const decisionList: Data[] = result?.decisions || historicalDecisions.filter(d=>!d.scenario || d.scenario === scenario);
  const planner =
    result?.planner || result?.planner_type || decisionList[0]?.planner;
  const plannerLabel =
    typeof planner === "string"
      ? planner
      : planner?.kind === "llm"
        ? `LLM mutation planner · ${planner.model || "model-driven"}`
        : planner?.kind === "rule_based"
          ? "Rule-based mutation planner · deterministic fallback"
          : "Planner mode reported after evaluation";
  const count = Object.values(db.counts || {}).reduce<number>(
    (a, b) => a + num(b),
    0,
  );
  const metricKeys = [
    ["total_passenger_delay_minutes", "Passenger delay · min", "min"],
    ["average_passenger_delay", "Average passenger delay · min", ""],
    ["passenger_wait_time", "Average passenger wait · min", ""],
    ["missed_transfer_rate", "Missed transfers", "%"],
    ["congestion", "Denied boardings", ""],
    ["unserved_passengers", "Unserved passengers", ""],
    ["additional_operating_cost", "Extra operating cost · model units", ""],
    ["boarding_within_10_minutes_rate", "First boarding within 10 min", "%"],
    ["eta_within_10_minutes_rate", "Arrival within initial ETA + 10 min", "%"],
    ["crowding_exposure_passenger_minutes", "Crowding exposure · passenger-min", ""],
    ["regional_density_peak", "Peak regional queue density · people/m²", ""],
    ["objective", "Objective · lower is better", ""],
  ];
  const readMetric = (m: Data, key: string) =>
    m?.[key] ??
    m?.[
      {
        total_passenger_delay_minutes: "total_delay_minutes",
        additional_operating_cost: "operating_cost",
        unserved_passengers: "unserved",
      }[key] || key
    ];
  const displayMetric = (m: Data, key: string) => {
    const v = readMetric(m, key);
    return key === "objective" && v !== undefined
      ? num(v).toFixed(4)
      : key.endsWith("_rate") && v !== undefined
      ? `${fmt(num(v) * 100)}%`
      : fmt(v);
  };
  const nodeName = (id: string) => nodes.find(n => (n.id || n.node_id) === id)?.name || id;
  const edgeInfo = (id: string) => {
    const e = edges.find(x => x.id === id);
    return e ? { route: `${String(e.operator).replace(/ Bus| Metro/, "")} ${e.service || ""}`.trim(), from: nodeName(e.source), to: nodeName(e.target) } : { route: id, from: "", to: "" };
  };
  const version = (d: Data) => d.candidate?.version || d.proposal?.candidate?.version || "candidate";
  const loop = buildLoopMessages({ job, result, busy, action, history: historicalDecisions.filter(d=>!d.scenario || d.scenario === scenario), time });
  const runDecisions: Data[] = result?.decisions || [];
  const outcomeDecision: Data | undefined = runDecisions.filter(d => d.accepted).slice(-1)[0] || runDecisions[runDecisions.length - 1];
  const kpiSource: Data = outcomeDecision?.before || {};
  const kpis: [string, string, boolean][] = kpiSource.boarding_within_10_minutes_rate !== undefined
    ? [["boarding_within_10_minutes_rate", "Boarded within 10 min", true], ["eta_within_10_minutes_rate", "Arrived by ETA + 10 min", true], ["crowding_exposure_passenger_minutes", "Crowding · passenger-min", false], ["objective", "Objective (lower is better)", false]]
    : [["average_passenger_delay", "Avg delay · min", false], ["unserved_passengers", "Unserved riders", false], ["objective", "Objective (lower is better)", false]];
  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#">
          <span className="brand-icon">≋</span>BayFlow
          <span className="brand-dot">.</span>
        </a>
        <span className="product-label">ADAPTIVE TRANSIT INTELLIGENCE</span>
        <nav>
          <a className={!historyPage?"nav-active":""} href="#operations">Agent loop</a>
          <a className={historyPage?"nav-active":""} href="#history">Evolution history</a>
        </nav>
        <div
          className={"db-pill " + (db.connected ? "connected" : "disconnected")}
        >
          <i />
          {STATIC ? "Atlas snapshot" : db.connected ? "Atlas connected" : "Atlas unavailable"}
          <span>{STATIC ? "read-only" : db.connected ? `${count} records` : "Sandbox required"}</span>
        </div>
      </header>
      {historyPage ? <EvolutionHistory offline={offline}/> : <main>
        <div className="intro">
          <h1>Transit agents that <span>fix their own operations.</span></h1>
          <p>Operator agents run the city. Harness agents watch riders, rewrite the operators' setup, and keep a change only if it wins on unseen days.</p>
        </div>
        <section className="controlbar">
          <div className="scenario-control">
            <span className="control-label">SCENARIO</span>
            <select aria-label="Transit scenario" value={scenario} onChange={(e) => setScenario(e.target.value)} disabled={busy}>
              {scenarios.length ? (
                (scenarios.some(s=>s.id === "city_commute") ? scenarios : [{id:"city_commute",name:"San Francisco Commute"},...scenarios]).map((s) => (
                  <option key={s.id || s.scenario_id} value={s.id || s.scenario_id}>{s.name || s.title || s.id}</option>
                ))
              ) : (
                <><option value="city_commute">San Francisco Commute</option><option value="event_surge">The Bay Area Event Surge</option></>
              )}
            </select>
          </div>
          <button className="primary" disabled={busy || STATIC} onClick={() => void launch("/operations/start", { seed, scenario, demand_scale: demandScale, advisory_acceptance_rate: advisoryAcceptance, horizon_minutes: scenario === "city_commute" ? horizonMinutes : undefined, iterations: scenario === "city_commute" ? 3 : 2, use_llm: useLlm })}>
            <Icon name="evolve" />
            {busy ? "Agents working…" : "Run autonomous simulation"}
          </button>
        </section>
        <details className="run-settings">
          <summary>Settings · {useLlm ? "LLM planner" : "rule-based planner"} · seed {seed}{scenario === "city_commute" ? ` · ${horizonMinutes / 60} h` : ""}</summary>
          <div className="settings-grid">
            <label>Mutation planner<select aria-label="Mutation planner" value={useLlm ? "llm" : "rule_based"} disabled={busy || STATIC} onChange={(e) => setUseLlm(e.target.value === "llm")}><option value="llm">LLM with validated fallback</option><option value="rule_based">Rule-based · deterministic</option></select></label>
            <label>Seed<input aria-label="Random seed" type="number" disabled={busy || STATIC} value={seed} onChange={(e) => setSeed(num(e.target.value))} /></label>
            {scenario === "city_commute" && <label>Operating horizon<select aria-label="Operating horizon" disabled={busy || STATIC} value={horizonMinutes} onChange={e=>setHorizonMinutes(Number(e.target.value))}><option value={180}>3 hours</option><option value={720}>12 hours</option><option value={1440}>24 hours</option></select></label>}
            <label>Passenger demand ×<input aria-label="Passenger demand multiplier" type="number" min=".25" max="3" step=".25" value={demandScale} disabled={busy || STATIC} onChange={e=>setDemandScale(num(e.target.value,1))}/></label>
            <label>Advice acceptance %<input aria-label="Voluntary advice acceptance percentage" type="number" min="0" max="100" step="10" value={Math.round(advisoryAcceptance*100)} disabled={busy || STATIC} onChange={e=>setAdvisoryAcceptance(num(e.target.value,60)/100)}/></label>
          </div>
          <div className="settings-benchmarks">
            <span>Benchmarks without the service monitor:</span>
            <select className="mode-select" aria-label="Baseline mode" disabled={busy || STATIC} value={mode} onChange={(e) => setMode(e.target.value)}><option value="fixed">Fixed agents</option><option value="static">Static timetable</option></select>
            <button className="secondary" disabled={busy || STATIC} onClick={() => void launch("/simulation/run", { mode, seed, scenario, demand_scale:demandScale, advisory_acceptance_rate:advisoryAcceptance, horizon_minutes:scenario === "city_commute" ? horizonMinutes : undefined })}><Icon name="play" />Run baseline</button>
            <button className="secondary" disabled={busy || STATIC} onClick={()=>void launch("/harness/evolve",{seed,scenario,demand_scale:demandScale,advisory_acceptance_rate:advisoryAcceptance,horizon_minutes:scenario === "city_commute" ? horizonMinutes : undefined,iterations:scenario === "city_commute" ? 3 : 2,use_llm:useLlm})}>Evaluate manually</button>
          </div>
        </details>
        {!db.connected && (
          <div className="database-warning">
            <span><b>MongoDB Atlas is not connected.</b> Official runs require the organizer sandbox. {db.error && <span className="db-error">{db.error}</span>}</span>
            <label><input type="checkbox" disabled={busy || STATIC} checked={offline} onChange={(e) => setOffline(e.target.checked)} />Enable offline preview</label>
          </div>
        )}
        {STATIC && <div className="offline-banner">READ-ONLY SNAPSHOT · Stored MongoDB Atlas records from a live BayFlow run, including a Gemini-proposed harness that the gate promoted. New simulations need the local backend: <a href="https://github.com/jin-dalrae/bayflow">github.com/jin-dalrae/bayflow</a></div>}
        {offline && <div className="offline-banner">OFFLINE PREVIEW · memory-only persistence; does not satisfy the Atlas requirement.</div>}
        {error && <div role="alert" className="error">{error}<button onClick={() => setError("")}>×</button></div>}
        {harnessError&&<div className="database-warning" role="status">{harnessError}</div>}
        <div id="operations" className="workspace stage">
          <section className="network-panel panel">
            <div className="panel-heading">
              <div>
                <span className="small-caps">SIMULATION REPLAY</span>
                <h2>The city the agents operate.</h2>{shown&&<span className="replay-context">Replay {shown.harness_version} · {shown.mode} policy{candidate ? ` · test day seed ${candidate.seed}` : ""} · run {String(shown.run_id).slice(0,8)}</span>}
              </div>
              <div className="live-label"><i />{playing ? "PLAYING" : frames.length ? "RUN LOADED" : "READY"}</div>
            </div>
            {runDecisions.length > 0 && result?.replay && (
              <div className="replay-switch" role="group" aria-label="Choose which harness to replay">
                <span>Replay</span>
                <button className={!candidate ? "on" : ""} onClick={() => { setCandidate(null); setFrameIndex(0); setPlaying(true); }}>Active harness {harness.version}</button>
                {runDecisions.map((d: Data) => { const seedRun = d.per_seed?.[0]; return seedRun?.after_run_id ? (
                  <button key={version(d)} className={candidate?.version === version(d) ? "on" : ""} disabled={candidate?.loading} onClick={async () => {
                    setCandidate({ version: version(d), loading: true, config: d.candidate, seed: seedRun.seed });
                    try { const r = await api(previewPath(`/simulation/${seedRun.after_run_id}`)); setCandidate({ version: version(d), run: r, config: d.candidate, seed: seedRun.seed }); setFrameIndex(0); setPlaying(true); }
                    catch (e) { setCandidate(null); setError(e instanceof Error ? e.message : String(e)); }
                  }}>Candidate {version(d)} test · {d.accepted ? "promoted" : "rejected"}</button>
                ) : null; })}
              </div>
            )}
            <div className="map-wrap">
              <TransitMap nodes={nodes} edges={edges} frame={frame} selected={selected} onSelect={setSelected} activeDispatchEdges={activeDispatchEdges} trackedGroup={trackedPassenger} trackedPath={trackedPath} />
              <div className="map-overlay">
                <strong>{time(frame.minute ?? frame.time_minutes ?? 0)}</strong>
                <span>{frames.length ? `Frame ${frameIndex + 1} / ${frames.length}` : `4:00 PM → ${time(scenario === "city_commute" ? horizonMinutes : 420)}`}</span>
              </div>
              {(frame.events || []).length > 0 && (
                <div className="active-events">{frame.events.map((e: Data, i: number) => <span key={i}><i />{e.label || e.type}</span>)}</div>
              )}
              {selectedNode && (
                <div className="station-info">
                  <button onClick={() => setSelected(null)}>×</button>
                  <span className="small-caps">STATION OBSERVATION</span>
                  <b>{selectedNode.name}</b>
                  <span>{fmt(queues[selected || ""] ?? 0)} passengers waiting</span>
                  <small>{selectedNode.operator} · {num(selectedNode.lat).toFixed(4)}, {num(selectedNode.lon).toFixed(4)}</small>
                </div>
              )}
            </div>
            <div className="playback">
              <button aria-label={playing ? "Pause playback" : "Play playback"} disabled={!frames.length} onClick={() => setPlaying(!playing)}><Icon name={playing ? "pause" : "play"} /></button>
              <span>{time(frame.minute ?? frame.time_minutes ?? 0)}</span>
              <input aria-label="Simulation time" type="range" min="0" max={Math.max(1, frames.length - 1)} value={frameIndex} disabled={!frames.length} onChange={(e) => { setPlaying(false); setFrameIndex(Number(e.target.value)); }} />
              <span>{time(run?.horizon_minutes ?? (scenario === "city_commute" ? horizonMinutes : 420))}</span>
            </div>
          </section>
          <AgentDiagram loop={loop.rows} loopSource={loop.source} busy={busy} traces={shown?.traces || []} minute={num(frame.minute)} interval={num(harness.replanning_interval_minutes, 15)} harness={candidate?.config || harness} proposals={[...(result?.decisions || []), ...historicalDecisions.filter(d => !d.scenario || d.scenario === scenario)]} time={time} edgeInfo={edgeInfo} nodeName={nodeName} />
        </div>
        <div className="outcome panel">
              <span className="small-caps">OUTCOME</span>
              {outcomeDecision ? <>
                <div className="outcome-verdict"><span className={"decision-badge " + (outcomeDecision.accepted ? "accepted" : "rejected")}>{outcomeDecision.accepted ? "PROMOTED" : "REJECTED"}</span><b>{outcomeDecision.accepted ? `${version(outcomeDecision)} is now active` : `${outcomeDecision.parent_version} kept`}</b></div>
                <p>{outcomeDecision.reason}</p>
                {outcomeDecision.before && <table className="outcome-table"><thead><tr><th>Held-out seeds</th><th>{outcomeDecision.parent_version}</th><th>{version(outcomeDecision)}</th></tr></thead><tbody>{kpis.map(([key,label,higher]) => { const b=readMetric(outcomeDecision.before,key), a=readMetric(outcomeDecision.after,key); const better = a===undefined||b===undefined ? null : higher ? a>b : a<b; return <tr key={key}><th>{label}</th><td>{displayMetric(outcomeDecision.before,key)}</td><td className={better===null?"":better?"better":"worse"}>{displayMetric(outcomeDecision.after,key)}</td></tr>; })}</tbody></table>}
                {result?.decisions && <small>{result.decisions.filter((d: Data) => d.accepted).length} promoted / {result.decisions.length} candidates tested this run</small>}
              </> : result?.operations ? <><div className="outcome-verdict"><span className="decision-badge accepted">HEALTHY</span><b>No change needed</b></div><p>Riders stayed on target, so the service monitor asked for no change.</p></> : <p className="muted">{run ? "Replaying the latest stored operating window. Run the autonomous simulation to watch the harness react." : "Run the autonomous simulation to see whether the agents can improve service."}</p>}
              <div className={"outcome-atlas " + (db.connected ? "ok" : "")}>{db.connected ? `✓ Every message and decision saved to MongoDB Atlas · ${fmt(count)} records` : offline ? "Offline preview · records held in memory only" : "Atlas not connected"}</div>
            </div>
        <div className="details-stack">
          <details className="detail-section">
            <summary>Full conversation log <span>every harness message and the operator channel at {time(frame.minute)}</span></summary>
            <AgentFlow rows={loop.rows} source={loop.source} />
            <div className="agent-activity">
              <div className="activity-heading"><span className="small-caps">OPERATOR CHANNEL UP TO {time(frame.minute)}</span><span>{recordedTraces.length} recorded traces so far</span></div>
              {interventions.length ? <ol className="ops-log">{interventions.flatMap(trace => narrate(trace, edgeInfo, nodeName, time)).map((c, index) => <li className="agent-intervention chat-line" key={index}><b>{time(c.minute)} · {agentName[c.from]}<i>{c.from === c.to ? " · action" : ` → ${agentName[c.to]}`}</i></b><span>{c.text}</span>{c.decision && <em className={`tone-${c.tone}`}>{c.decision}</em>}</li>)}</ol> : <p>{run ? "No operator messages yet at this point in the replay." : "Run a simulation to hear the operators."}</p>}
              {recordedTraces.length > 0 && <details className="trace-observations"><summary>Raw agent traces · latest {Math.min(40,recordedTraces.length)}</summary><pre>{JSON.stringify(recordedTraces.slice(-40), null, 2)}</pre></details>}
            </div>
          </details>
          <details className="detail-section">
            <summary>Passenger journeys <span>boarding, ETA and crowding for each simulated rider group</span></summary>
            <PassengerInspector run={shown} frame={frame} nodes={nodes} edges={edges} selected={trackedPassenger} onSelect={setTrackedPassenger} onSeek={(minute)=>{setPlaying(false);const index=frames.findIndex(f=>f.minute>=minute);if(index>=0)setFrameIndex(index);}} />
          </details>
          <details id="evaluation" className="detail-section evaluation">
            <summary>Full metric comparison <span>static timetable · fixed agents · evolving harness</span></summary>
            {!result && !run ? (
              <p className="comparison-empty">No results yet. After a run, this table compares all three modes on the same scenario and seed.</p>
            ) : (
              <div className="comparison-table">
                <div className="table-row table-head"><span>Performance metric</span><span>Static timetable</span><span>Fixed agents</span><span className="evolved-col">Evolving harness <Icon name="evolve" /></span></div>
                {metricKeys.map(([key, label]) => (
                  <div className="table-row" key={key}>
                    <span>{label}</span>
                    <b>{displayMetric(comparisons.static || (!result && run?.mode === "static" ? metrics : {}), key)}</b>
                    <b>{displayMetric(comparisons.fixed || (!result && run?.mode === "fixed" ? metrics : {}), key)}</b>
                    <b className="evolved-col">{displayMetric(comparisons.evolved || {}, key)}</b>
                  </div>
                ))}
              </div>
            )}
          </details>
          <details className="detail-section">
            <summary>Candidate changes & backend log <span>{decisionList.length} proposals · {plannerLabel}</span></summary>
            <div className="audit-panel">
              <span className="planner-label">{!result && decisionList.length ? `Latest recorded planner · ${plannerLabel}` : plannerLabel}</span>
              {(result?.decisions || decisionList.slice(-3).reverse()).map((d: Data, i: number) => (
                <div className="decision" key={i}>
                  <div className="decision-top"><span className={"decision-badge " + (d.accepted ? "accepted" : "rejected")}>{d.accepted ? "PROMOTED" : "REJECTED"}</span><b>{version(d)}</b></div>
                  <p>{d.reason || d.proposal?.rationale || d.rationale}</p>
                  <small>{d.proposal?.diagnosis || d.proposal?.root_cause || ""}</small>
                  {result?.decisions ? <><MutationDiff decision={d} versions={versions}/><details><summary>Inspect proposal & evaluation</summary><pre>{JSON.stringify(d, null, 2)}</pre></details></> : null}
                </div>
              ))}
              {job && job.history?.length > 0 && (
                <details className="execution-history">
                  <summary>Backend execution log · {job.history.length} stages</summary>
                  <ol>{job.history.map((entry: Data, i: number) => <li key={i}><i /><span>{entry.stage}</span><time dateTime={entry.at}>{entry.at ? new Date(entry.at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—"}</time></li>)}</ol>
                </details>
              )}
              <a className="history-inline-link" href="#history">Full evolution history →</a>
            </div>
          </details>
          <details className="detail-section">
            <summary>Harness configuration & rules <span>the architecture the planner is allowed to change</span></summary>
            <div className="harness-details">
              <div className="config-list">
                {[["Planning horizon", `${harness.planning_horizon_minutes ?? 30} minutes`], ["Replan interval", `${harness.replanning_interval_minutes ?? 15} minutes`], ["Context policy", harness.context_policy || "local_only"], ["Memory window", `${harness.memory_window_steps ?? 6} steps`], ["Strategy", harness.optimization_strategy || "local_greedy"], ["Verification", harness.verification_policy || "basic"]].map(([k, v]) => <div key={k}><span>{k}</span><b>{v.replace(/_/g, " ")}</b></div>)}
              </div>
              <div className="tools"><span className="small-caps">ENABLED TOOLS</span><div>{(harness.active_tools || ["local_dispatch_optimizer"]).map((t: string) => <span key={t}>⌁ {t.replace(/_/g, " ")}</span>)}</div></div>
              {result?.automatic_trigger&&<details className="automatic-trigger"><summary>Automatic evolution trigger</summary><pre>{JSON.stringify(result.automatic_trigger,null,2)}</pre></details>}
              <Rulebook config={harness} run={run}/>
            </div>
          </details>
          <details className="detail-section">
            <summary>MongoDB Atlas records & versions <span>{db.connected ? `${fmt(count)} records` : "not connected"}</span></summary>
            <div className="persistence-panel">
              <p>{db.connected ? "Harness configurations, traces, evaluations, and deployment decisions are recorded in the organizer MongoDB Atlas Sandbox." : offline ? "Preview records are held only in memory. No records from this preview are persisted in MongoDB Atlas." : "Atlas persistence is unavailable. Connect the organizer sandbox to record harness configurations, traces, evaluations, and deployment decisions."}</p>
              <div className="record-counts">{Object.entries(db.counts || {}).map(([k, v]) => <div key={k}><span>{k.replace(/_/g, " ")}</span><b>{fmt(v)}</b></div>)}</div>
              <div className="version-history">
                <span className="small-caps">VERSION HISTORY & ROLLBACK</span>
                {versions.filter(v=>(v.config?.version||v.version)===harness.version).concat(versions.filter(v=>(v.config?.version||v.version)!==harness.version).slice(-7).reverse()).map((v, i) => {
                  const c = v.config || v;
                  return (
                    <div key={c.version || i}>
                      <span>{c.version || v.version}</span>
                      <span>{v.active ? "Active" : v.parent_version || c.coordination_mode}</span>
                      <button disabled={busy || c.version === harness.version || v.accepted === false} onClick={() => void launch("/harness/rollback", { version: c.version, scenario })}>{v.accepted === false ? "Rejected" : "↶ Restore"}</button>
                    </div>
                  );
                })}
                {!versions.length && <p className="muted">No persisted harness history yet.</p>}
              </div>
            </div>
          </details>
        </div>
        <footer><span>BayFlow <b>↗</b> Real SF geography · synthetic demand · reproducible decisions</span></footer>
      </main>}
    </div>
  );
}
