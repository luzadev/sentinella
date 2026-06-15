import React, { useEffect, useState } from "react";
import { api, getToken, setToken } from "./api.js";
import Login from "./components/Login.jsx";
import Dashboard from "./components/Dashboard.jsx";
import ServerDetail from "./components/ServerDetail.jsx";
import Alerts from "./components/Alerts.jsx";
import Actions from "./components/Actions.jsx";
import Backups from "./components/Backups.jsx";
import Rules from "./components/Rules.jsx";

const NAV = [
  { key: "dashboard", label: "📊 Dashboard" },
  { key: "alerts", label: "🔔 Alert" },
  { key: "actions", label: "🤖 Remediation" },
  { key: "rules", label: "⚙️ Regole" },
  { key: "backups", label: "💾 Backup" },
];

export default function App() {
  const [authed, setAuthed] = useState(!!getToken());
  const [view, setView] = useState("dashboard");
  const [selectedServer, setSelectedServer] = useState(null);

  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  function logout() {
    setToken(null);
    setAuthed(false);
  }
  function openServer(id) {
    setSelectedServer(id);
    setView("server");
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">🛡️ Sentinella</div>
        {NAV.map((n) => (
          <button
            key={n.key}
            className={`nav-item ${view === n.key ? "active" : ""}`}
            onClick={() => setView(n.key)}
          >
            {n.label}
          </button>
        ))}
        <div style={{ marginTop: 24 }}>
          <button className="nav-item" onClick={logout}>🚪 Esci</button>
        </div>
      </aside>
      <main className="main">
        {view === "dashboard" && <Dashboard onOpenServer={openServer} />}
        {view === "server" && (
          <ServerDetail serverId={selectedServer} onBack={() => setView("dashboard")} />
        )}
        {view === "alerts" && <Alerts />}
        {view === "actions" && <Actions />}
        {view === "rules" && <Rules />}
        {view === "backups" && <Backups />}
      </main>
    </div>
  );
}
