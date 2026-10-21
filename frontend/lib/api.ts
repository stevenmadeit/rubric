export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type RunSummary = {
  run_id: string;
  model_name: string;
  prompt_variant: string;
  judge_model: string;
  started_at: string;
  accuracy: number | null;
  bug_recall: number | null;
  false_positive_rate: number | null;
  average_judge_score: number | null;
  average_similarity_score: number | null;
  number_of_cases: number;
};

export type CategoryMetric = {
  model_name: string;
  category: string;
  number_of_cases: number;
  accuracy: number;
  average_judge_score: number | null;
};

export type RunResult = {
  test_case_id: string;
  model_name: string;
  predicted_has_bug: boolean;
  actual_has_bug: boolean;
  model_explanation: string;
  correct: boolean;
  judge_score: number | null;
  judge_reasoning: string | null;
  similarity_score: number | null;
  category: string | null;
  language: string | null;
  bug_description: string | null;
};

export type CaseRun = {
  run_id: string;
  model_name: string;
  prompt_variant: string;
  judge_model: string;
  started_at: string;
  predicted_has_bug: boolean;
  model_explanation: string;
  correct: boolean;
  judge_score: number | null;
  judge_reasoning: string | null;
  similarity_score: number | null;
};

export type CaseDetail = {
  id: string;
  code: string;
  language: string;
  category: string;
  has_bug: boolean;
  bug_description?: string;
  runs: CaseRun[];
};

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`API request failed (${response.status}): ${path}`);
  }
  return response.json() as Promise<T>;
}

export const getRuns = () => fetchJson<RunSummary[]>("/runs");
export const getCategories = () => fetchJson<CategoryMetric[]>("/categories");
export const getRunResults = (runId: string) =>
  fetchJson<RunResult[]>(`/runs/${encodeURIComponent(runId)}/results`);
export const getCase = (caseId: string) =>
  fetchJson<CaseDetail>(`/cases/${encodeURIComponent(caseId)}`);
