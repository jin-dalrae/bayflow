type Data = Record<string, any>;
export type Message = { from: string; to: string; label: string; detail?: string; decision: string; tone: "ok" | "bad" | "neutral" | "live"; group?: string };

const ACTORS = [
  { id: "ops", label: "Transport operators", sub: "Muni · BART · Caltrain" },
  { id: "monitor", label: "Service monitor", sub: "Backend thresholds" },
  { id: "planner", label: "Planner agent", sub: "Proposes changes" },
  { id: "validator", label: "Validator", sub: "Schema & safety" },
  { id: "evaluator", label: "Evaluator", sub: "Held-out seeds" },
  { id: "gate", label: "Promotion gate", sub: "Frozen thresholds" },
  { id: "atlas", label: "MongoDB Atlas", sub: "Memory & record" },
];
const actorName = (id: string) => ACTORS.find(a => a.id === id)?.label || id;
const pct = (v: any) => (Number.isFinite(Number(v)) ? `${(Number(v) * 100).toFixed(0)}%` : "—");
const short = (v: any) => {
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s === undefined ? "none" : s.length > 28 ? `${s.slice(0, 26)}…` : s.replace(/_/g, " ");
};
const label = (v: any) => String(v).replace(/_/g, " ");
const describeChange = (c: Data) => {
  const path = label(String(c.path).replace(/^rules\./, "rule "));
  if (Array.isArray(c.before) || Array.isArray(c.after)) {
    const before: any[] = c.before || [], after: any[] = c.after || [];
    const added = after.filter(x => !before.includes(x)).map(label), removed = before.filter(x => !after.includes(x)).map(label);
    return `${path}: ${[...added.map(x => `+${x}`), ...removed.map(x => `−${x}`)].join(", ") || "reordered"}`;
  }
  if (c.operation === "add") return `add ${path}`;
  if (c.operation === "remove") return `remove ${path}`;
  return `${path}: ${short(c.before)} → ${short(c.after)}`;
};
const diffSummary = (diff: Data[] = []) =>
  diff.length ? diff.slice(0, 3).map(describeChange).join(" · ") + (diff.length > 3 ? ` · +${diff.length - 3} more` : "") : "no configuration change";
const plannerName = (p: Data | undefined) => (p?.kind === "llm" ? `LLM · ${p.model || p.provider}` : p?.kind === "rule_based" ? "Rule-based planner" : "Planner");
const version = (d: Data) => d.candidate?.version || d.proposal?.candidate?.version || "candidate";

// Live stage text from the backend job → which actor sent a message to which.
function liveRoute(stage: string): [string, string] {
  if (/^Starting|^Queued/.test(stage)) return ["ops", "monitor"];
  if (/^Monitoring/.test(stage)) return ["ops", "monitor"];
  if (/^Checking/.test(stage)) return ["monitor", "monitor"];
  if (/triggered/.test(stage)) return ["monitor", "planner"];
  if (/^Monitor passed/.test(stage)) return ["monitor", "atlas"];
  if (/^Analyzing|^Reviewing/.test(stage)) return ["ops", "planner"];
  if (/^Proposing/.test(stage)) return ["planner", "validator"];
  if (/^Validating/.test(stage)) return ["validator", "evaluator"];
  if (/held-out evaluation/.test(stage)) return ["evaluator", "evaluator"];
  if (/^Comparing/.test(stage)) return ["evaluator", "gate"];
  if (/^Promoting|^Rejecting/.test(stage)) return ["gate", "atlas"];
  if (/three-way/.test(stage)) return ["evaluator", "evaluator"];
  return ["ops", "ops"];
}

function liveMessages(job: Data): Message[] {
  const stages: string[] = (job.history || []).map((h: Data) => h.stage);
  const rows: Message[] = [];
  stages.forEach(stage => {
    const [from, to] = liveRoute(stage);
    const previous = rows[rows.length - 1];
    if (previous && /held-out evaluation/.test(stage) && /held-out evaluation/.test(previous.label)) { previous.label = stage; return; }
    if (previous) { previous.decision = "Done"; previous.tone = "ok"; }
    rows.push({ from, to, label: stage, decision: "Working…", tone: "live" });
  });
  return rows;
}

