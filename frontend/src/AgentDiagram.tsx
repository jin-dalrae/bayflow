import { useEffect, useRef, useState } from "react";
import { type Message } from "./AgentFlow";
import { narrate, agentName, type Chat, type EdgeInfo } from "./narrate";
type Data = Record<string, any>;
type Node = { id: string; x: number; y: number; label: string; kind: "op" | "harness"; color?: string };

const NODES: Node[] = [
  { id: "coord", x: 260, y: 80, label: "Regional coordinator", kind: "op", color: "#acd3ae" },
  { id: "muni", x: 95, y: 196, label: "Muni agent", kind: "op", color: "#e9b168" },
  { id: "bart", x: 260, y: 196, label: "BART agent", kind: "op", color: "#75c7f2" },
  { id: "caltrain", x: 425, y: 196, label: "Caltrain agent", kind: "op", color: "#df8290" },
  { id: "monitor", x: 92, y: 384, label: "Service monitor", kind: "harness" },
  { id: "planner", x: 260, y: 384, label: "Planner", kind: "harness" },
  { id: "validator", x: 428, y: 384, label: "Validator", kind: "harness" },
  { id: "evaluator", x: 428, y: 494, label: "Evaluator", kind: "harness" },
  { id: "gate", x: 260, y: 494, label: "Promotion gate", kind: "harness" },
  { id: "atlas", x: 92, y: 494, label: "MongoDB Atlas", kind: "harness" },
];
const node = (id: string) => NODES.find(n => n.id === id)!;
// The harness talks to the operator layer as a whole.
const OPS_BOX = { x: 30, y: 30, w: 480, h: 258 };
const EDGES: [string, string][] = [
  ["coord", "muni"], ["coord", "bart"], ["coord", "caltrain"],
  ["opsbox", "monitor"], ["monitor", "planner"], ["planner", "validator"], ["validator", "evaluator"],
  ["evaluator", "gate"], ["gate", "atlas"], ["atlas", "planner"], ["atlas", "opsbox"],
];
const key = (a: string, b: string) => `${a}>${b}`;
const nameOf = (id: string) => (id === "opsbox" ? "Transport operators" : NODES.find(n => n.id === id)?.label || id);
// Coordinator ↔ operator lines carry requests one way and replies the other.
const TWO_WAY = new Set(["coord>muni", "coord>bart", "coord>caltrain"]);
const pairKey = (a: string, b: string) => (TWO_WAY.has(key(b, a)) ? key(b, a) : key(a, b));

// Point where a line toward (tx,ty) leaves the node outline.
function edgePoint(n: Node, tx: number, ty: number) {
  const dx = tx - n.x, dy = ty - n.y, len = Math.hypot(dx, dy) || 1;
  if (n.kind === "op") return [n.x + (dx / len) * 30, n.y + (dy / len) * 30];
  const hw = 68, hh = 23;
  const t = Math.min(hw / Math.abs(dx || 1e-6), hh / Math.abs(dy || 1e-6));
  return [n.x + dx * t, n.y + dy * t];
}
function edgePath(a: string, b: string) {
  if (a === "atlas" && b === "opsbox") return "M24 494 C -8 470, -8 250, 28 210";
  if (a === "opsbox" && b === "monitor") return "M92 290 L92 359";
  const A = node(a), B = node(b);
  const [x1, y1] = edgePoint(A, B.x, B.y), [x2, y2] = edgePoint(B, A.x, A.y);
  return `M${x1.toFixed(1)} ${y1.toFixed(1)} L${x2.toFixed(1)} ${y2.toFixed(1)}`;
}
function loopEdge(m: Message): [string, string] {
  const from = m.from === "ops" ? "opsbox" : m.from, to = m.to === "ops" ? "opsbox" : m.to;
  return [from, to];
}

