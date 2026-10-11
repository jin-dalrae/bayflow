import { useEffect, useMemo, useRef, useState } from "react";
import TransitMap from "./TransitMap";
import PassengerInspector from "./PassengerInspector";
import { Rulebook, MutationDiff } from "./Rulebook";
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
  const t = 960 + num(m);
  return `${Math.floor(t / 60) % 12 || 12}:${String(t % 60).padStart(2, "0")} ${t >= 720 ? "PM" : "AM"}`;
};
async function api(path: string, body?: Data) {
  const r = await fetch(
    `/api${path}`,
    body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : undefined,
  );
  const d = await r.json();
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
    [useLlm, setUseLlm] = useState(true);
  const alive = useRef(true);
  const requestGeneration = useRef(0);
  const previewPath = (p: string) => (offline ? `${p}?offline=true` : p);
  const refresh = async () => {
    const generation = ++requestGeneration.current;
    const requests = [
      [`/network?scenario=${encodeURIComponent(scenario)}`, setNetwork],
      [previewPath("/database/status"), setDb],
      [previewPath("/harness/current"), (d: Data) => setHarness(d.config || d)],
      [previewPath("/harness/versions"), (d: any) => setVersions(Array.isArray(d) ? d : d.versions || [])],
      ["/scenarios", (d: any) => setScenarios(Array.isArray(d) ? d : d.scenarios || [])],
      [previewPath("/harness/proposals"), (d: any) => setHistoricalDecisions(Array.isArray(d) ? d : d.proposals || [])],
    ] as const;
    await Promise.allSettled(requests.map(async ([path, apply], index) => {
      try {
        const data = await api(path);
        if (alive.current && generation === requestGeneration.current) apply(data);
      } catch {
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
    setJob(null);
    setPlaying(false);
    setFrameIndex(0);
    setTrackedPassenger(null);
    void refresh();
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
  }, [offline, scenario]);
  const trackedPath: string[] = useMemo(()=>run?.passenger_groups?.find((group:Data)=>group.cohort_id===trackedPassenger)?.path || [],[run,trackedPassenger]);
  const frames: Data[] = run?.frames || [];
  const frame = frames[frameIndex] || {};
  const recordedTraces: Data[] = useMemo(() => (run?.traces || []).filter((trace: Data) => num(trace.minute) <= num(frame.minute)), [run, frame.minute]);
  const interventions = recordedTraces.filter(trace => trace.action !== "observe").slice(-6).reverse();
  const activeDispatchEdges = new Set(recordedTraces.filter(trace => trace.action === "standby_dispatch" && trace.tool !== "operating_rule" && num(trace.minute) === num(frame.minute)).map(trace => trace.edge_id));
  useEffect(() => {
    if (!playing || !frames.length) return;
    const t = setInterval(
      () =>
        setFrameIndex((i) => {
          if (i >= frames.length - 1) {
            setPlaying(false);
            return i;
          }
          return i + 1;
        }),
      100,
    );
    return () => clearInterval(t);
  }, [playing, frames.length]);
  async function launch(path: string, body: Data) {
    setError("");
    setBusy(true);
    setPlaying(false);
    setTrackedPassenger(null);
    setJob({ status: "pending", stage: "Starting real backend evaluation" });
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
      } else if (path.includes("evolve")) {
        setResult(d);
        if (d.current) setHarness(d.current.config || d.current);
        if (d.replay || d.run || d.evolved_run) {
          setRun(d.replay || d.run || d.evolved_run);
          setFrameIndex(0);
          setPlaying(true);
        }
      } else {
        setRun(d);
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
  const decisionList: Data[] = result?.decisions || historicalDecisions;
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
  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#">
          <span className="brand-icon">≋</span>BayFlow
          <span className="brand-dot">.</span>
        </a>
        <span className="product-label">ADAPTIVE TRANSIT INTELLIGENCE</span>
        <nav>
          <span className="nav-active">Operations lab</span>
          <a href="#evaluation">Evaluation</a>
          <a href="#audit">Architecture log</a>
        </nav>
        <div
          className={"db-pill " + (db.connected ? "connected" : "disconnected")}
        >
          <i />
          {db.connected ? "Atlas connected" : "Atlas unavailable"}
          <span>{db.connected ? `${count} records` : "Sandbox required"}</span>
        </div>
      </header>
      <main>
        <div className="intro">
          <div>
            <div className="eyebrow">
              <span /> BAY AREA OPERATIONS / EXPERIMENT 001
            </div>
            <h1>
              A city in motion.
              <br />
              <span>A system that learns.</span>
            </h1>
            <p>
              Observe disruption. Evolve the architecture. Prove the
              improvement.
            </p>
          </div>
          <div className="intro-note">
            <span className="small-caps">RECURSIVE HARNESSING</span>
            <p>
              The agents can change how they
              <br />
              coordinate — and test if it works.
            </p>
            <span className="note-line">
              San Francisco Bay Area <b>↗</b>
            </span>
          </div>
        </div>
        <section className="controlbar">
          <div className="scenario-control">
            <span className="control-label">SCENARIO</span>
            <select
              aria-label="Transit scenario"
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              disabled={busy}
            >
              {scenarios.length ? (
                (scenarios.some(s=>s.id === "city_commute") ? scenarios : [{id:"city_commute",name:"San Francisco Commute"},...scenarios]).map((s) => (
                  <option
                    key={s.id || s.scenario_id}
                    value={s.id || s.scenario_id}
                  >
                    {s.name || s.title || s.id}
                  </option>
                ))
              ) : (
                <><option value="city_commute">San Francisco Commute</option><option value="event_surge">The Bay Area Event Surge</option></>
              )}
            </select>
          </div>
          <div className="seed-control">
            <span className="control-label">SEED</span>
            <input
              aria-label="Random seed"
              type="number"
              disabled={busy}
              value={seed}
              onChange={(e) => setSeed(num(e.target.value))}
            />
          </div>
          <select
            className="mode-select"
            aria-label="Baseline mode"
            disabled={busy}
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value="fixed">Fixed agents</option>
            <option value="static">Static timetable</option>
          </select>
          <button
            className="secondary"
            disabled={busy}
            onClick={() =>
              void launch("/simulation/run", { mode, seed, scenario, demand_scale:demandScale, advisory_acceptance_rate:advisoryAcceptance })
            }
          >
            <Icon name="play" />
            Run baseline
          </button>
          <button
            className="primary"
            disabled={busy}
            onClick={() => {
              
              void launch("/harness/evolve", {
                seed,
                scenario,
                demand_scale: demandScale,
                advisory_acceptance_rate: advisoryAcceptance,
                iterations: 2,
                use_llm: useLlm,
              });
            }}
          >
            <Icon name="evolve" />
            {busy ? "Evaluating…" : "Evolve harness"}
            <span>↗</span>
          </button>
        </section>
        <div className="experiment-options">
          <span>
            Evolution evaluates the selected scenario on fixed held-out seeds.
          </span>
          <label>
            Mutation planner{" "}
            <select
              aria-label="Mutation planner"
              value={useLlm ? "llm" : "rule_based"}
              disabled={busy}
              onChange={(e) => setUseLlm(e.target.value === "llm")}
            >
              <option value="llm">LLM with validated fallback</option>
              <option value="rule_based">Rule-based · deterministic</option>
            </select>
          </label>
        </div>
        <div className="demand-controls"><label>Passenger demand <input aria-label="Passenger demand multiplier" type="number" min=".25" max="3" step=".25" value={demandScale} disabled={busy} onChange={e=>setDemandScale(num(e.target.value,1))}/><span>× scenario demand</span></label><label>Voluntary advice acceptance <input aria-label="Voluntary advice acceptance percentage" type="number" min="0" max="100" step="10" value={Math.round(advisoryAcceptance*100)} disabled={busy} onChange={e=>setAdvisoryAcceptance(num(e.target.value,60)/100)}/><span>% of simulated offers</span></label><small>Frozen before each run and shared by baseline, candidate, and held-out evaluations.</small></div>
        {!db.connected && (
          <div className="database-warning">
            <span>
              <b>Organizer Atlas Sandbox is not connected.</b> Official runs
              require a verified sandbox.{" "}
              {db.error && <span className="db-error">{db.error}</span>}
            </span>
            <label>
              <input
                type="checkbox"
                disabled={busy}
                checked={offline}
                onChange={(e) => setOffline(e.target.checked)}
              />
              Enable offline preview
            </label>
          </div>
        )}
        {offline && (
          <div className="offline-banner">
            OFFLINE PREVIEW · Deterministic simulation with memory-only
            persistence. This mode does not satisfy the hackathon Atlas
            requirement.
          </div>
        )}
        {error && (
          <div role="alert" className="error">
            {error}
            <button onClick={() => setError("")}>×</button>
          </div>
        )}
        <div className="workspace">
          <section className="network-panel panel">
            <div className="panel-heading">
              <div>
                <span className="small-caps">LIVING TRANSIT NETWORK</span>
                <h2>One region. Four systems.</h2>{run&&<span className="replay-context">Replay {run.harness_version} · {run.mode} policy · run {String(run.run_id).slice(0,8)}</span>}
              </div>
              <div className="live-label">
                <i />
                {playing
                  ? "SIMULATION PLAYING"
                  : frames.length
                    ? "RUN LOADED"
                    : "READY TO SIMULATE"}
              </div>
            </div>
            <div className="map-wrap">
              <TransitMap nodes={nodes} edges={edges} frame={frame} selected={selected} onSelect={setSelected} activeDispatchEdges={activeDispatchEdges} trackedGroup={trackedPassenger} trackedPath={trackedPath} />
              <div className="map-overlay">
                <span className="small-caps">SAN FRANCISCO / REAL GEOGRAPHY</span>
                <strong>{time(frame.minute ?? frame.time_minutes ?? 0)}</strong>
                <span>
                  {frames.length
                    ? `Frame ${frameIndex + 1} / ${frames.length}`
                    : `4:00 PM → ${time(scenario === "city_commute" ? 180 : 420)}`}
                </span>
              </div>
              {(frame.events || []).length > 0 && (
                <div className="active-events">
                  {frame.events.map((e: Data, i: number) => (
                    <span key={i}>
                      <i />
                      {e.label || e.type}
                    </span>
                  ))}
                </div>
              )}
              <div className="map-key">
                {[
                  ["Muni Bus", "#e9b168"],
                  ["Muni Metro", "#b6a4ef"],
                  ["BART", "#75c7f2"],
                  ["Caltrain", "#df8290"],
                ].map(([name, c]) => (
                  <span key={name}>
                    <i style={{ background: c }} />
                    {name}
                  </span>
                ))}
              </div>
              {selectedNode && (
                <div className="station-info">
                  <button onClick={() => setSelected(null)}>×</button>
                  <span className="small-caps">STATION OBSERVATION</span>
                  <b>{selectedNode.name}</b>
                  <span>
                    {fmt(queues[selected || ""] ?? 0)} passengers waiting
                  </span>
                  <small>
                    {selectedNode.operator} · {num(selectedNode.lat).toFixed(4)}
                    , {num(selectedNode.lon).toFixed(4)}
                  </small>
                </div>
              )}
            </div>
            <div className="playback">
              <button
                aria-label={playing ? "Pause playback" : "Play playback"}
                disabled={!frames.length}
                onClick={() => setPlaying(!playing)}
              >
                <Icon name={playing ? "pause" : "play"} />
              </button>
              <span>{time(frame.minute ?? frame.time_minutes ?? 0)}</span>
              <input
                aria-label="Simulation time"
                type="range"
                min="0"
                max={Math.max(1, frames.length - 1)}
                value={frameIndex}
                disabled={!frames.length}
                onChange={(e) => {
                  setPlaying(false);
                  setFrameIndex(Number(e.target.value));
                }}
              />
              <span>{time(run?.horizon_minutes ?? (scenario === "city_commute" ? 180 : 420))}</span>
              <span className="synthetic-tag">SYNTHETIC SCENARIO</span>
            </div>
            <PassengerInspector run={run} frame={frame} nodes={nodes} edges={edges} selected={trackedPassenger} onSelect={setTrackedPassenger} onSeek={(minute)=>{setPlaying(false);const index=frames.findIndex(f=>f.minute>=minute);if(index>=0)setFrameIndex(index);}} />
            <div className="event-strip">{scenario === "city_commute" ? <><div><i className="event-dot"/><b>4:00–7:00 PM</b><span>Rolling commuter intent</span></div><div><i className="event-dot blue"/><b>10 minute support</b><span>First boarding + initial ETA</span></div><div><i className="event-dot coral"/><b>Regional coordination</b><span>Queue density & crowding</span></div></> : <>
              <div>
                <i className="event-dot" />
                <b>5:20 PM</b>
                <span>Driver unavailable</span>
              </div>
              <div>
                <i className="event-dot blue" />
                <b>6:10 PM</b>
                <span>BART delay</span>
              </div>
              <div>
                <i className="event-dot coral" />
                <b>8:45 / 9:30 PM</b>
                <span>Dual event surge</span>
              </div></>}
            </div>
            <div className="agent-activity">
              <div className="activity-heading"><span className="small-caps">LIVE AGENT ACTIVITY</span><span>{recordedTraces.length} recorded decisions / observations by {time(frame.minute)}</span></div>
              {interventions.length ? <ol>{interventions.map((trace, index) => <li className="agent-intervention" key={`${trace.minute}-${trace.agent}-${index}`}><time>{time(trace.minute)}</time><div><b>{String(trace.agent || (trace.operator ? `${trace.operator} controller` : "harness interpreter")).replace(/_/g," ")}</b><span>{trace.tool === "operating_rule" ? `Rule ${trace.rule_id} fired → ${String(trace.action).replace(/_/g," ")} requested` : String(trace.action).replace(/_/g," ")}{trace.tool ? ` · ${trace.tool}` : ""}{trace.edge_id ? ` · ${trace.edge_id}` : ""}</span><small>{trace.tool === "operating_rule" ? `Observed signal ${fmt(trace.signal_value)} · feasibility-gated action; actual executions appear in rule telemetry.` : trace.action === "passenger_advisory" ? `${trace.requested_operator} ${trace.requested_service||''} → ${trace.alternative_operator} ${trace.alternative_service||''} · ${fmt(trace.accepted_count)}/${fmt(trace.offered_count)} accepted · alternative ETA ${time(trace.alternative_eta)} (estimated)` : trace.rationale || (trace.observed_queue !== undefined ? `${fmt(trace.observed_queue)} observed passengers${trace.verification ? ` · ${trace.verification} verification` : ""}` : "Recorded backend intervention")}</small></div></li>)}</ol> : <p>No operational interventions recorded by this frame. Replay observations are available below.</p>}
              {recordedTraces.length > 0 && <details className="trace-observations"><summary>Inspect recorded agent observations · latest {Math.min(40,recordedTraces.length)} traces</summary><pre>{JSON.stringify(recordedTraces.slice(-40), null, 2)}</pre></details>}
            </div>
          </section>
          <aside className="harness-panel panel">
            <div className="panel-heading">
              <div>
                <span className="small-caps">THE EVOLVING HARNESS</span>
                <h2>Intelligence, connected.</h2>
              </div>
              <span className="version-tag">{harness.version || "v1"}</span>
            </div>
            <div className="topology">
              <svg
                viewBox="0 0 360 225"
                aria-label="Current agent coordination topology"
              >
                <defs>
                  <linearGradient id="connection">
                    <stop stopColor="#93d5b4" />
                    <stop offset="1" stopColor="#36544b" />
                  </linearGradient>
                </defs>
                {operationalAgents.map((a, i) => {
                  const x =
                    55 + i * (250 / Math.max(1, operationalAgents.length - 1));
                  return (
                    <g key={a}>
                      {isCoordinated && (
                        <path
                          d={`M180 58L${x} 160`}
                          stroke="url(#connection)"
                          strokeWidth="1.5"
                        />
                      )}
                      <circle
                        cx={x}
                        cy="160"
                        r="22"
                        fill="#24322c"
                        stroke={color(a.split("_")[0])}
                      />
                      <text
                        x={x}
                        y="166"
                        textAnchor="middle"
                        fill={color(a.split("_")[0])}
                        fontSize="15"
                      >
                        {a.includes("regional") ? "◎" : "▰"}
                      </text>
                      <text
                        x={x}
                        y="202"
                        textAnchor="middle"
                        fill="#c1cfc4"
                        fontSize="11"
                      >
                        {{
                          muni_agent: "MUNI",
                          bart_agent: "BART",
                          caltrain_agent: "CALTRAIN",
                          regional_coordinator: "COORD",
                          demand_forecaster: "FORECAST",
                        }[a] || a.replace(/_agent/g, "").toUpperCase()}
                      </text>
                    </g>
                  );
                })}
                <circle
                  cx="180"
                  cy="50"
                  r="27"
                  fill="#283b2e"
                  stroke="#acd3ae"
                  strokeWidth="1.5"
                />
                <text
                  x="180"
                  y="57"
                  textAnchor="middle"
                  fill="#acd3ae"
                  fontSize="23"
                >
                  {isCoordinated ? "◎" : "✧"}
                </text>
                <text
                  x="180"
                  y="100"
                  textAnchor="middle"
                  fill="#abc5af"
                  fontSize="10"
                >
                  {isCoordinated ? "REGIONAL COORDINATOR" : "HARNESS PLANNER"}
                </text>
              </svg>
              <div className="topology-caption">
                <span>{harness.coordination_mode || "decentralized"}</span>
                <span>{agents.length} active agents</span>
              </div>
            </div>
            <div className="config-list">
              {[
                [
                  "Planning horizon",
                  `${harness.planning_horizon_minutes ?? 30} minutes`,
                ],
                [
                  "Replan interval",
                  `${harness.replanning_interval_minutes ?? 15} minutes`,
                ],
                ["Context policy", harness.context_policy || "local_only"],
                ["Memory window", `${harness.memory_window_steps ?? 6} steps`],
                ["Strategy", harness.optimization_strategy || "local_greedy"],
                ["Verification", harness.verification_policy || "basic"],
              ].map(([k, v]) => (
                <div key={k}>
                  <span>{k}</span>
                  <b>{v.replace(/_/g, " ")}</b>
                </div>
              ))}
            </div>
            <div className="tools">
              <span className="small-caps">ENABLED TOOLS</span>
              <div>
                {(harness.active_tools || ["local_dispatch_optimizer"]).map(
                  (t: string) => (
                    <span key={t}>⌁ {t.replace(/_/g, " ")}</span>
                  ),
                )}
              </div>
            </div>
            <Rulebook config={harness} run={run}/>
            <div className="evolution-state">
              <div className="state-heading">
                <span className={"state-orb " + (busy ? "pulse" : "")} />
                <b>
                  {busy
                    ? "Evolution in progress"
                    : decisionList.length
                      ? "Evaluation complete"
                      : "Ready to evolve"}
                </b>
              </div>
              <p>
                {job?.stage ||
                  "Run the baseline to expose failures, then let the planner propose a new architecture."}
              </p>
              {busy && (
                <div className="progress-track">
                  <span />
                </div>
              )}
              <span className="planner-label">{plannerLabel}</span>
              {job && job.history?.length > 0 && (
                <details
                  className="execution-history"
                  open={job.status === "completed"}
                >
                  <summary>
                    Backend execution history · {job.history.length} stages
                  </summary>
                  <ol>
                    {job.history.map((entry: Data, i: number) => (
                      <li key={i}>
                        <i />
                        <span>{entry.stage}</span>
                        <time dateTime={entry.at}>
                          {entry.at
                            ? new Date(entry.at).toLocaleTimeString(undefined, {
                                hour: "2-digit",
                                minute: "2-digit",
                                second: "2-digit",
                                fractionalSecondDigits: 3,
                              })
                            : "—"}
                        </time>
                      </li>
                    ))}
                  </ol>
                </details>
              )}
            </div>
          </aside>
        </div>
        <section id="evaluation" className="evaluation panel">
          <div className="panel-heading">
            <div>
              <span className="small-caps">INDEPENDENT EVALUATION</span>
              <h2>Better architecture. Measured impact.</h2>
            </div>
            <span className="evaluation-note">
              Same scenario · same seeds · fixed objective
            </span>
          </div>
          <div className="comparison-table">
            <div className="table-row table-head">
              <span>Performance metric</span>
              <span>Static timetable</span>
              <span>Fixed agents</span>
              <span className="evolved-col">
                Evolving harness <Icon name="evolve" />
              </span>
            </div>
            {metricKeys.map(([key, label]) => (
              <div className="table-row" key={key}>
                <span>{label}</span>
                <b>
                  {displayMetric(
                    comparisons.static ||
                      (!result && run?.mode === "static" ? metrics : {}),
                    key,
                  )}
                </b>
                <b>
                  {displayMetric(
                    comparisons.fixed ||
                      (!result && run?.mode === "fixed" ? metrics : {}),
                    key,
                  )}
                </b>
                <b className="evolved-col">
                  {displayMetric(comparisons.evolved || {}, key)}
                </b>
              </div>
            ))}
          </div>
          <div className="eval-footer">
            <span>
              Evaluation results come directly from the Python simulator.
            </span>
            <span>
              {result
                ? `${comparisons.fixed?.objective > 0 && comparisons.evolved?.objective !== undefined ? `${fmt((1 - comparisons.evolved.objective / comparisons.fixed.objective) * 100)}% objective improvement · ` : ""}${decisionList.filter((d) => d.accepted).length} promoted / ${decisionList.length} mutations tested`
                : "Run an evolution cycle to compare all three modes."}
            </span>
          </div>
        </section>
        <section id="audit" className="audit-grid">
          <div className="panel audit-panel">
            <div className="panel-heading">
              <div>
                <span className="small-caps">MUTATION AUDIT TRAIL</span>
                <h2>Every change earns its place.</h2>
              </div>
              <span className="version-tag">
                {decisionList.length} proposals
              </span>
            </div>
            {!decisionList.length ? (
              <div className="empty-log">
                <span>↗</span>
                <p>No mutations evaluated yet.</p>
                <small>
                  The complete proposal, evaluation, and decision will appear
                  here.
                </small>
              </div>
            ) : (
              decisionList.map((d, i) => (
                <div className="decision" key={i}>
                  <div className="decision-top">
                    <span
                      className={
                        "decision-badge " +
                        (d.accepted ? "accepted" : "rejected")
                      }
                    >
                      {d.accepted ? "PROMOTED" : "REJECTED"}
                    </span>
                    <b>
                      {d.candidate?.version ||
                        d.proposal?.candidate?.version ||
                        `Candidate ${i + 1}`}
                    </b>
                  </div>
                  <p>{d.reason || d.proposal?.rationale || d.rationale}</p>
                  <small>
                    {d.proposal?.diagnosis || d.proposal?.root_cause || ""}
                  </small>
                  <MutationDiff decision={d} versions={versions}/>
                  <details>
                    <summary>Inspect proposal & evaluation</summary>
                    <pre>{JSON.stringify(d, null, 2)}</pre>
                  </details>
                </div>
              ))
            )}
          </div>
          <div className="panel persistence-panel">
            <div className="panel-heading">
              <div>
                <span className="small-caps">PERSISTENT SYSTEM OF RECORD</span>
                <h2>Proof, beyond the screen.</h2>
              </div>
              <span className="mongo-mark">◈</span>
            </div>
            <p>
              {db.connected
                ? "Harness configurations, traces, evaluations, and deployment decisions are recorded in the organizer MongoDB Atlas Sandbox."
                : offline
                  ? "Preview records are held only in memory. No records from this preview are persisted in MongoDB Atlas."
                  : "Atlas persistence is unavailable. Connect the organizer sandbox to record harness configurations, traces, evaluations, and deployment decisions."}
            </p>
            <div className="record-counts">
              {Object.entries(db.counts || {}).map(([k, v]) => (
                <div key={k}>
                  <span>{k.replace(/_/g, " ")}</span>
                  <b>{fmt(v)}</b>
                </div>
              ))}
              {!Object.keys(db.counts || {}).length && (
                <span className="muted">
                  {offline
                    ? "Preview record counts will appear after a run."
                    : "Atlas record counts will appear after connection."}
                </span>
              )}
            </div>
            <div className="version-history">
              <span className="small-caps">VERSION HISTORY & ROLLBACK</span>
              {versions.map((v, i) => {
                const c = v.config || v;
                return (
                  <div key={c.version || i}>
                    <span>{c.version || v.version}</span>
                    <span>
                      {v.active
                        ? "Active"
                        : v.parent_version || c.coordination_mode}
                    </span>
                    <button
                      disabled={
                        busy ||
                        c.version === harness.version ||
                        v.accepted === false
                      }
                      onClick={() =>
                        void launch("/harness/rollback", { version: c.version })
                      }
                    >
                      {v.accepted === false ? "Rejected" : "↶ Restore"}
                    </button>
                  </div>
                );
              })}
              {!versions.length && (
                <p className="muted">No persisted harness history yet.</p>
              )}
            </div>
          </div>
        </section>
        <footer>
          <span>
            BayFlow <b>↗</b> Experimental autonomous systems lab
          </span>
          <span>Real places. Synthetic demand. Reproducible decisions.</span>
        </footer>
      </main>
    </div>
  );
}
