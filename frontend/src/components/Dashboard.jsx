import React, { useEffect, useState } from "react";
import { api } from "../api.js";

function Gauge({ label, value }) {
  const v = value ?? 0;
  const cls = v >= 90 ? "crit" : v >= 75 ? "warn" : "";
  return (
    <div style={{ flex: 1 }}>
      <div className="spread">
        <span className="muted">{label}</span>
        <span>{value == null ? "—" : `${v.toFixed(0)}%`}</span>
      </div>
      <div className="bar"><span className={cls} style={{ width: `${Math.min(v, 100)}%` }} /></div>
    </div>
  );
}

export default function Dashboard({ onOpenServer }) {
  const [servers, setServers] = useState([]);
  const [error, setError] = useState("");

  async function load() {
    try {
      setServers(await api.servers());
    } catch (e) {
      setError(e.message);
    }
  }
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const online = servers.filter((s) => s.status === "online").length;

  return (
    <>
      <div className="topbar">
        <h1>Dashboard</h1>
        <span className="muted">{online}/{servers.length} server online</span>
      </div>
      {error && <div className="error">{error}</div>}
      {servers.length === 0 && (
        <div className="card">
          <h2>Nessun server registrato</h2>
          <p className="muted">
            Installa l'agent su un host Linux con l'enroll token configurato.
            Apparirà qui automaticamente al primo heartbeat.
          </p>
        </div>
      )}
      <div className="grid">
        {servers.map((s) => (
          <div key={s.id} className="card clickable" onClick={() => onOpenServer(s.id)}>
            <div className="spread" style={{ marginBottom: 10 }}>
              <div className="row">
                <span className={`dot ${s.status}`} />
                <strong>{s.name}</strong>
              </div>
              <span className="status-chip">{s.status}</span>
            </div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
              {s.os_info?.distro || s.hostname || "—"}
            </div>
            {s.latest ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <Gauge label="CPU" value={s.latest.cpu_percent} />
                <Gauge label="RAM" value={s.latest.mem_percent} />
                <Gauge label="Disco" value={s.latest.disk_percent} />
                <div className="muted" style={{ fontSize: 12 }}>load1: {s.latest.load1?.toFixed(2)}</div>
              </div>
            ) : (
              <div className="muted">In attesa di metriche…</div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
