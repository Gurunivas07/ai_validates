import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  BarChart3,
  Code2,
  Home,
  LogOut,
  Play,
  RefreshCw,
  ShieldCheck,
  Trash2,
  Zap,
  Check
} from 'lucide-react';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api';

function getToken() {
  return localStorage.getItem('token');
}

async function api(path, options = {}) {
  const token = getToken();
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try {
      const data = await response.json();
      message = data.detail || data.error || message;
    } catch {}
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

function ms(value) {
  if (value == null) return '—';
  if (value < 1000) return `${value} ms`;
  return `${(value / 1000).toFixed(1)} sec`;
}

function money(value) {
  if (value == null) return '—';
  return `$${Number(value).toFixed(5)}`;
}

function StatusBadge({ status }) {
  return <span className={`badge ${status}`}>{status}</span>;
}

function JsonViewer({ data }) {
  if (!data) return <p className="muted">No output yet.</p>;
  return <pre className="json">{JSON.stringify(data, null, 2)}</pre>;
}

function AuthPage({ onLogin }) {
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const update = (field, value) => setForm((old) => ({ ...old, [field]: value }));

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const path = mode === 'login' ? '/auth/login' : '/auth/register';
      const body = mode === 'login'
        ? { email: form.email, password: form.password }
        : { name: form.name, email: form.email, password: form.password };
      const data = await api(path, { method: 'POST', body: JSON.stringify(body) });
      localStorage.setItem('token', data.access_token);
      onLogin(data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-screen">
      <section className="auth-card card">
        <div className="auth-copy">
          <p className="eyebrow">React JS + FastAPI</p>
          <h1>{mode === 'login' ? 'Login to continue' : 'Create your account'}</h1>
          <p className="muted">The compiler dashboard opens only after login. Your auth token is stored in localStorage.</p>
        </div>
        <form onSubmit={submit} className="auth-form">
          {mode === 'register' && (
            <label>
              Name
              <input value={form.name} onChange={(e) => update('name', e.target.value)} placeholder="Enter your name" required />
            </label>
          )}
          <label>
            Email
            <input type="email" value={form.email} onChange={(e) => update('email', e.target.value)} placeholder="Enter email" required />
          </label>
          <label>
            Password
            <input type="password" value={form.password} onChange={(e) => update('password', e.target.value)} placeholder="Enter password" minLength={6} required />
          </label>
          <button className="primary" disabled={loading}>{loading ? 'Please wait...' : mode === 'login' ? 'Login' : 'Register'}</button>
          {error && <p className="error">{error}</p>}
          <button type="button" className="switch-auth" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}>
            {mode === 'login' ? 'New user? Create account' : 'Already have an account? Login'}
          </button>
        </form>
      </section>
    </div>
  );
}

function Layout({ page, setPage, user, onLogout, children }) {
  const nav = [
    ['home', Home, 'Compiler'],
    ['runs', Activity, 'Runs'],
    ['eval', BarChart3, 'Evaluation'],
    ['pricing', Zap, 'Pricing'],
    ...(user?.role === 'admin' ? [['admin', ShieldCheck, 'Admin']] : []),
  ];
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><Code2 size={24} /><div><strong>AI App Compiler</strong><span>React JS + FastAPI</span></div></div>
        <nav>
          {nav.map(([id, Icon, label]) => (
            <button key={id} onClick={() => setPage(id)} className={page === id ? 'active' : ''}><Icon size={18} />{label}</button>
          ))}
        </nav>
        <div className="sidebar-user">
          <span>{user?.name || user?.email}</span>
          <small className={user?.role === 'admin' ? 'role admin-role' : 'role'}>{user?.role === 'admin' ? 'Admin account' : 'User account'}</small>
          <button onClick={onLogout}><LogOut size={16} /> Logout</button>
        </div>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}

function StatCard({ label, value, icon }) {
  return <div className="card stat"><span>{icon}</span><p>{label}</p><strong>{value}</strong></div>;
}

