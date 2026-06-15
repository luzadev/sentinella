// Tiny fetch wrapper that injects the JWT and handles JSON.
const TOKEN_KEY = "sentinella_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let payload;
  if (form) {
    payload = new URLSearchParams(form);
    headers["Content-Type"] = "application/x-www-form-urlencoded";
  } else if (body !== undefined) {
    payload = JSON.stringify(body);
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { method, headers, body: payload });
  if (res.status === 401) {
    setToken(null);
    throw new Error("Sessione scaduta");
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Errore ${res.status}`);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  login: (username, password) =>
    request("/api/auth/login", { method: "POST", form: { username, password } }),
  me: () => request("/api/auth/me"),
  servers: () => request("/api/servers"),
  serverMetrics: (id, limit = 120) => request(`/api/servers/${id}/metrics?limit=${limit}`),
  deleteServer: (id) => request(`/api/servers/${id}`, { method: "DELETE" }),
  alerts: () => request("/api/alerts"),
  ackAlert: (id) => request(`/api/alerts/${id}/acknowledge`, { method: "POST" }),
  rules: () => request("/api/alert-rules"),
  createRule: (body) => request("/api/alert-rules", { method: "POST", body }),
  deleteRule: (id) => request(`/api/alert-rules/${id}`, { method: "DELETE" }),
  actions: () => request("/api/actions"),
  approveAction: (id) => request(`/api/actions/${id}/approve`, { method: "POST" }),
  rejectAction: (id) => request(`/api/actions/${id}/reject`, { method: "POST" }),
  manualAction: (body) => request("/api/actions", { method: "POST", body }),
  backupJobs: () => request("/api/backups/jobs"),
  createBackupJob: (body) => request("/api/backups/jobs", { method: "POST", body }),
  deleteBackupJob: (id) => request(`/api/backups/jobs/${id}`, { method: "DELETE" }),
  runBackup: (id) => request(`/api/backups/jobs/${id}/run`, { method: "POST" }),
  backupRuns: () => request("/api/backups/runs"),
};
