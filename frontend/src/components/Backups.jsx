import React, { useEffect, useState } from "react";
import { api } from "../api.js";

function bytes(n) {
  if (!n) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0; let v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${u[i]}`;
}

export default function Backups() {
  const [jobs, setJobs] = useState([]);
  const [runs, setRuns] = useState([]);
  const [servers, setServers] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ server_id: "", name: "", paths: "", schedule_cron: "0 3 * * *", retention: 7 });

  async function load() {
    const [j, r, s] = await Promise.all([api.backupJobs(), api.backupRuns(), api.servers()]);
    setJobs(j); setRuns(r); setServers(s);
  }
  useEffect(() => {
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, []);

  async function save() {
    await api.createBackupJob({
      server_id: Number(form.server_id),
      name: form.name,
      paths: form.paths.split("\n").map((p) => p.trim()).filter(Boolean),
      schedule_cron: form.schedule_cron,
      retention: Number(form.retention),
    });
    setOpen(false);
    setForm({ server_id: "", name: "", paths: "", schedule_cron: "0 3 * * *", retention: 7 });
    load();
  }
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const serverName = (id) => servers.find((s) => s.id === id)?.name || `#${id}`;

  return (
    <>
      <div className="topbar">
        <h1>Backup</h1>
        <button className="primary" onClick={() => setOpen(true)} disabled={servers.length === 0}>+ Nuovo job</button>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h2>Job pianificati</h2>
        <table>
          <thead><tr><th>Nome</th><th>Server</th><th>Path</th><th>Cron</th><th>Retention</th><th></th></tr></thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td>{j.name}</td>
                <td>{serverName(j.server_id)}</td>
                <td><code>{(j.paths || []).join(", ")}</code></td>
                <td><code>{j.schedule_cron}</code></td>
                <td>{j.retention}</td>
                <td className="row">
                  <button onClick={() => api.runBackup(j.id).then(load)}>▶ Esegui ora</button>
                  <button className="danger" onClick={() => api.deleteBackupJob(j.id).then(load)}>Elimina</button>
                </td>
              </tr>
            ))}
            {jobs.length === 0 && <tr><td colSpan={6} className="muted">Nessun job configurato.</td></tr>}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>Esecuzioni recenti</h2>
        <table>
          <thead><tr><th>Server</th><th>Stato</th><th>Archivio</th><th>Dimensione</th><th>Avviato</th></tr></thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id}>
                <td>{serverName(r.server_id)}</td>
                <td><span className="status-chip">{r.status}</span></td>
                <td><code>{r.archive_path || "—"}</code></td>
                <td>{bytes(r.size_bytes)}</td>
                <td className="muted">{new Date(r.started_at).toLocaleString("it-IT")}</td>
              </tr>
            ))}
            {runs.length === 0 && <tr><td colSpan={5} className="muted">Nessuna esecuzione.</td></tr>}
          </tbody>
        </table>
      </div>

      {open && (
        <div className="modal-bg" onClick={() => setOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Nuovo job di backup</h2>
            <div className="field"><label>Server</label>
              <select value={form.server_id} onChange={set("server_id")}>
                <option value="">— seleziona —</option>
                {servers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div className="field"><label>Nome</label><input value={form.name} onChange={set("name")} /></div>
            <div className="field"><label>Path da archiviare (uno per riga)</label>
              <textarea rows={3} style={{ background: "var(--bg)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: 8 }}
                value={form.paths} onChange={set("paths")} placeholder="/etc&#10;/var/www" />
            </div>
            <div className="row">
              <div className="field" style={{ flex: 2 }}><label>Cron</label><input value={form.schedule_cron} onChange={set("schedule_cron")} /></div>
              <div className="field" style={{ flex: 1 }}><label>Retention</label><input type="number" value={form.retention} onChange={set("retention")} /></div>
            </div>
            <div className="row">
              <button className="primary" onClick={save} disabled={!form.server_id || !form.name}>Salva</button>
              <button onClick={() => setOpen(false)}>Annulla</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
