import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Alerts() {
  const [alerts, setAlerts] = useState([]);

  async function load() {
    setAlerts(await api.alerts());
  }
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  async function ack(id) {
    await api.ackAlert(id);
    load();
  }

  return (
    <>
      <div className="topbar"><h1>Alert</h1></div>
      <div className="card">
        <table>
          <thead>
            <tr><th>Severità</th><th>Titolo</th><th>Valore</th><th>Stato</th><th>Creato</th><th></th></tr>
          </thead>
          <tbody>
            {alerts.map((a) => (
              <tr key={a.id}>
                <td className={`sev-${a.severity}`}>● {a.severity}</td>
                <td>{a.title}<div className="muted" style={{ fontSize: 12 }}>{a.message}</div></td>
                <td>{a.value?.toFixed(1)}</td>
                <td><span className="status-chip">{a.status}</span></td>
                <td className="muted">{new Date(a.created_at).toLocaleString("it-IT")}</td>
                <td>
                  {a.status === "firing" && <button onClick={() => ack(a.id)}>Riconosci</button>}
                </td>
              </tr>
            ))}
            {alerts.length === 0 && (
              <tr><td colSpan={6} className="muted">Nessun alert. Tutto tranquillo. 🌿</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
