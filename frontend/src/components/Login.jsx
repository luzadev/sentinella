import React, { useState } from "react";
import { api, setToken } from "../api.js";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api.login(username, password);
      setToken(res.access_token);
      onLogin();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <div className="brand" style={{ justifyContent: "center", paddingBottom: 8 }}>
          🛡️ Sentinella
        </div>
        <p className="muted" style={{ textAlign: "center", marginTop: 0 }}>
          Gestione e monitoraggio server Linux
        </p>
        <input placeholder="Utente" value={username} onChange={(e) => setUsername(e.target.value)} />
        <input
          type="password" placeholder="Password" value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <div className="error">{error}</div>}
        <button className="primary" style={{ width: "100%" }} disabled={busy}>
          {busy ? "Accesso..." : "Accedi"}
        </button>
      </form>
    </div>
  );
}
