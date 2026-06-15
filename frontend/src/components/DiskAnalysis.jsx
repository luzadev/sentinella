import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

function bytes(n) {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
}

function parentPath(p) {
  if (!p || p === "/") return "/";
  const trimmed = p.replace(/\/+$/, "");
  const idx = trimmed.lastIndexOf("/");
  return idx <= 0 ? "/" : trimmed.slice(0, idx);
}

export default function DiskAnalysis({ serverId }) {
  const [path, setPath] = useState("/");
  const [scan, setScan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const pendingId = useRef(null);
  const poll = useRef(null);

  // carica l'ultima scansione disponibile all'apertura
  useEffect(() => {
    api.getDiskScan(serverId).then((s) => {
      if (s) { setScan(s); setPath(s.path); }
    }).catch(() => {});
    return () => clearInterval(poll.current);
  }, [serverId]);

  async function analyze(targetPath) {
    setError("");
    setLoading(true);
    try {
      const created = await api.requestDiskScan(serverId, targetPath);
      pendingId.current = created.id;
      setPath(targetPath);
      clearInterval(poll.current);
      poll.current = setInterval(async () => {
        const s = await api.getDiskScan(serverId);
        if (s && s.id === pendingId.current && (s.status === "done" || s.status === "failed")) {
          clearInterval(poll.current);
          setScan(s);
          setLoading(false);
          if (s.status === "failed") setError(s.error || "Analisi fallita");
        }
      }, 3000);
    } catch (e) {
      setError(e.message);
      setLoading(false);
    }
  }

  async function remove(entry) {
    if (!window.confirm(`Eliminare definitivamente?\n\n${entry.path}\n(${bytes(entry.size_bytes)})\n\nL'operazione non è reversibile.`)) return;
    setError("");
    try {
      await api.deletePath(serverId, entry.path);
      // l'eliminazione è eseguita dall'agent al prossimo heartbeat; poi ri-analizziamo
      setTimeout(() => analyze(path), 16000);
      setError("Eliminazione accodata: verrà eseguita entro pochi secondi, poi la cartella sarà rianalizzata.");
    } catch (e) {
      setError(e.message);
    }
  }

  const entries = scan?.entries || [];
  const maxSize = entries.length ? entries[0].size_bytes || 1 : 1;

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h2>Analisi disco</h2>
      <div className="row" style={{ marginBottom: 10 }}>
        <input
          style={{ flex: 1 }} value={path} onChange={(e) => setPath(e.target.value)}
          placeholder="/percorso/da/analizzare"
          onKeyDown={(e) => e.key === "Enter" && analyze(path)}
        />
        <button onClick={() => analyze(parentPath(path))} disabled={loading || path === "/"}>↑ Su</button>
        <button className="primary" onClick={() => analyze(path)} disabled={loading}>
          {loading ? "Analisi…" : "Analizza"}
        </button>
      </div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        Percorso analizzato: <code>{scan?.path || "—"}</code>
        {scan?.finished_at ? ` · ${new Date(scan.finished_at).toLocaleString("it-IT")}` : ""}
      </div>
      {error && <div className="error" style={{ marginBottom: 8 }}>{error}</div>}
      {loading && <div className="muted">Scansione in corso sull'host… (può richiedere qualche secondo)</div>}

      {!loading && entries.length > 0 && (
        <table>
          <thead>
            <tr><th>Nome</th><th style={{ width: 120 }}>Dimensione</th><th style={{ width: 160 }}></th></tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.path}>
                <td>
                  {e.is_dir ? "📁 " : "📄 "}
                  {e.is_dir ? (
                    <a style={{ cursor: "pointer" }} onClick={() => analyze(e.path)}>{e.name}</a>
                  ) : (
                    <span>{e.name}</span>
                  )}
                  <div className="bar" style={{ maxWidth: 320 }}>
                    <span className={e.size_bytes / maxSize > 0.66 ? "crit" : e.size_bytes / maxSize > 0.33 ? "warn" : ""}
                      style={{ width: `${Math.max(2, (e.size_bytes / maxSize) * 100)}%` }} />
                  </div>
                </td>
                <td>{bytes(e.size_bytes)}</td>
                <td>
                  {e.is_dir && <button onClick={() => analyze(e.path)}>Apri</button>}{" "}
                  <button className="danger" onClick={() => remove(e)}>Elimina</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {!loading && scan && entries.length === 0 && !error && (
        <div className="muted">Nessuna voce in questo percorso.</div>
      )}
    </div>
  );
}
