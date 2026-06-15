import React, { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { api } from "../api.js";

export default function ServerDetail({ serverId, onBack }) {
  const [metrics, setMetrics] = useState([]);
  const [server, setServer] = useState(null);
  const [cmd, setCmd] = useState("");
  const [msg, setMsg] = useState("");

  async function load() {
    const [m, servers] = await Promise.all([api.serverMetrics(serverId), api.servers()]);
    setMetrics(
      m.map((x) => ({
        t: new Date(x.ts).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
        cpu: x.cpu_percent, mem: x.mem_percent, disk: x.disk_percent,
      }))
    );
    setServer(servers.find((s) => s.id === serverId));
  }
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [serverId]);

  async function sendCommand() {
    setMsg("");
    try {
      await api.manualAction({ server_id: serverId, command: cmd });
      setMsg("Comando accodato — verrà eseguito al prossimo heartbeat.");
      setCmd("");
    } catch (e) {
      setMsg(e.message);
    }
  }

  const latest = metrics[metrics.length - 1];
  const extra = server?.os_info || {};

  return (
    <>
      <div className="topbar">
        <div className="row">
          <button onClick={onBack}>← Indietro</button>
          <h1>{server?.name || `Server #${serverId}`}</h1>
          <span className={`dot ${server?.status || "unknown"}`} />
        </div>
        <span className="muted">{server?.hostname}</span>
      </div>

      <div className="grid" style={{ marginBottom: 16, gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))" }}>
        <div className="card"><div className="muted">CPU</div><div className="metric-num">{latest?.cpu?.toFixed(0) ?? "—"}%</div></div>
        <div className="card"><div className="muted">RAM</div><div className="metric-num">{latest?.mem?.toFixed(0) ?? "—"}%</div></div>
        <div className="card"><div className="muted">Disco</div><div className="metric-num">{latest?.disk?.toFixed(0) ?? "—"}%</div></div>
        <div className="card"><div className="muted">SO</div><div style={{ marginTop: 6 }}>{extra.distro || "—"}</div></div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h2>Andamento (CPU / RAM / Disco)</h2>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={metrics}>
            <CartesianGrid stroke="#2a3340" strokeDasharray="3 3" />
            <XAxis dataKey="t" stroke="#8b96a5" fontSize={11} minTickGap={40} />
            <YAxis stroke="#8b96a5" fontSize={11} domain={[0, 100]} />
            <Tooltip contentStyle={{ background: "#161b22", border: "1px solid #2a3340" }} />
            <Line type="monotone" dataKey="cpu" stroke="#3b82f6" dot={false} name="CPU %" />
            <Line type="monotone" dataKey="mem" stroke="#d29922" dot={false} name="RAM %" />
            <Line type="monotone" dataKey="disk" stroke="#f85149" dot={false} name="Disco %" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="card">
        <h2>Esegui comando manuale</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Il comando viene eseguito dall'agent sull'host. Usa con cautela.
        </p>
        <div className="row">
          <input
            style={{ flex: 1 }} placeholder="es. systemctl restart nginx"
            value={cmd} onChange={(e) => setCmd(e.target.value)}
          />
          <button className="primary" onClick={sendCommand} disabled={!cmd}>Esegui</button>
        </div>
        {msg && <div className="muted" style={{ marginTop: 8 }}>{msg}</div>}
      </div>
    </>
  );
}
