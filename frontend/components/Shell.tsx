import Link from "next/link";

export function Shell({
  children,
  active = "overview",
}: {
  children: React.ReactNode;
  active?: "overview" | "runs";
}) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href="/">
          <span className="brand-mark">R</span>
          <span>
            <strong>Rubric</strong>
            <small>Evaluation lab</small>
          </span>
        </Link>
        <div className="side-label">WORKSPACE</div>
        <nav className="side-nav">
          <Link className={active === "overview" ? "active" : ""} href="/">
            <span className="nav-glyph">▦</span> Overview
          </Link>
          <Link className={active === "runs" ? "active" : ""} href="/">
            <span className="nav-glyph">◷</span> Evaluation runs
          </Link>
        </nav>
        <div className="sidebar-bottom">
          <span className="status-dot" />
          <span>Local evaluation data</span>
        </div>
      </aside>
      <main className="main-panel">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>Rubric</span>
            <span className="crumb-separator">/</span>
            <span className="crumb-current">{active === "runs" ? "Run detail" : "Overview"}</span>
          </div>
          <div className="topbar-right">
            <span className="live-indicator"><i /> LOCAL DATABASE</span>
            <div className="avatar">RL</div>
          </div>
        </header>
        <div className="page-content">{children}</div>
      </main>
    </div>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="section-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}

export function MetricCard({
  label,
  value,
  detail,
  accent,
}: {
  label: string;
  value: string;
  detail: string;
  accent: string;
}) {
  return (
    <article className="metric-card">
      <div className="metric-top">
        <span>{label}</span>
        <span className={`metric-icon ${accent}`}>{accent === "purple" ? "◈" : accent === "blue" ? "↗" : accent === "green" ? "✓" : "⌁"}</span>
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

export function LoadingState({ label = "Loading evaluation data…" }: { label?: string }) {
  return <div className="state-card"><span className="spinner" />{label}</div>;
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="error-card">
      <strong>Couldn’t load dashboard data</strong>
      <p>{message}</p>
      <span>Check that the FastAPI server is running at the configured API URL.</span>
    </div>
  );
}
