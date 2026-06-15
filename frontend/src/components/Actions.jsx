import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const RISK_COLORS = { low: "var(--green)", medium: "var(--yellow)", high: "var(--red)" };

export default function Actions() {
  const [actions, setActions] = useState([]);

  async function load() {
    setActions(await api.actions());
  }
  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, []);

  async function approve(id) { await api.approveAction(id); load(); }
  async function reject(id) { await api.rejectAction(id); load(); }

  return (
    <>
      <div className="topbar">
        <h1>Remediation AI</h1>
        <span className="muted">Le azioni proposte richiedono la tua approvazione</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {actions.map((a) => (
          <div className="card" key={a.id}>
            <div className="spread">
              <div className="row">
                {a.proposed_by_ai && <span className="tag">🤖 AI</span>}
                <span className="tag" style={{ color: RISK_COLORS[a.risk] }}>rischio: {a.risk}</span>
                <span className="status-chip">{a.status}</span>
              </div>
              <span className="muted">{new Date(a.created_at).toLocaleString("it-IT")}</span>
            </div>
            {a.ai_reasoning && (
              <p style={{ marginBottom: 8 }}><span className="muted">Diagnosi: </span>{a.ai_reasoning}</p>
            )}
            <pre>{a.command}</pre>
            {a.output && (
              <details>
                <summary className="muted">Output (exit {a.exit_code})</summary>
                <pre>{a.output}</pre>
              </details>
            )}
            {a.status === "proposed" && (
              <div className="row" style={{ marginTop: 10 }}>
                <button className="primary success" onClick={() => approve(a.id)}>✅ Approva ed esegui</button>
                <button className="danger" onClick={() => reject(a.id)}>❌ Rifiuta</button>
              </div>
            )}
          </div>
        ))}
        {actions.length === 0 && <div className="card muted">Nessuna azione di remediation finora.</div>}
      </div>
    </>
  );
}
