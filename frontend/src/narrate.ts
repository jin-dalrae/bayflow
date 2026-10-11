// Plain-language lines for recorded agent actions. Every number comes from the trace.
type Data = Record<string, any>;
export type EdgeInfo = { route: string; from: string; to: string };
export type Chat = { minute: number; from: string; to: string; text: string; decision?: string; tone: "ok" | "bad" | "neutral" | "live" };

// Riders are not agents: an operator acting on its own network is a self-action (from === to).
export const agentId = (s: string = "") => (/muni/i.test(s) ? "muni" : /bart/i.test(s) ? "bart" : /caltrain/i.test(s) ? "caltrain" : "coord");
export const agentName: Record<string, string> = { coord: "Regional coordinator", muni: "Muni agent", bart: "BART agent", caltrain: "Caltrain agent" };
const pick = (t: Data, options: string[]) => options[(Number(t.minute) + String(t.edge_id || t.origin || "").length) % options.length];
const service = (op: string = "", svc: string = "") => `${op.replace(/ Bus| Metro/, "")} ${svc}`.trim();

export function narrate(t: Data, edge: (id: string) => EdgeInfo, place: (id: string) => string, time: (m: any) => string): Chat[] {
  const m = Number(t.minute);
  if (t.action === "passenger_advisory") {
    const op = agentId(t.requested_operator), crowded = service(t.requested_operator, t.requested_service), alt = service(t.alternative_operator, t.alternative_service);
    return [
      { minute: m, from: "coord", to: op, tone: "neutral", text: `${crowded} is crowded at ${place(t.origin)}. Post a sign there: ${alt} reaches ${place(t.destination)} by about ${time(t.alternative_eta)}.` },
      { minute: m, from: op, to: "coord", tone: t.accepted_count ? "ok" : "neutral", text: `Sign posted at ${place(t.origin)} pointing riders to ${alt}.`, decision: `${t.accepted_count} of ${t.offered_count} riders switched` },
    ];
  }
  const e = t.edge_id ? edge(t.edge_id) : { route: "", from: "", to: "" };
  const op = agentId(t.provider_agent || t.operator || t.agent);
  if (t.action === "standby_dispatch" && t.agent === "regional_coordinator")
    return [
      { minute: m, from: "coord", to: op, tone: "neutral", text: pick(t, [
        `${t.observed_queue} riders are waiting for ${e.route} at ${e.from}. Can you add a standby vehicle?`,
        `${e.from} needs help: ${t.observed_queue} people queued for ${e.route}. Please add a run.`,
        `Priority request: ${e.route} at ${e.from} has ${t.observed_queue} waiting. Send your next standby vehicle there.`,
      ]) },
      { minute: m, from: op, to: "coord", tone: "ok", text: `On it: standby vehicle out on ${e.route} from ${e.from} toward ${e.to}.`, decision: "Dispatched" },
    ];
  if (t.action === "standby_dispatch")
    return [{ minute: m, from: op, to: op, tone: "ok", decision: "Dispatched", text: pick(t, [
      `${t.observed_queue} riders are stuck at ${e.from} on ${e.route}. Sending a standby vehicle toward ${e.to}.`,
      `${e.route} is backing up at ${e.from} (${t.observed_queue} waiting). Extra vehicle heading to ${e.to}.`,
      `Queue of ${t.observed_queue} at ${e.from}. Releasing a standby ${e.route} run toward ${e.to}.`,
    ]) }];
  if (t.action === "service_hold")
    return [
      { minute: m, from: "coord", to: op, tone: "neutral", text: `Only ${t.observed_queue} riders on ${e.route} at ${e.from}. Skip this run; the next one still arrives inside 10 minutes.` },
      { minute: m, from: op, to: "coord", tone: "neutral", text: `Agreed. Skipping this ${e.route} departure at ${e.from}.`, decision: "Departure skipped" },
    ];
  if (t.action === "hold_for_transfer")
    return [{ minute: m, from: op, to: op, tone: "ok", text: `Holding ${e.route} at ${e.from} for ${t.hold_minutes} min so ${t.riders_affected} connecting riders can make it.`, decision: "Held for transfer" }];
  if (t.tool === "operating_rule")
    return [{ minute: m, from: op, to: op, tone: "neutral", text: `Rule ${t.rule_id} tripped on ${e.route} at ${e.from} (signal ${Number(t.signal_value).toFixed(2)}).`, decision: `${String(t.action).replace(/_/g, " ")} requested` }];
  return [{ minute: m, from: op, to: op, tone: "neutral", text: `${String(t.action).replace(/_/g, " ")}${e.route ? ` on ${e.route} at ${e.from}` : ""}.` }];
}
