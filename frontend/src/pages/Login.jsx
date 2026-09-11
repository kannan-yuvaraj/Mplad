import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../AuthContext.jsx";
import Logo from "../components/Logo.jsx";

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [accounts, setAccounts] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { login } = useAuth();
  const nav = useNavigate();

  useEffect(() => { api.demoAccounts().then(setAccounts).catch(() => {}); }, []);

  async function submit(e) {
    e.preventDefault();
    if (!username || !password || busy) return;
    setBusy(true);
    setError("");
    try {
      await login(username, password);
      nav("/overview");
    } catch {
      setError("Incorrect username or password.");
      setBusy(false);
    }
  }

  function useAccount(u) {
    setUsername(u);
    setPassword(accounts?.shared_password || "");
    setError("");
  }

  return (
    <div className="login-page">
      <div className="login-grid" />
      <div className="login-card">
        <div className="login-head">
          <Logo size={46} className="login-logo" />
          <div>
            <div className="login-title">MPLADS Intelligence</div>
            <div className="login-sub">Office of Public Works Monitoring</div>
          </div>
        </div>

        <form onSubmit={submit} className="login-form">
          <label className="login-label" htmlFor="u">Username</label>
          <input id="u" className="input" value={username} autoComplete="username"
            onChange={(e) => setUsername(e.target.value)} placeholder="e.g. bihar" />

          <label className="login-label" htmlFor="p">Password</label>
          <input id="p" className="input" type="password" value={password}
            autoComplete="current-password"
            onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />

          {error && <div className="login-error">{error}</div>}

          <button className="btn btn-primary login-submit" type="submit"
            disabled={busy || !username || !password}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        {accounts && (
          <div className="login-demo">
            <div className="login-demo-head">Demo accounts for judges and testers</div>
            <div className="login-accounts">
              {accounts.accounts.map((a) => (
                <button key={a.username} className="login-account" onClick={() => useAccount(a.username)}>
                  <span className="la-name">{a.name}</span>
                  <span className="la-meta">
                    {a.username} · {a.role}{a.scope ? ` · ${a.scope}` : " · all of India"}
                  </span>
                </button>
              ))}
            </div>
            <p className="login-warn">{accounts.warning}</p>
          </div>
        )}

        <button className="login-skip" onClick={() => nav("/overview")}>
          Continue without signing in — you can look, but not change anything →
        </button>
      </div>
    </div>
  );
}
