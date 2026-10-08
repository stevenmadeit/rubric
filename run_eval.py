import argparse
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any

import requests
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    inspect,
    text,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "data" / "test_cases.json"
DEFAULT_DATABASE = ROOT / "rubric.db"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
DISAGREEMENT_JUDGE_MAX = 2
DISAGREEMENT_SIMILARITY_MIN = 0.7

metadata = MetaData()
eval_results = Table(
    "eval_results",
    metadata,
    Column("test_case_id", String, primary_key=True),
    Column("model_name", String, primary_key=True),
    Column("predicted_has_bug", Boolean, nullable=False),
    Column("actual_has_bug", Boolean, nullable=False),
    Column("model_explanation", Text, nullable=False),
    Column("correct", Boolean, nullable=False),
    Column("judge_score", Integer),
    Column("judge_reasoning", Text),
    Column("similarity_score", Float),
    Column("run_timestamp", DateTime(timezone=True), primary_key=True),
)


def load_cases(dataset_path: Path) -> list[dict[str, Any]]:
    with dataset_path.open(encoding="utf-8") as dataset_file:
        cases = json.load(dataset_file)
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"Dataset must contain a non-empty JSON array: {dataset_path}")

    required = {"id", "language", "code", "has_bug", "category"}
    seen_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not required.issubset(case):
            raise ValueError(f"Each case must be an object containing {sorted(required)}")
        if case["id"] in seen_ids:
            raise ValueError(f"Duplicate test case id: {case['id']}")
        if not isinstance(case["has_bug"], bool):
            raise ValueError(f"has_bug must be a boolean for case {case['id']}")
        if case["has_bug"] and not case.get("bug_description"):
            raise ValueError(f"Bug description is required for buggy case {case['id']}")
        seen_ids.add(case["id"])
    return cases


