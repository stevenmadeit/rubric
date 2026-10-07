import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import Boolean, Column, DateTime, MetaData, String, Table, Text, create_engine


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "data" / "test_cases.json"
DEFAULT_DATABASE = ROOT / "rubric.db"
DEFAULT_OLLAMA_URL = "http://localhost:11434"

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


def parse_response(response_text: str) -> tuple[bool, str]:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*?\}", response_text, re.DOTALL)
        if not match:
            raise ValueError(f"Model response did not contain a JSON object: {response_text!r}")
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError as error:
            raise ValueError(f"Model response contained invalid JSON: {response_text!r}") from error

    if not isinstance(payload, dict) or "has_bug" not in payload:
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
            response = requests.post(
                f"{ollama_url.rstrip('/')}/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"num_predict": 256, "temperature": 0},
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
                f"Ollama request failed for case {case['id']}: "
                f"HTTP {response.status_code}: {response.text}",
                response=response,
            ) from error
        break
    body = response.json()
    if not isinstance(body, dict) or not isinstance(body.get("response"), str):
        raise ValueError(f"Ollama returned an unexpected response for {case['id']}: {body!r}")
    return parse_response(body["response"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate an Ollama model on the bug dataset.")
    parser.add_argument("--model", default="llama3", help="Ollama model name (default: llama3)")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    cases = load_cases(args.dataset)
    engine = create_engine(f"sqlite:///{args.database}", future=True)
    metadata.create_all(engine)
    timestamp = datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []

    for case in cases:
        predicted, explanation = evaluate_case(
            case, args.model, args.ollama_url, args.timeout
        )
        actual = case["has_bug"]
        correct = predicted == actual
        results.append(
            {
                "test_case_id": case["id"],
                "model_name": args.model,
                "predicted_has_bug": predicted,
                "actual_has_bug": actual,
                "model_explanation": explanation,
                "correct": correct,
                "run_timestamp": timestamp,
            }
        )
        print(f"{case['id']}: predicted={predicted}, actual={actual}, correct={correct}")

    with engine.begin() as connection:
        connection.execute(eval_results.insert(), results)

    correct_count = sum(result["correct"] for result in results)
    print(f"\nModel: {args.model}")
    print(f"Results saved to: {args.database}")
    print(f"Accuracy: {correct_count}/{len(results)} ({correct_count / len(results):.1%})")
    print("Accuracy by category:")
    for category in sorted({case["category"] for case in cases}):
        category_results = [
            result["correct"]
            for case, result in zip(cases, results)
            if case["category"] == category
        ]
        category_correct = sum(category_results)
        print(
            f"  {category}: {category_correct}/{len(category_results)} "
            f"({category_correct / len(category_results):.1%})"
        )
    engine.dispose()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, requests.RequestException, ValueError) as error:
        print(f"Evaluation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