function HomePage({ openRun }) {
  const [requirements, setRequirements] = useState('Build a bus ticket booking app with login, route search, seat selection, wallet payment, cancellation, refunds, admin panel, and analytics dashboard.');
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const [s, r] = await Promise.all([api('/compiler/stats'), api('/compiler/recent')]);
      setStats(s); setRecent(r);
    } catch (err) { setError(err.message); }
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      const limit = await api('/billing/check-limit', { method: 'POST', body: '{}' });
      if (!limit.allowed) throw new Error('Daily free run limit reached.');
      const run = await api('/compiler/runs', { method: 'POST', body: JSON.stringify({ requirements }) });
      openRun(run.id);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="page">
      <section className="hero card">
        <div>
          <p className="eyebrow">Four stage compiler pipeline</p>
          <h1>Convert app ideas into structured schemas, APIs, UI plans, and validation reports.</h1>
          <p className="muted">This version keeps the React frontend and replaces the TypeScript Express backend with FastAPI.</p>
        </div>
        <form onSubmit={submit} className="compiler-form">
          <label>Project requirements</label>
          <textarea value={requirements} onChange={(e) => setRequirements(e.target.value)} rows={8} />
          <button className="primary" disabled={loading || requirements.length < 10}><Play size={18} />{loading ? 'Starting...' : 'Run Compiler'}</button>
          {error && <p className="error">{error}</p>}
        </form>
      </section>

      <section className="grid four">
        <StatCard label="Total Runs" value={stats?.totalRuns ?? 0} icon="🚀" />
        <StatCard label="Completed" value={stats?.completedRuns ?? 0} icon="✅" />
        <StatCard label="Success Rate" value={`${stats?.successRate ?? 0}%`} icon="📈" />
        <StatCard label="Token Usage" value={stats?.totalTokensUsed ?? 0} icon="🧠" />
      </section>

      <section className="card">
        <div className="section-head"><h2>Recent Runs</h2><button onClick={load}><RefreshCw size={16} />Refresh</button></div>
        <RunTable runs={recent} openRun={openRun} empty="No recent runs yet." />
      </section>
    </div>
  );
}

function RunTable({ runs, openRun, onDelete, empty }) {
  if (!runs.length) return <p className="muted">{empty}</p>;
  return (
    <div className="table-wrap"><table><thead><tr><th>Status</th><th>Requirements</th><th>Tokens</th><th>Cost</th><th>Duration</th><th></th></tr></thead><tbody>
      {runs.map((run) => <tr key={run.id}>
        <td><StatusBadge status={run.status} /></td>
        <td><button className="link" onClick={() => openRun(run.id)}>{run.requirements.slice(0, 95)}{run.requirements.length > 95 ? '...' : ''}</button></td>
        <td>{run.totalTokens ?? '—'}</td><td>{money(run.totalCostUsd)}</td><td>{ms(run.durationMs)}</td>
        <td>{onDelete && <button className="icon danger" onClick={() => onDelete(run.id)}><Trash2 size={16}/></button>}</td>
      </tr>)}
    </tbody></table></div>
  );
}

function RunsPage({ openRun }) {
  const [runs, setRuns] = useState([]); const [error, setError] = useState('');
  const load = async () => { try { setRuns(await api('/compiler/runs')); } catch (err) { setError(err.message); } };
  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t); }, []);
  const del = async (id) => { await api(`/compiler/runs/${id}`, { method: 'DELETE' }); load(); };
  return <section className="card"><div className="section-head"><h1>Compiler Runs</h1><button onClick={load}><RefreshCw size={16}/>Refresh</button></div>{error && <p className="error">{error}</p>}<RunTable runs={runs} openRun={openRun} onDelete={del} empty="No runs found." /></section>;
}