def decode_json_object(response_text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", response_text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    decoder = json.JSONDecoder()
    for index, character in enumerate(cleaned):
        if character == "{":
            try:
                payload, _ = decoder.raw_decode(cleaned[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    raise ValueError(f"Model response did not contain a valid JSON object: {response_text!r}")


def parse_response(response_text: str) -> tuple[bool, str]:
    payload = decode_json_object(response_text)
    if "has_bug" not in payload:
        raise ValueError(f"Model response JSON must contain has_bug: {response_text!r}")
    prediction = payload["has_bug"]
    if isinstance(prediction, str):
        normalized = prediction.strip().lower()
        if normalized not in {"true", "false"}:
            raise ValueError(f"Model returned invalid has_bug value: {prediction!r}")
        prediction = normalized == "true"
    if not isinstance(prediction, bool):
        raise ValueError(f"Model returned invalid has_bug value: {prediction!r}")

    explanation = payload.get("explanation", "")
    if not isinstance(explanation, str):
        raise ValueError("Model explanation must be a string")
    return prediction, explanation.strip()


def post_generate(
    ollama_url: str,
    model_name: str,
    prompt: str,
    timeout: float,
    *,
    max_tokens: int = 256,
) -> str:
    for attempt in range(3):
        try:
            response = requests.post(
                f"{ollama_url.rstrip('/')}/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"num_predict": max_tokens, "temperature": 0},
                },
                timeout=timeout,
            )
        except requests.Timeout:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
            continue
        if response.status_code >= 500 and attempt < 2:
            time.sleep(2**attempt)
            continue
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            raise requests.HTTPError(
                f"Ollama request for model {model_name!r} failed: "
                f"HTTP {response.status_code}: {response.text}",
                response=response,
            ) from error
        break
    body = response.json()
    if not isinstance(body, dict) or not isinstance(body.get("response"), str):
        raise ValueError(f"Ollama returned an unexpected response: {body!r}")
    return body["response"]


def evaluate_case(
    case: dict[str, Any], model_name: str, ollama_url: str, timeout: float
) -> tuple[bool, str]:
    prompt = (
        "Review the following code for an actual bug. Decide based only on the code; "
        "do not invent missing requirements. Respond as a JSON object with exactly "
        'these fields: {"has_bug": true or false, "explanation": "brief explanation"}. '
        "If there is no clear bug, set has_bug to false.\n\n"
        f"Language: {case['language']}\nCode:\n```{case['language']}\n{case['code']}\n```"
    )
    for attempt in range(3):
        try:
            return parse_response(
                post_generate(ollama_url, model_name, prompt, timeout)
            )
        except requests.Timeout:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
        except ValueError:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
    raise RuntimeError(f"Unable to evaluate case {case['id']}")


def score_with_judge(
    explanation: str,
    bug_description: str,
    judge_model: str,
    ollama_url: str,
    timeout: float,
) -> tuple[int | None, str | None]:
    prompt = (
        "You are grading a code bug explanation against the known bug. Score only "
        "whether the explanation correctly identifies the actual bug: 1 means "
        "completely wrong or missed it; 5 means it correctly identifies the exact "
        "bug. Use intermediate scores for partial correctness. Do not reward unrelated "
        "issues. Return JSON with exactly these fields: "
        '{"score": 1, "reasoning": "brief reason"}.\n\n'
        f"Ground-truth bug: {bug_description}\n"
        f"Model explanation: {explanation}"
    )
    last_error: ValueError | None = None
    for attempt in range(2):
        response_text = post_generate(
            ollama_url, judge_model, prompt, timeout, max_tokens=160
        )
        try:
            payload = decode_json_object(response_text)
            score = payload.get("score")
            reasoning = payload.get("reasoning")
            if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
                raise ValueError(f"Judge score must be an integer from 1 to 5: {score!r}")
            if not isinstance(reasoning, str):
                raise ValueError("Judge reasoning must be a string")
            return score, reasoning.strip()
        except ValueError as error:
            last_error = error
            if attempt == 0:
                time.sleep(1)
    print(f"Warning: judge returned malformed output twice; storing null: {last_error}", file=sys.stderr)
    return None, None


def get_embeddings(
    texts: list[str],
    model_name: str,
    ollama_url: str,
    timeout: float,
) -> list[list[float]]:
    response = requests.post(
        f"{ollama_url.rstrip('/')}/api/embed",
        json={"model": model_name, "input": texts},
        timeout=timeout,
    )
    if response.status_code == 404:
        raise requests.HTTPError(
            "Ollama /api/embed is unavailable (HTTP 404). Update Ollama to a version "
            "that supports this route.",
            response=response,
        )
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        raise requests.HTTPError(
            f"Ollama embedding request failed: HTTP {response.status_code}: {response.text}",
            response=response,
        ) from error
    body = response.json()
    embeddings = body.get("embeddings") if isinstance(body, dict) else None
    if (
        not isinstance(embeddings, list)
        or len(embeddings) != len(texts)
        or any(not isinstance(vector, list) or not vector for vector in embeddings)
    ):
        raise ValueError(f"Ollama returned an unexpected embeddings response: {body!r}")
    vectors: list[list[float]] = []
    for vector in embeddings:
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in vector
        ):
            raise ValueError("Ollama embeddings must contain only finite numbers")
        vectors.append([float(value) for value in vector])
    return vectors


def cosine_similarity(first: list[float], second: list[float]) -> float:
    if len(first) != len(second):
        raise ValueError("Embedding vectors have different dimensions")
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))
    if first_norm == 0 or second_norm == 0:
        raise ValueError("Ollama returned a zero-length embedding vector")
    cosine = sum(a * b for a, b in zip(first, second)) / (first_norm * second_norm)
    return min(1.0, max(0.0, cosine))


def migrate_schema(engine: Any) -> None:
    metadata.create_all(engine)
    existing_columns = {
        column["name"] for column in inspect(engine).get_columns("eval_results")
    }
    additions = {
        "judge_score": "INTEGER",
        "judge_reasoning": "TEXT",
        "similarity_score": "FLOAT",
    }
    with engine.begin() as connection:
        for name, sql_type in additions.items():
            if name not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE eval_results ADD COLUMN {name} {sql_type}")
                )


def average(values: list[float | int | None]) -> float | None:
    available = [float(value) for value in values if value is not None]
    return fmean(available) if available else None