function cycleMessages(trigger: Data | null | undefined, decisions: Data[], startVersion: string, healthy: boolean, time: (m: any) => string, stored: boolean): Message[] {
  const rows: Message[] = [];
  if (trigger || healthy) {
    const obs = trigger?.observations?.[trigger.observations.length - 1];
    rows.push({
      from: "ops", to: "monitor", label: obs?.boarding_within_10_rate !== undefined ? `Service report on harness ${startVersion}: ${pct(obs.boarding_within_10_rate)} of riders boarded within 10 minutes (target 80%); ${obs.crowded_waiting_riders ?? 0} waiting in crowded queues.` : `Service report on harness ${startVersion}.`,
      detail: obs && obs.boarding_within_10_rate === undefined ? `Average delay ${obs.average_passenger_delay} min · ${obs.unserved_passengers} unserved` : undefined,
      decision: trigger ? `Below target since ${time(trigger.minute)}` : "On target", tone: trigger ? "bad" : "ok",
    });
  }
  if (healthy && !trigger) {
    rows.push({ from: "monitor", to: "atlas", label: "Riders are boarding on time. Logging a healthy window; nothing to change.", decision: `Keep harness ${startVersion}; no change requested`, tone: "ok" });
    return rows;
  }
  rows.push({
    from: trigger ? "monitor" : "ops", to: "planner",
    label: trigger ? `Riders have been missing the 10-minute boarding target since ${time(trigger.minute)}, two checks in a row. Please find a better setup.` : "Manual request: propose and test a better setup.",
    decision: decisions[0]?.proposal?.diagnosis ? `Diagnosis: ${decisions[0].proposal.diagnosis}` : "Review rider journeys", tone: "neutral",
  });
  decisions.forEach((d, i) => {
    const v = version(d), group = `Attempt ${i + 1} · ${plannerName(d.planner)} · candidate ${v}`;
    const seeds = d.evaluation_seeds?.length || 5;
    rows.push({ group, from: "planner", to: "validator", label: `Let's try ${v}: ${diffSummary(d.config_diff)}.`, detail: d.proposal?.rationale, decision: "Valid · passed schema & safety envelope", tone: "ok" });
    rows.push({
      group, from: "validator", to: "evaluator", label: `${v} is well-formed and inside the safety limits. Race it against ${d.parent_version} on ${seeds} days it has never seen.`,
      decision: d.seed_wins !== undefined ? `${d.seed_wins}/${seeds} seeds improved · ${Number(d.improvement_percent) >= 0 ? "+" : ""}${Number(d.improvement_percent || 0).toFixed(1)}% objective` : stored ? "Measured · see history" : "Measured",
      tone: d.seed_wins !== undefined ? (d.seed_wins >= (d.required_seed_wins ?? 3) ? "ok" : "bad") : "neutral",
    });
    rows.push({
      group, from: "evaluator", to: "gate",
      label: d.before?.objective !== undefined ? `Results are in${d.seed_wins !== undefined ? `: ${v} beat ${d.parent_version} on ${d.seed_wins} of ${seeds} days` : ` for ${v}`}; overall cost ${Number(d.before.objective).toFixed(3)} → ${Number(d.after.objective).toFixed(3)} (lower is better).` : `Results for ${v} are in.`,
      decision: d.accepted ? `PROMOTE ${v}` : `REJECT · ${d.reason || "gate not met"}`, tone: d.accepted ? "ok" : "bad",
    });
    rows.push({ group, from: "gate", to: "atlas", label: d.accepted ? `Promote ${v}: it cleared every gate. Make it the active harness.` : `Reject ${v}: ${d.reason || "gate not met"}. Keep ${d.parent_version}.`, decision: d.accepted ? `Active harness → ${v}` : `Stored as rejected; ${d.parent_version} stays active`, tone: d.accepted ? "ok" : "neutral" });
    if (d.accepted) rows.push({ group, from: "atlas", to: "ops", label: `Harness ${v} is live. Operators, switch to the new setup.`, decision: "Agents run the new architecture", tone: "ok" });
    if (i < decisions.length - 1) rows.push({ group, from: "atlas", to: "planner", label: `Note for your next attempt: ${v} ${d.accepted ? "worked" : "failed"}${d.reason ? `. ${d.reason}` : ""}.`, decision: `Re-plan with this lesson → attempt ${i + 2}`, tone: "neutral" });
  });
  return rows;
}

export function buildLoopMessages({ job, result, busy, action, history, time }: { job: Data | null; result: Data | null; busy: boolean; action: string; history: Data[]; time: (m: any) => string }): { rows: Message[]; source: string } {
  if (busy && job && action !== "baseline") return { rows: liveMessages(job), source: "Live · streaming from the backend job" };
  if (result && action !== "baseline") {
    const start = result.operations?.harness_version || result.initial?.version || result.decisions?.[0]?.parent_version || result.current?.version || "v1";
    return { rows: cycleMessages(result.automatic_trigger, result.decisions || [], start, !!result.operations, time, false), source: "This run" };
  }
  if (history.length) {
    const last = history[history.length - 1];
    const key = last.automatic_trigger?.source_run_id;
    const cycle = key ? history.filter(d => d.automatic_trigger?.source_run_id === key) : [last];
    return { rows: cycleMessages(last.automatic_trigger, cycle, cycle[0]?.parent_version || "v1", false, time, true), source: `Last stored cycle${last.created_at ? ` · ${new Date(last.created_at).toLocaleString()}` : ""}` };
  }
  return { rows: [], source: "" };
}

export function MessageRow({ m, onHover, active, extra = "" }: { m: Message; onHover?: (m: Message | null) => void; active?: boolean; extra?: string }) {
  return (
    <li className={`message-row tone-${m.tone}${active ? " active" : ""} ${extra}`} onMouseEnter={() => onHover?.(m)} onMouseLeave={() => onHover?.(null)}>
      <span className="message-route"><b>{actorName(m.from)}</b><i>→</i><b>{actorName(m.to)}</b></span>
      <span className="message-body">{m.label}{m.detail && <small>{m.detail}</small>}</span>
      <span className="message-decision">{m.decision}</span>
    </li>
  );
}

export default function AgentFlow({ rows, source }: { rows: Message[]; source: string }) {
  const groups: [string | undefined, Message[]][] = [];
  rows.forEach(m => { const g = groups[groups.length - 1]; if (g && g[0] === m.group) g[1].push(m); else groups.push([m.group, [m]]); });
  return rows.length ? (
    <div className="message-log agent-flow" aria-label="Harness conversation log">
      <div className="message-head"><span>From → to · {source}</span><span>Message</span><span>Decision</span></div>
      {groups.map(([group, items], gi) => (
        <ol key={gi}>
          {group && <li className="message-group">{group}</li>}
          {items.map((m, i) => <MessageRow key={i} m={m} />)}
        </ol>
      ))}
    </div>
  ) : <p className="flow-empty">No harness messages yet.</p>;
}
