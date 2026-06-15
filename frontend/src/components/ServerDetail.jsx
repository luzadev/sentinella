import React, { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { api } from "../api.js";
import DiskAnalysis from "./DiskAnalysis.jsx";

export default function ServerDetail({ serverId, onBack }) {
  const [metrics, setMetrics] = useState([]);
  const [last, setLast] = useState(null);
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
    setLast(m[m.length - 1] || null);
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

  const osi = server?.os_info || {};
  const ext = last?.extra || {};
  const vhosts = ext.vhosts || [];
  const services = ext.services || {};
  const ports = ext.listen_ports || [];

  return (
    <>
      <div className="topbar">
        <div className="row">
          <button onClick={onBack}>← Indietro</button>
          <h1>{server?.name || `Server #${serverId}`}</h1>
          <span className={`dot ${server?.status || "unknown"}`} />
        </div>
        <span className="muted">{server?.hostname}{osi.ip_public ? ` · ${osi.ip_public}` : ""}</span>
      </div>

      <div className="grid" style={{ marginBottom: 16, gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))" }}>
        <div className="card"><div className="muted">CPU</div><div className="metric-num">{last?.cpu_percent?.toFixed(0) ?? "—"}%</div></div>
        <div className="card"><div className="muted">RAM</div><div className="metric-num">{last?.mem_percent?.toFixed(0) ?? "—"}%</div></div>
        <div className="card"><div className="muted">Disco</div><div className="metric-num">{last?.disk_percent?.toFixed(0) ?? "—"}%</div></div>
        <div className="card">
          <div className="muted">Uptime</div>
          <div style={{ marginTop: 6 }}>{last?.uptime_seconds ? `${Math.floor(last.uptime_seconds / 86400)}g ${Math.floor((last.uptime_seconds % 86400) / 3600)}h` : "—"}</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="grid" style={{ gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
          <div><div className="muted">Sistema operativo</div><div>{osi.distro || "—"}</div></div>
          <div><div className="muted">IP pubblico</div><div>{osi.ip_public || "—"}</div></div>
          <div>
            <div className="muted">IP locali</div>
            <div>{(osi.ips || []).length ? osi.ips.map((x) => `${x.ip} (${x.iface})`).join(", ") : (osi.ip_local || "—")}</div>
          </div>
          <div><div className="muted">CPU / RAM tot.</div><div>{osi.cpu_count ?? "—"} core · {osi.total_mem_gb ?? "—"} GB</div></div>
        </div>
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

      <div className="card" style={{ marginBottom: 16 }}>
        <h2>Virtual host & certificati SSL</h2>
        {vhosts.length === 0 ? (
          <p className="muted" style={{ marginTop: 0 }}>
            Nessun virtual host rilevato (l'agent legge i vhost Apache; puoi aggiungerne con SENTINELLA_TLS_DOMAINS).
          </p>
        ) : (
          <table>
            <thead>
              <tr><th>Dominio</th><th>Porte</th><th>SSL</th><th>Scadenza</th><th>Reverse proxy</th></tr>
            </thead>
            <tbody>
              {vhosts.map((v) => {
                const d = v.ssl_days_left;
                const sslCls = v.ssl_valid === false ? "sev-critical" : d != null && d < 14 ? "sev-warning" : "sev-info";
                const sslTxt = v.ports?.includes(443)
                  ? (v.ssl_valid === false ? "NON VALIDO" : v.ssl_valid ? "valido" : "—")
                  : "no HTTPS";
                const proxies = v.proxies || [];
                return (
                  <tr key={v.domain}>
                    <td>
                      <span className="dot online" />{" "}
                      <a href={`https://${v.domain}`} target="_blank" rel="noreferrer">{v.domain}</a>
                    </td>
                    <td className="muted">{(v.ports || []).join(", ")}</td>
                    <td className={sslCls} title={v.error || ""}>{sslTxt}</td>
                    <td>{d != null && v.ssl_valid ? `tra ${d} giorni` : "—"}</td>
                    <td>
                      {proxies.length === 0 ? (
                        <span className="muted">—</span>
                      ) : (
                        proxies.map((p, i) => (
                          <div key={i} style={{ fontSize: 12, marginBottom: 2 }}>
                            <code>{p.path}</code> <span className="muted">→</span> <code>{p.target}</code>
                          </div>
                        ))
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <DiskAnalysis serverId={serverId} />

      <div className="grid" style={{ marginBottom: 16, gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))" }}>
        <div className="card">
          <h2>Servizi</h2>
          {Object.keys(services).length === 0 ? (
            <p className="muted" style={{ marginTop: 0 }}>Nessun servizio rilevato.</p>
          ) : (
            <table>
              <tbody>
                {Object.entries(services).map(([name, state]) => (
                  <tr key={name}>
                    <td><span className={`dot ${state === "active" ? "online" : "offline"}`} /> {name}</td>
                    <td className={state === "active" ? "sev-info" : "sev-critical"} style={{ textAlign: "right" }}>{state}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="card">
          <h2>Porte in ascolto</h2>
          {ports.length === 0 ? (
            <p className="muted" style={{ marginTop: 0 }}>Nessuna porta rilevata.</p>
          ) : (
            <table>
              <tbody>
                {ports.map((p) => (
                  <tr key={p.port}><td><code>{p.port}</code></td><td className="muted" style={{ textAlign: "right" }}>{p.process}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
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