function RunDetail({ id, back }) {
  const [run, setRun] = useState(null); const [selected, setSelected] = useState(0); const [error, setError] = useState('');
  const load = async () => { try { setRun(await api(`/compiler/runs/${id}`)); } catch (err) { setError(err.message); } };
  useEffect(() => { load(); const t = setInterval(load, 1500); return () => clearInterval(t); }, [id]);
  const retry = async () => { await api(`/compiler/runs/${id}/retry`, { method: 'POST', body: '{}' }); load(); };
  if (error) return <div className="card"><button onClick={back}>← Back</button><p className="error">{error}</p></div>;
  if (!run) return <div className="card">Loading...</div>;
  const stage = run.stages[selected] || run.stages[0];
  return (
    <div className="page">
      <section className="card detail-head">
        <button onClick={back}>← Back</button>
        <div><h1>Run Detail</h1><p className="muted">{run.requirements}</p></div>
        <StatusBadge status={run.status} />
        <button onClick={retry}><RefreshCw size={16}/>Retry</button>
      </section>
      <section className="grid four">
        <StatCard label="Current Stage" value={run.currentStage ?? 'Done'} icon="⚙️" />
        <StatCard label="Total Tokens" value={run.totalTokens ?? '—'} icon="🧠" />
        <StatCard label="Cost" value={money(run.totalCostUsd)} icon="💵" />
        <StatCard label="Duration" value={ms(run.durationMs)} icon="⏱️" />
      </section>
      <section className="grid two">
        <div className="card">
          <h2>Stages</h2>
          <div className="stages">{run.stages.map((s, index) => <button key={s.id} className={selected === index ? 'stage active-stage' : 'stage'} onClick={() => setSelected(index)}><span>{s.stageNumber}</span><div><strong>{s.stageName}</strong><StatusBadge status={s.status}/></div></button>)}</div>
        </div>
        <div className="card"><h2>{stage?.stageName}</h2><p className="muted">Tokens: {stage?.totalTokens ?? '—'} | Cost: {money(stage?.estimatedCostUsd)} | Duration: {ms(stage?.durationMs)}</p>{stage?.error && <p className="error">{stage.error}</p>}<JsonViewer data={stage?.output}/></div>
      </section>
    </div>
  );
}

function EvalPage({ openRun }) {
  const [prompts, setPrompts] = useState([]); const [metrics, setMetrics] = useState(null); const [error, setError] = useState('');
  const load = async () => { try { const [p, m] = await Promise.all([api('/compiler/eval/prompts'), api('/compiler/eval/metrics')]); setPrompts(p); setMetrics(m); } catch (err) { setError(err.message); } };
  useEffect(() => { load(); }, []);
  const runPrompt = async (id) => { const run = await api(`/compiler/eval/run/${id}`, { method: 'POST', body: '{}' }); openRun(run.id); };
  return <div className="page"><section className="grid four"><StatCard label="Eval Runs" value={metrics?.totalEvalRuns ?? 0} icon="🧪"/><StatCard label="Completed" value={metrics?.completedEvalRuns ?? 0} icon="✅"/><StatCard label="Success" value={`${metrics?.successRate ?? 0}%`} icon="📈"/><StatCard label="Avg Tokens" value={metrics?.avgTokensPerRun ?? '—'} icon="🧠"/></section><section className="card"><div className="section-head"><h1>Evaluation Prompts</h1><button onClick={load}><RefreshCw size={16}/>Refresh</button></div>{error && <p className="error">{error}</p>}<div className="prompt-grid">{prompts.map(p => <div className="prompt-card" key={p.id}><div><StatusBadge status={p.category}/><h3>{p.label}</h3><p>{p.prompt}</p><small>{p.notes}</small></div><button className="primary" onClick={() => runPrompt(p.id)}>Run</button></div>)}</div></section></div>;
}

