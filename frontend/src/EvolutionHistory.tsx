import { useEffect, useState } from "react";
import { MutationDiff, Rulebook } from "./Rulebook";
type Data = Record<string, any>;
export default function EvolutionHistory({ offline }: { offline: boolean }) {
  const [proposals, setProposals] = useState<Data[]>([]),
    [versions, setVersions] = useState<Data[]>([]),
    [evaluations, setEvaluations] = useState<Data[]>([]),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [filter, setFilter] = useState("all"),
    [version, setVersion] = useState("all"),
    [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    const query = offline ? "?offline=true" : "";
    Promise.allSettled(
      ["/harness/proposals", "/harness/versions", "/harness/evaluations"].map(
        async (path) => {
          const response = await fetch(`/api${path}${query}`);
          const data = await response.json();
          if (!response.ok)
            throw Error(
              typeof data.detail === "string"
                ? data.detail
                : JSON.stringify(data.detail),
            );
          return Array.isArray(data)
            ? data
            : data.proposals || data.versions || data.evaluations || [];
        },
      ),
    ).then((results) => {
      if (!active) return;
      const setters = [setProposals, setVersions, setEvaluations];
      results.forEach((result, index) => {
        if (result.status === "fulfilled") setters[index](result.value);
      });
      const failed = results.filter((result) => result.status === "rejected");
      if (failed.length)
        setError(
          "Some history records could not be retrieved. Restart the updated API or check Atlas connectivity.",
        );
      setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [offline, refresh]);
  const rows = proposals.filter(
    (p) =>
      (filter === "all" ||
        (filter === "accepted" ? p.accepted === true : p.accepted === false)) &&
      (version === "all" ||
        p.parent_version === version ||
        p.candidate?.version === version),
  );
  return (
    <main className="history-page">
      <div className="intro">
        <div>
          <div className="eyebrow">
            <span />
            PERSISTENT EVOLUTION AUDIT
          </div>
          <h1>
            Every change.
            <br />
            <span>Every measured outcome.</span>
          </h1>
          <p>
            Inspect architecture, executable rules and evaluation evidence
            across autonomous operation cycles.
          </p>
        </div>
        <a className="secondary history-back" href="#operations">
          ← Operations lab
        </a>
      </div>
      <div className={offline ? "offline-banner" : "history-source"}>
        {offline
          ? "OFFLINE PREVIEW · History records are held only in memory."
          : "ORGANIZER ATLAS · This page retrieves stored proposals, versions and evaluation records."}
      </div>
      <section className="history-controls panel">
        <label>
          Outcome{" "}
          <select
            aria-label="History outcome"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">All decisions</option>
            <option value="accepted">Promoted</option>
            <option value="rejected">Rejected</option>
          </select>
        </label>
        <label>
          Harness version{" "}
          <select
            aria-label="History version"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
          >
            <option value="all">All versions</option>
            {versions.map((v) => (
              <option key={v.version || v.config?.version}>
                {v.version || v.config?.version}
              </option>
            ))}
          </select>
        </label>
        <span>
          {proposals.length} proposals · {versions.length} versions ·{" "}
          {evaluations.length} evaluations
        </span>
        <button
          className="secondary"
          onClick={() => setRefresh((value) => value + 1)}
          disabled={loading}
        >
          Refresh records
        </button>
      </section>
      {error && <p className="database-warning">{error}</p>}
      {loading && <p className="muted">Loading actual persistence records…</p>}
      <div className="history-decisions">
        {rows.map((proposal, index) => {
          const evaluationId = proposal.evaluation_id || proposal.mutation_id || proposal._id;
          const evaluation = evaluationId ? evaluations.find(e => [e.evaluation_id,e.mutation_id,e._id].includes(evaluationId)) : undefined;
          const decision = { ...evaluation, ...proposal };
          return (
            <details
              className="history-entry panel"
              key={proposal.mutation_id || proposal.id || index}
              open={index === 0}
            >
              <summary>
                <span
                  className={
                    proposal.accepted
                      ? "decision-tag accepted"
                      : "decision-tag rejected"
                  }
                >
                  {proposal.accepted
                    ? "PROMOTED"
                    : proposal.accepted === false
                      ? "REJECTED"
                      : proposal.status || "PROPOSED"}
                </span>
                <b>
                  {proposal.scenario ? `${proposal.scenario} · ` : ""}{proposal.parent_version} →{" "}
                  {proposal.candidate?.version ||
                    proposal.version ||
                    "candidate"}
                </b>
                <span>
                  {proposal.created_at
                    ? new Date(proposal.created_at).toLocaleString()
                    : proposal.mutation_id || "Recorded mutation"}
                </span>
              </summary>
              <div className="history-body">
                <p>{proposal.reason || proposal.proposal?.rationale}</p>
                {(proposal.automatic_trigger ||
                  evaluation?.automatic_trigger) && (
                  <details open>
                    <summary>Measured automatic evolution trigger</summary>
                    <pre>
                      {JSON.stringify(
                        proposal.automatic_trigger ||
                          evaluation?.automatic_trigger,
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                )}
                <MutationDiff decision={decision} versions={versions} />
                {proposal.candidate && (
                  <Rulebook config={proposal.candidate} run={null} />
                )}
                <details>
                  <summary>
                    Complete stored proposal and evaluation record
                  </summary>
                  <pre>{JSON.stringify(decision, null, 2)}</pre>
                </details>
              </div>
            </details>
          );
        })}
      </div>
      {!loading && !rows.length && (
        <section className="panel history-empty">
          <h2>No matching evolution records.</h2>
          <p>
            Start autonomous operations or evaluate a candidate in the
            operations lab. Decisions appear after the backend persists them.
          </p>
        </section>
      )}
    </main>
  );
}
