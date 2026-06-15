import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const METRICS = ["cpu_percent", "mem_percent", "swap_percent", "disk_percent", "load1", "load5", "load15"];
const BLANK = {
  name: "", metric: "cpu_percent", operator: ">", threshold: 90,
  duration_seconds: 60, severity: "warning", enabled: true, auto_remediate: true,
};

export default function Rules() {
  const [rules, setRules] = useState([]);
  const [form, setForm] = useState(BLANK);
  const [open, setOpen] = useState(false);

  async function load() { setRules(await api.rules()); }
  useEffect(() => { load(); }, []);

  async function save() {
    await api.createRule({ ...form, threshold: Number(form.threshold), duration_seconds: Number(form.duration_seconds) });
    setOpen(false);
    setForm(BLANK);
    load();
  }
  async function remove(id) { await api.deleteRule(id); load(); }
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  return (
    <>
      <div className="topbar">
        <h1>Regole di alert</h1>
        <button className="primary" onClick={() => setOpen(true)}>+ Nuova regola</button>
      </div>
      <div className="card">
        <table>
          <thead>
            <tr><th>Nome</th><th>Condizione</th><th>Durata</th><th>Severità</th><th>AI</th><th>Attiva</th><th></th></tr>
          </thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td><code>{r.metric} {r.operator} {r.threshold}</code></td>
                <td>{r.duration_seconds}s</td>
                <td className={`sev-${r.severity}`}>{r.severity}</td>
                <td>{r.auto_remediate ? "🤖" : "—"}</td>
                <td>{r.enabled ? "✅" : "⏸️"}</td>
                <td><button className="danger" onClick={() => remove(r.id)}>Elimina</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {open && (
        <div className="modal-bg" onClick={() => setOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Nuova regola</h2>
            <div className="field"><label>Nome</label><input value={form.name} onChange={set("name")} /></div>
            <div className="field"><label>Metrica</label>
              <select value={form.metric} onChange={set("metric")}>
                {METRICS.map((m) => <option key={m}>{m}</option>)}
              </select>
            </div>
            <div className="row">
              <div className="field" style={{ flex: 1 }}><label>Operatore</label>
                <select value={form.operator} onChange={set("operator")}>
                  {[">", "<", ">=", "<=", "=="].map((o) => <option key={o}>{o}</option>)}
                </select>
              </div>
              <div className="field" style={{ flex: 1 }}><label>Soglia</label>
                <input type="number" value={form.threshold} onChange={set("threshold")} /></div>
            </div>
            <div className="field"><label>Durata sforamento (s)</label>
              <input type="number" value={form.duration_seconds} onChange={set("duration_seconds")} /></div>
            <div className="field"><label>Severità</label>
              <select value={form.severity} onChange={set("severity")}>
                {["info", "warning", "critical"].map((s) => <option key={s}>{s}</option>)}
              </select>
            </div>
            <label className="row" style={{ marginBottom: 14 }}>
              <input type="checkbox" checked={form.auto_remediate} onChange={set("auto_remediate")} style={{ width: "auto" }} />
              Proponi remediation AI quando scatta
            </label>
            <div className="row">
              <button className="primary" onClick={save} disabled={!form.name}>Salva</button>
              <button onClick={() => setOpen(false)}>Annulla</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
