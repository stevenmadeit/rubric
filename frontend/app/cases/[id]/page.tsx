"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorState, LoadingState, SectionHeading, Shell } from "@/components/Shell";
import { getCase, type CaseDetail } from "@/lib/api";

function score(value: number | null) {
  return value === null ? "—" : value.toFixed(3);
}

export default function CasePage() {
  const params = useParams<{ id: string }>();
  const caseId = params.id;
  const [testCase, setTestCase] = useState<CaseDetail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getCase(caseId)
      .then(setTestCase)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unknown API error"))
      .finally(() => setLoading(false));
  }, [caseId]);

  if (loading) return <Shell><LoadingState label="Loading test case…" /></Shell>;
  if (error) return <Shell><ErrorState message={error} /></Shell>;
  if (!testCase) return <Shell><ErrorState message="This test case was not found." /></Shell>;

  return (
    <Shell>
      <SectionHeading
        eyebrow={`TEST CASE · ${testCase.category.replaceAll("_", " ").toUpperCase()}`}
        title={testCase.id}
        description={`${testCase.language} · Ground truth: ${testCase.has_bug ? "bug present" : "clean code"}`}
        action={<Link className="button-secondary" href="/">← Dashboard</Link>}
      />
      <section className="case-source-grid">
        <article className="card source-card">
          <div className="card-heading"><div><h2>Source code</h2><p>Ground-truth test snippet</p></div><span className="language-pill">{testCase.language}</span></div>
          <pre className="code-block"><code>{testCase.code}</code></pre>
          {testCase.has_bug ? (
            <div className="ground-truth"><span className="ground-truth-icon">!</span><div><strong>Ground-truth bug</strong><p>{testCase.bug_description}</p></div></div>
          ) : (
            <div className="ground-truth clean-truth"><span className="ground-truth-icon">✓</span><div><strong>Ground truth</strong><p>This snippet is labeled as clean.</p></div></div>
          )}
        </article>
        <article className="card case-meta-card">
          <div className="card-heading"><div><h2>Case profile</h2><p>Dataset metadata</p></div></div>
          <div className="profile-row"><span>Language</span><strong>{testCase.language}</strong></div>
          <div className="profile-row"><span>Category</span><strong>{testCase.category.replaceAll("_", " ")}</strong></div>
          <div className="profile-row"><span>Expected label</span><strong>{testCase.has_bug ? "Bug present" : "Clean"}</strong></div>
          <div className="profile-row"><span>Evaluations</span><strong>{testCase.runs.length} runs</strong></div>
        </article>
      </section>
      <section className="card table-card case-comparison">
        <div className="card-heading">
          <div><h2>Run-by-run comparison</h2><p>Predictions, explanations, and explanation quality scores</p></div>
          <span className="count-pill">{testCase.runs.length} evaluations</span>
        </div>
        <div className="comparison-grid">
          {testCase.runs.map((run) => (
            <article className="comparison-card" key={run.run_id}>
              <div className="comparison-top">
                <div><strong>{run.model_name}</strong><span>{run.prompt_variant}</span></div>
                <span className={`result-badge ${run.correct ? "correct" : "incorrect"}`}>{run.correct ? "Correct" : "Incorrect"}</span>
              </div>
              <div className="prediction-line"><span>Prediction</span><strong className={run.predicted_has_bug ? "text-orange" : "text-green"}>{run.predicted_has_bug ? "Bug detected" : "No bug detected"}</strong></div>
              <p className="run-explanation">{run.model_explanation}</p>
              <div className="score-pair">
                <div><span>Judge score</span><strong>{run.judge_score === null ? "—" : `${run.judge_score} / 5`}</strong></div>
                <div><span>Similarity</span><strong>{score(run.similarity_score)}</strong></div>
              </div>
              {run.judge_reasoning && <details className="judge-reasoning"><summary>Judge reasoning</summary><p>{run.judge_reasoning}</p></details>}
              <Link className="subtle-link" href={`/runs/${encodeURIComponent(run.run_id)}`}>View full run →</Link>
            </article>
          ))}
        </div>
      </section>
    </Shell>
  );
}
