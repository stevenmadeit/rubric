"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AccuracyChart, CategoryChart } from "@/components/Charts";
import { ErrorState, LoadingState, MetricCard, SectionHeading, Shell } from "@/components/Shell";
import { getCategories, getRuns, type CategoryMetric, type RunSummary } from "@/lib/api";

type MetricKey =
  | "accuracy"
  | "bug_recall"
  | "false_positive_rate"
  | "average_judge_score"
  | "average_similarity_score";

const columns: { key: MetricKey; label: string; kind: "percent" | "score"; best: "high" | "low" }[] = [
  { key: "accuracy", label: "Accuracy", kind: "percent", best: "high" },
  { key: "bug_recall", label: "Bug recall", kind: "percent", best: "high" },
  { key: "false_positive_rate", label: "False positive", kind: "percent", best: "low" },
  { key: "average_judge_score", label: "Avg judge", kind: "score", best: "high" },
  { key: "average_similarity_score", label: "Avg similarity", kind: "score", best: "high" },
];

function formatValue(value: number | null, kind: "percent" | "score") {
  if (value === null) return "—";
  return kind === "percent" ? `${(value * 100).toFixed(1)}%` : value.toFixed(3);
}

function bestValues(runs: RunSummary[]) {
  const result: Partial<Record<MetricKey, number>> = {};
  for (const column of columns) {
    const values = runs
      .map((run) => run[column.key])
      .filter((value): value is number => value !== null);
    if (values.length) {
      result[column.key] = column.best === "high" ? Math.max(...values) : Math.min(...values);
    }
  }
  return result;
}

export default function Home() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [categories, setCategories] = useState<CategoryMetric[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getRuns(), getCategories()])
      .then(([runData, categoryData]) => {
        setRuns(runData);
        setCategories(categoryData);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unknown API error"))
      .finally(() => setLoading(false));
  }, []);

  const sortedRuns = useMemo(
    () => [...runs].sort((a, b) => (b.accuracy ?? -1) - (a.accuracy ?? -1)),
    [runs],
  );
  const best = useMemo(() => bestValues(runs), [runs]);
  const latestRun = runs.reduce<RunSummary | null>(
    (current, run) => (!current || Date.parse(run.started_at) > Date.parse(current.started_at) ? run : current),
    null,
  );
  const uniqueModels = Array.from(new Set(runs.map((run) => run.model_name))).length;
  const metricRuns = runs.filter((run) => run.average_judge_score !== null);
  const averageJudge = metricRuns.length
    ? metricRuns.reduce((total, run) => total + (run.average_judge_score ?? 0), 0) / metricRuns.length
    : null;
  const datasetSize = Math.max(0, ...runs.map((run) => run.number_of_cases));

  if (loading) return <Shell><LoadingState /></Shell>;
  if (error) return <Shell><ErrorState message={error} /></Shell>;

  return (
    <Shell>
      <SectionHeading
        eyebrow="EVALUATION OVERVIEW"
        title="Model performance"
        description="Compare bug detection quality across models, prompts, and categories."
        action={<span className="updated-pill"><i /> Database connected</span>}
      />
      <section className="metric-grid">
        <MetricCard label="Evaluation runs" value={String(runs.length)} detail={`${uniqueModels} models · 3 prompt variants`} accent="purple" />
        <MetricCard label="Latest accuracy" value={latestRun ? formatValue(latestRun.accuracy, "percent") : "—"} detail={latestRun ? `${latestRun.model_name} · ${latestRun.prompt_variant}` : "No runs yet"} accent="blue" />
        <MetricCard label="Mean judge score" value={formatValue(averageJudge, "score")} detail="Across runs with judge scores" accent="green" />
        <MetricCard label="Test dataset" value={String(datasetSize)} detail="Python + JavaScript snippets" accent="orange" />
      </section>

      <section className="chart-grid">
        <article className="card chart-card">
          <div className="card-heading">
            <div><h2>Accuracy by model &amp; prompt</h2><p>Latest result for each model and prompt combination</p></div>
            <span className="chart-symbol purple-symbol">▥</span>
          </div>
          <div className="chart-area"><AccuracyChart runs={runs} /></div>
        </article>
        <article className="card chart-card">
          <div className="card-heading">
            <div><h2>Accuracy by bug category</h2><p>Model performance across the full dataset history</p></div>
            <span className="chart-symbol teal-symbol">◫</span>
          </div>
          <div className="chart-area"><CategoryChart categories={categories} /></div>
        </article>
      </section>

      <section className="card table-card">
        <div className="card-heading leaderboard-heading">
          <div><h2>Run leaderboard</h2><p>All evaluation runs ranked by overall accuracy</p></div>
          <span className="count-pill">{runs.length} runs</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Rank</th><th>Model</th><th>Prompt variant</th>{columns.map((column) => <th key={column.key}>{column.label}</th>)}<th>Cases</th></tr></thead>
            <tbody>
              {sortedRuns.map((run, index) => (
                <tr key={run.run_id}>
                  <td><span className={`rank-number ${index === 0 ? "rank-first" : ""}`}>{String(index + 1).padStart(2, "0")}</span></td>
                  <td><Link className="model-link" href={`/runs/${encodeURIComponent(run.run_id)}`}>{run.model_name}</Link><span className="table-subline">judge · {run.judge_model}</span></td>
                  <td><span className={`prompt-pill prompt-${run.prompt_variant}`}>{run.prompt_variant.replaceAll("_", " ")}</span></td>
                  {columns.map((column) => {
                    const value = run[column.key];
                    const isBest = value !== null && value === best[column.key];
                    return <td key={column.key}><span className={`metric-value ${isBest ? "best-value" : ""}`}>{formatValue(value, column.kind)}{isBest && <span className="best-star">✦</span>}</span></td>;
                  })}
                  <td className="cases-count">{run.number_of_cases}</td>
                </tr>
              ))}
              {runs.length === 0 && <tr><td colSpan={9} className="empty-cell">No evaluation runs found in the database.</td></tr>}
            </tbody>
          </table>
        </div>
        {datasetSize > 0 && <div className="dataset-note"><span className="info-mark">i</span><span><strong>{datasetSize} test cases</strong> in this dataset; one case changes accuracy by <strong>{(100 / datasetSize).toFixed(1)} percentage points</strong>.</span></div>}
      </section>
      <footer className="page-footer"><span>Rubric Evaluation Framework</span><span>Local-first · Transparent evaluation</span></footer>
    </Shell>
  );
}