export default function AgentDiagram({ loop, loopSource, busy, traces, minute, interval, harness, proposals, time, edgeInfo, nodeName }: {
  loop: Message[]; loopSource: string; busy: boolean; traces: Data[]; minute: number; interval: number; harness: Data; proposals: Data[];
  time: (m: any) => string; edgeInfo: (id: string) => EdgeInfo; nodeName: (id: string) => string;
}) {
  // Step through harness messages: follow live while running, replay once when a run completes.
  const [step, setStep] = useState<number | null>(null), [auto, setAuto] = useState(false);
  const signature = `${loopSource}:${loop.length}`, seen = useRef(signature);
  useEffect(() => {
    if (seen.current === signature) return;
    seen.current = signature;
    if (busy || !loop.length) { setStep(null); setAuto(false); return; }
    setStep(0); setAuto(true);
  }, [signature, busy, loop.length]);
  useEffect(() => {
    if (!auto) return;
    const t = setInterval(() => setStep(s => { const n = (s ?? 0) + 1; if (n >= loop.length - 1) { setAuto(false); return loop.length - 1; } return n; }), 2200);
    return () => clearInterval(t);
  }, [auto, loop.length]);
  const index = step === null ? loop.length - 1 : Math.min(step, loop.length - 1);
  const current = loop[index];
  const go = (d: number) => { setAuto(false); setStep(Math.max(0, Math.min(loop.length - 1, index + d))); };

  // Operator conversation recorded in the current replanning window of the replay.
  const recent = traces.filter(t => t.action !== "observe" && t.action !== "boarding_denied" && Number(t.minute) > minute - interval && Number(t.minute) <= minute);
  const chat: Chat[] = recent.flatMap(t => narrate(t, edgeInfo, nodeName, time));
  const opsActive = new Map<string, { count: number }>();
  const actions = new Map<string, number>();
  chat.forEach(c => {
    if (c.from === c.to) { actions.set(c.from, (actions.get(c.from) || 0) + 1); return; }
    const k = pairKey(c.from, c.to); opsActive.set(k, { count: (opsActive.get(k)?.count || 0) + 1 });
  });
  const feed = chat.slice(-4);
  const loopKey = current ? key(...loopEdge(current)) : "";
  const coordActive = (harness.active_agents || []).includes("regional_coordinator");
  const nodeStatus = (id: string) => {
    if (id === "coord" && !coordActive) {
      const tried = proposals.filter(d => (d.candidate?.active_agents || []).includes("regional_coordinator")).map(d => String(d.candidate?.version || "")).filter(Boolean)
        .sort((a, b) => Number(a.slice(1)) - Number(b.slice(1)));
      return tried.length ? `Proposed in ${tried[tried.length - 1]} · not approved yet` : `Not in ${harness.version || "v1"} yet`;
    }
    const nodeKind = node(id).kind;
    if (nodeKind === "harness") { const r = [...loop.slice(0, index + 1)].reverse().find(m => loopEdge(m)[1] === id); return r?.decision; }
    const talk = [...opsActive.entries()].filter(([k]) => k.split(">").includes(id)).reduce((n, [, v]) => n + v.count, 0), acts = actions.get(id) || 0;
    return [talk && `${talk} message${talk === 1 ? "" : "s"}`, acts && `${acts} action${acts === 1 ? "" : "s"}`].filter(Boolean).join(" · ") || undefined;
  };
  const touched = new Set<string>([...(current ? loopEdge(current) : []), ...[...opsActive.keys()].flatMap(k => k.split(">")), ...actions.keys()]);

  return (
    <section className="agent-diagram panel" aria-label="Agent communication diagram">
      <div className="panel-heading">
        <div><span className="small-caps">AGENT COMMUNICATION</span><h2>Who talks to whom.</h2></div>
        <span className="version-tag" title="Active harness version">{harness.version || "v1"}</span>
      </div>
      <svg viewBox="-12 0 544 540" className="diagram-svg" role="img" aria-label="Transport operator agents and harness agents with their messages">
        <defs>
          <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L8 4L0 8z" fill="#4f6349" /></marker>
          <marker id="arrow-on" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L8 4L0 8z" fill="#d6ecb0" /></marker>
        </defs>
        <rect x={OPS_BOX.x} y={OPS_BOX.y} width={OPS_BOX.w} height={OPS_BOX.h} rx="12" className={`ops-box${touched.has("opsbox") ? " on" : ""}`} />
        <text x="0" y="16" className="diagram-zone">TRANSPORT OPERATOR AGENTS · run the network in the simulation</text>
        
        <text x="160" y="318" className="diagram-zone">HARNESS AGENTS · rewrite how the operators work</text>
        <text x="100" y="334" className="diagram-edge-note">service data · boarding times, queues</text>
        <text x="-4" y="300" className="diagram-edge-note" transform="rotate(-90 -4 300)">new operating setup</text>
        <text x="146" y="452" className="diagram-edge-note">memory</text>
        {EDGES.map(([a, b]) => {
          const k = key(a, b), ops = opsActive.get(k), on = k === loopKey || !!ops;
          const d = edgePath(a, b);
          return (
            <g key={k} className={`diagram-edge${on ? " on" : ""}${k === loopKey && busy ? " live" : ""}`}>
              <path d={d} markerEnd={`url(#${on ? "arrow-on" : "arrow"})`} markerStart={TWO_WAY.has(k) ? `url(#${on ? "arrow-on" : "arrow"})` : undefined} />
              {on && <circle r="3.6" className="packet"><animateMotion dur="1.4s" repeatCount="indefinite" path={d} /></circle>}
              {ops && ops.count > 1 && (() => { const A = node(a), B = node(b); return <text x={(A.x + B.x) / 2 + 8} y={(A.y + B.y) / 2 - 4} className="diagram-count">×{ops.count}</text>; })()}
            </g>
          );
        })}
        {NODES.map(n => {
          const status = nodeStatus(n.id), on = touched.has(n.id), dim = n.id === "coord" && !coordActive;
          return (
            <g key={n.id} className={`diagram-node ${n.kind}${on ? " on" : ""}${dim ? " dim" : ""}`}>
              {n.kind === "op" ? <circle cx={n.x} cy={n.y} r="28" style={{ stroke: n.color }} /> : <rect x={n.x - 68} y={n.y - 23} width={136} height={46} rx="7" />}
              {n.kind === "op" && <text x={n.x} y={n.y + 5} textAnchor="middle" className="diagram-glyph" style={{ fill: n.color }}>{n.id === "coord" ? "◎" : "▰"}</text>}
              {n.id === "coord" ? <>
                <text x={n.x + 38} y={n.y - 2} className="diagram-label">{n.label}</text>
                {status && <text x={n.x + 38} y={n.y + 12} className="diagram-status">{status}</text>}
              </> : <>
                <text x={n.x} y={n.kind === "op" ? n.y + 44 : n.y + (status && n.kind === "harness" ? -3 : 4)} textAnchor="middle" className="diagram-label">{n.label}</text>
                {status && <text x={n.x} y={n.kind === "op" ? n.y + 57 : n.y + 12} textAnchor="middle" className="diagram-status"><title>{status}</title>{status.length > 26 ? `${status.slice(0, 25)}…` : status}</text>}
              </>}
            </g>
          );
        })}
      </svg>
      <div className="diagram-captions">
        <div className="diagram-caption">
          <span className="small-caps">OPERATOR CHANNEL · {time(minute)}{chat.length > feed.length ? ` · latest ${feed.length} of ${chat.length}` : ""}</span>
          {feed.length ? <ol className="chat">{feed.map((c, i) => <li key={i} className={`chat-line from-${c.from}`}><b>{agentName[c.from]}<i>{c.from === c.to ? " · action" : ` → ${agentName[c.to]}`}</i></b><span>{c.text}</span>{c.decision && <em className={`tone-${c.tone}`}>{c.decision}</em>}</li>)}</ol> : <p className="muted">{traces.length ? "Quiet in this replay window. Scrub the timeline to hear the operators." : "Run the simulation to hear the operators coordinate."}</p>}
        </div>
        <div className="diagram-caption">
          <span className="small-caps">HARNESS CHANNEL · {loopSource || "no run yet"}</span>
          {current ? <ol className="chat"><li className={`chat-line from-${loopEdge(current)[0]}`}><b>{nameOf(loopEdge(current)[0])}<i> → {nameOf(loopEdge(current)[1])}</i></b><span>{current.label}</span>{current.detail && <small>{current.detail}</small>}<em className={`tone-${current.tone}`}>{current.decision}</em></li></ol> : <p className="muted">Run the autonomous simulation to watch the harness diagnose and test a change.</p>}
          {loop.length > 1 && <div className="diagram-stepper"><button aria-label="Previous message" onClick={() => go(-1)} disabled={index <= 0}>‹</button><span>Message {index + 1} / {loop.length}{current?.group ? ` · ${current.group}` : ""}</span><button aria-label="Next message" onClick={() => go(1)} disabled={index >= loop.length - 1}>›</button></div>}
        </div>
        <p className="diagram-footnote">Lines are plain-language renderings of actions the simulator and harness actually recorded; every count and stop name comes from the trace.</p>
      </div>
    </section>
  );
}