function PricingPage() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const FREE_LIMIT = 5;

  useEffect(() => {
    api('/billing/status')
      .then(setStatus)
      .catch(() => {});
  }, []);

  const isPremium = status?.plan === 'premium';

  const freeRunsLeft = status?.remainingFreeRuns ?? FREE_LIMIT;
  const runsToday = status?.runsToday ?? 0;
  const isStripeConfigured = status?.isStripeConfigured ?? false;

  const handleUpgrade = async () => {
    setError('');
    setLoading(true);

    try {
      const data = await api('/billing/create-checkout', {
        method: 'POST',
        body: '{}',
      });

      if (data?.url) {
        window.location.href = data.url;
      } else {
        setError('Checkout URL not received from backend.');
      }
    } catch (err) {
      setError(err.message || 'Unable to start payment.');
    } finally {
      setLoading(false);
    }
  };

  const FREE_FEATURES = [
    `${FREE_LIMIT} pipeline runs per day`,
    'All 4 AI stages',
    'Supabase SQL output',
    'Evaluation framework access',
    'JSON schema download',
  ];

  const PREMIUM_FEATURES = [
    'Higher daily pipeline runs',
    'All 4 AI stages',
    'Supabase SQL + RLS + Auth triggers',
    'Priority AI processing',
    'Full evaluation framework',
    'Admin analytics dashboard',
    'ZIP export with migration files',
    'Email support',
  ];

  const comparisonRows = [
    ['4-stage AI pipeline', true, true],
    ['Supabase SQL output', true, true],
    ['Row Level Security policies', true, true],
    ['Auth trigger SQL', true, true],
    ['Payment schema', true, true],
    ['Self-healing validator', true, true],
    ['Evaluation framework', true, true],
    ['Daily run limit', `${FREE_LIMIT}/day`, 'Higher limit'],
    ['ZIP schema export', false, true],
    ['Batch eval runs', false, true],
    ['Priority processing', false, true],
    ['Admin analytics', false, true],
  ];

  return (
    <div className="page pricing-page">
      <section className="pricing-title card">
        <div>
          <p className="eyebrow">Pricing plans</p>
          <h1>
            <Zap size={28} />
            Choose your compiler plan
          </h1>
          <p className="muted">
            Free users get limited daily compiler runs. Premium users get higher usage,
            priority processing, and advanced compiler features.
          </p>
        </div>

        <div className="current-plan">
          <span>Current plan</span>
          <strong className={isPremium ? 'premium-text' : 'free-text'}>
            {isPremium ? 'PREMIUM' : 'FREE'}
          </strong>

          {!isPremium ? (
            <small>{freeRunsLeft}/{FREE_LIMIT} runs left today</small>
          ) : (
            <small>{runsToday} runs used today</small>
          )}
        </div>
      </section>

      <section className="grid two">
        {/* Free Plan */}
        <div className="card pricing-card">
          <div className="plan-head">
            <div>
              <p className="eyebrow">Free</p>
              <h2>FREE</h2>
            </div>

            {!isPremium && <span className="plan-badge free-badge">CURRENT</span>}
          </div>

          <div className="plan-price">
            <strong>$0</strong>
            <span>/month</span>
          </div>

          <p className="muted">{FREE_LIMIT} pipeline runs per day</p>

          <ul className="plan-list">
            {FREE_FEATURES.map((feature) => (
              <li key={feature}>
                <Check size={16} />
                {feature}
              </li>
            ))}
          </ul>

          <button className="outline-full" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            START_BUILDING →
          </button>
        </div>

        {/* Premium Plan */}
        <div className="card pricing-card premium-card">
          <div className="plan-head">
            <div>
              <p className="eyebrow premium-text">Recommended</p>
              <h2 className="premium-text">PREMIUM</h2>
            </div>

            <span className="plan-badge premium-badge">BEST VALUE</span>
          </div>

          <div className="plan-price">
            <strong>$29</strong>
            <span>/month</span>
          </div>

          <p className="muted">
            Higher daily usage and priority AI processing
          </p>

          <ul className="plan-list premium-list">
            {PREMIUM_FEATURES.map((feature) => (
              <li key={feature}>
                <Zap size={16} />
                {feature}
              </li>
            ))}
          </ul>

          {error && <p className="error">{error}</p>}

          {!isStripeConfigured && (
            <div className="stripe-warning">
              Stripe is not configured. Add STRIPE_SECRET_KEY and
              STRIPE_PREMIUM_PRICE_ID in backend .env file.
            </div>
          )}

          {isPremium ? (
            <button className="premium-active" disabled>
              PREMIUM_ACTIVE
            </button>
          ) : (
            <button
              className="premium-upgrade"
              onClick={handleUpgrade}
              disabled={loading || !isStripeConfigured}
            >
              {loading ? 'REDIRECTING...' : 'UPGRADE_TO_PREMIUM →'}
            </button>
          )}
        </div>
      </section>

      <section className="card">
        <div className="section-head">
          <h2>Capability Matrix</h2>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Feature</th>
                <th>Free</th>
                <th>Premium</th>
              </tr>
            </thead>

            <tbody>
              {comparisonRows.map((row, index) => (
                <tr key={index}>
                  <td>{row[0]}</td>

                  <td>
                    {row[1] === true ? (
                      <Check size={16} className="check-icon" />
                    ) : row[1] === false ? (
                      '—'
                    ) : (
                      row[1]
                    )}
                  </td>

                  <td>
                    {row[2] === true ? (
                      <Zap size={16} className="zap-icon" />
                    ) : row[2] === false ? (
                      '—'
                    ) : (
                      row[2]
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="pricing-footer-text">
        <span>
          <ShieldCheck size={15} />
          Secured by Stripe
        </span>
        <span>·</span>
        <span>Cancel anytime</span>
        <span>·</span>
        <span>No setup fees</span>
      </section>
    </div>
  );
}


function AdminPage({ user }) {
  const [summary, setSummary] = useState(null);
  const [users, setUsers] = useState([]);
  const [error, setError] = useState('');

  const load = async () => {
    setError('');
    try {
      const [s, u] = await Promise.all([api('/admin/summary'), api('/admin/users')]);
      setSummary(s);
      setUsers(u);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => { load(); }, []);

  if (user?.role !== 'admin') {
    return <section className="card"><h1>Admin access required</h1><p className="error">Only admin login can open this page.</p></section>;
  }

  return (
    <div className="page">
      <section className="card hero admin-hero">
        <div>
          <p className="eyebrow">Admin panel</p>
          <h1>Admin dashboard</h1>
          <p className="muted">This page is visible only for users whose role is <b>admin</b>. Normal users cannot see the Admin menu.</p>
        </div>
        <div className="price"><strong>{summary?.totalUsers ?? 0}</strong><span>registered users</span></div>
      </section>

      {error && <p className="error">{error}</p>}

      <section className="grid four">
        <StatCard label="Total Users" value={summary?.totalUsers ?? 0} icon="👥" />
        <StatCard label="Admins" value={summary?.adminUsers ?? 0} icon="🛡️" />
        <StatCard label="Normal Users" value={summary?.normalUsers ?? 0} icon="🙋" />
        <StatCard label="Total Runs" value={summary?.totalRuns ?? 0} icon="🚀" />
      </section>

      <section className="card">
        <div className="section-head"><h2>Users</h2><button onClick={load}><RefreshCw size={16}/>Refresh</button></div>
        {!users.length ? <p className="muted">No users found.</p> : (
          <div className="table-wrap"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Plan</th><th>Created</th></tr></thead><tbody>
            {users.map((u) => <tr key={u.id}><td>{u.name}</td><td>{u.email}</td><td><StatusBadge status={u.role === 'admin' ? 'completed' : 'pending'} /> {u.role}</td><td>{u.plan}</td><td>{u.createdAt ? new Date(u.createdAt).toLocaleString() : '—'}</td></tr>)}
          </tbody></table></div>
        )}
      </section>
    </div>
  );
}

function App() {
  const [page, setPage] = useState('home');
  const [runId, setRunId] = useState(null);
  const [user, setUser] = useState(null);
  const [checkingAuth, setCheckingAuth] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setCheckingAuth(false);
      return;
    }
    api('/auth/me')
      .then(setUser)
      .catch(() => localStorage.removeItem('token'))
      .finally(() => setCheckingAuth(false));
  }, []);

  const openRun = (id) => { setRunId(id); setPage('detail'); };
  const logout = async () => {
    try { await api('/auth/logout', { method: 'POST', body: '{}' }); } catch {}
    localStorage.removeItem('token');
    setUser(null);
    setRunId(null);
    setPage('home');
  };

  const current = useMemo(() => {
    if (page === 'admin') {
      return user?.role === 'admin' ? <AdminPage user={user} /> : <HomePage openRun={openRun} />;
    }
    if (page === 'detail') return <RunDetail id={runId} back={() => setPage('runs')} />;
    if (page === 'runs') return <RunsPage openRun={openRun} />;
    if (page === 'eval') return <EvalPage openRun={openRun} />;
    if (page === 'pricing') return <PricingPage />;
    return <HomePage openRun={openRun} />;
  }, [page, runId, user]);

  if (checkingAuth) return <div className="auth-screen"><div className="card">Checking login...</div></div>;
  if (!user) return <AuthPage onLogin={setUser} />;

  return <Layout page={page} setPage={setPage} user={user} onLogout={logout}>{current}</Layout>;
}

createRoot(document.getElementById('root')).render(<App />);