def format_average(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "N/A"


def print_summary(
    cases: list[dict[str, Any]],
    results: list[dict[str, Any]],
    model_name: str,
    judge_model: str,
) -> None:
    def show(label: str, paired: list[tuple[dict[str, Any], dict[str, Any]]]) -> None:
        accuracy = sum(result["correct"] for _, result in paired) / len(paired)
        judge_average = average([result["judge_score"] for _, result in paired])
        similarity_average = average([result["similarity_score"] for _, result in paired])
        scored_pairs = [
            result
            for _, result in paired
            if result["judge_score"] is not None and result["similarity_score"] is not None
        ]
        disagreements = sum(
            result["judge_score"] <= DISAGREEMENT_JUDGE_MAX
            and result["similarity_score"] > DISAGREEMENT_SIMILARITY_MIN
            for result in scored_pairs
        )
        disagreement_rate = (
            f"{disagreements}/{len(scored_pairs)} "
            f"({disagreements / len(scored_pairs):.1%})"
            if scored_pairs
            else "N/A"
        )
        print(
            f"{label}: accuracy {sum(result['correct'] for _, result in paired)}/"
            f"{len(paired)} ({accuracy:.1%}); "
            f"avg judge {format_average(judge_average)}; "
            f"avg similarity {format_average(similarity_average)}; "
            f"judge <= {DISAGREEMENT_JUDGE_MAX} & similarity > "
            f"{DISAGREEMENT_SIMILARITY_MIN:.1f}: {disagreement_rate}"
        )

    paired_results = list(zip(cases, results))
    print(f"\nModel: {model_name}")
    print(f"Judge model: {judge_model}")
    print(f"Accuracy: {sum(result['correct'] for result in results)}/{len(results)} "
          f"({sum(result['correct'] for result in results) / len(results):.1%})")
    print(f"Average judge score: {format_average(average([r['judge_score'] for r in results]))}")
    print(f"Average similarity score: "
          f"{format_average(average([r['similarity_score'] for r in results]))}")
    scored_pairs = [
        result for result in results
        if result["judge_score"] is not None and result["similarity_score"] is not None
    ]
    disagreements = sum(
        result["judge_score"] <= DISAGREEMENT_JUDGE_MAX
        and result["similarity_score"] > DISAGREEMENT_SIMILARITY_MIN
        for result in scored_pairs
    )
    print(
        f"Disagreement (judge <= {DISAGREEMENT_JUDGE_MAX} and similarity > "
        f"{DISAGREEMENT_SIMILARITY_MIN:.1f}): {disagreements}/{len(scored_pairs)} "
        f"({disagreements / len(scored_pairs):.1%})"
        if scored_pairs
        else "Disagreement: N/A (no cases had both explanation scores)"
    )
    print("Breakdown by category:")
    for category in sorted({case["category"] for case in cases}):
        show(
            f"  {category}",
            [(case, result) for case, result in paired_results if case["category"] == category],
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate an Ollama model on the bug dataset.")
    parser.add_argument("--model", default="llama3", help="Ollama model name (default: llama3)")
    parser.add_argument(
        "--judge-model",
        default=os.environ.get("JUDGE_MODEL", "llama3"),
        help="Ollama judge model (default: JUDGE_MODEL env var or llama3)",
    )
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help=f"Ollama embedding model (default: {DEFAULT_EMBEDDING_MODEL})",
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL))
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    cases = load_cases(args.dataset)
    engine = create_engine(f"sqlite:///{args.database}", future=True)
    migrate_schema(engine)
    timestamp = datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []

    for case in cases:
        predicted, explanation = evaluate_case(
            case, args.model, args.ollama_url, args.timeout
        )
        actual = case["has_bug"]
        result: dict[str, Any] = {
            "test_case_id": case["id"],
            "model_name": args.model,
            "predicted_has_bug": predicted,
            "actual_has_bug": actual,
            "model_explanation": explanation,
            "correct": predicted == actual,
            "judge_score": None,
            "judge_reasoning": None,
            "similarity_score": None,
            "run_timestamp": timestamp,
        }
        if actual:
            result["judge_score"], result["judge_reasoning"] = score_with_judge(
                explanation,
                case["bug_description"],
                args.judge_model,
                args.ollama_url,
                args.timeout,
            )
            vectors = get_embeddings(
                [explanation, case["bug_description"]],
                args.embedding_model,
                args.ollama_url,
                args.timeout,
            )
            result["similarity_score"] = cosine_similarity(vectors[0], vectors[1])
        results.append(result)
        print(
            f"{case['id']}: predicted={predicted}, actual={actual}, "
            f"correct={result['correct']}, judge={result['judge_score']}, "
            f"similarity={format_average(result['similarity_score'])}"
        )

    with engine.begin() as connection:
        connection.execute(eval_results.insert(), results)
    print(f"\nResults saved to: {args.database}")
    print_summary(cases, results, args.model, args.judge_model)
    engine.dispose()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, requests.RequestException, ValueError) as error:
        print(f"Evaluation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
