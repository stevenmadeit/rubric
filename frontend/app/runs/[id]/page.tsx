"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorState, LoadingState, MetricCard, SectionHeading, Shell } from "@/components/Shell";
import { getRunResults, getRuns, type RunResult, type RunSummary } from "@/lib/api";

function percentage(value: number | null) {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function score(value: number | null) {
  return value === null ? "—" : value.toFixed(3);
}

export default function RunPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const [run, setRun] = useState<RunSummary | null>(null);
  const [results, setResults] = useState<RunResult[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getRuns(), getRunResults(runId)])
      .then(([runs, rows]) => {
        setRun(runs.find((item) => item.run_id === runId) ?? null);
        setResults(rows);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unknown API error"))
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) return <Shell active="runs"><LoadingState label="Loading run…" /></Shell>;
  if (error) return <Shell active="runs"><ErrorState message={error} /></Shell>;
  if (!run) return <Shell active="runs"><ErrorState message="This run was not found." /></Shell>;

  const buggyCount = results.filter((result) => result.actual_has_bug).length;
  const recallCount = results.filter((result) => result.actual_has_bug && result.predicted_has_bug).length;
  const cleanCount = results.length - buggyCount;
  const falsePositiveCount = results.filter((result) => !result.actual_has_bug && result.predicted_has_bug).length;
  const avg = (values: (number | null)[]) => {
    const scored = values.filter((value): value is number => value !== null);
    return scored.length ? scored.reduce((total, value) => total + value, 0) / scored.length : null;
  };

  return (
    <Shell active="runs">
      <SectionHeading
        eyebrow="EVALUATION RUN"
        title={`${run.model_name} · ${run.prompt_variant}`}
        description={`Run ${run.run_id} · Judge: ${run.judge_model}`}
        action={<Link className="button-secondary" href="/">← Dashboard</Link>}
      />
      <section className="metric-grid four">
        <MetricCard label="Accuracy" value={percentage(run.accuracy)} detail={`${results.filter((result) => result.correct).length} of ${results.length} cases`} accent="purple" />
        <MetricCard label="Bug recall" value={percentage(buggyCount ? recallCount / buggyCount : null)} detail={`${recallCount} of ${buggyCount} buggy cases`} accent="blue" />
        <MetricCard label="Clean false positive rate" value={percentage(cleanCount ? falsePositiveCount / cleanCount : null)} detail={`${falsePositiveCount} false positives`} accent="orange" />
        <MetricCard label="Avg judge · similarity" value={`${score(avg(results.map((result) => result.judge_score)))} · ${score(avg(results.map((result) => result.similarity_score)))}`} detail="Buggy cases with available scores" accent="green" />
      </section>
      <section className="card table-card run-results">
        <div className="card-heading">
          <div><h2>Test case results</h2><p>Inspect each prediction and its explanation scores</p></div>
          <span className="count-pill">{results.length} cases</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Case</th><th>Category</th><th>Actual</th><th>Prediction</th><th>Result</th><th>Judge</th><th>Similarity</th><th>Explanation</th></tr></thead>
            <tbody>
              {results.map((result) => (
                <tr key={result.test_case_id}>
                  <td><Link className="case-link" href={`/cases/${encodeURIComponent(result.test_case_id)}`}>{result.test_case_id}</Link></td>
                  <td><span className="category-tag">{result.category?.replaceAll("_", " ") ?? "—"}</span></td>
                  <td>{result.actual_has_bug ? "Bug" : "Clean"}</td>
                  <td>{result.predicted_has_bug ? "Bug" : "Clean"}</td>
                  <td><span className={`result-badge ${result.correct ? "correct" : "incorrect"}`}>{result.correct ? "Correct" : "Incorrect"}</span></td>
                  <td>{result.judge_score ?? "—"}</td>
                  <td>{score(result.similarity_score)}</td>
                  <td className="explanation-cell">{result.model_explanation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </Shell>
  );
}
