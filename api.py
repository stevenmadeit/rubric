import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import URL, create_engine, text


ROOT = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.environ.get("RUBRIC_DB_PATH", ROOT / "rubric.db")).resolve()
DATASET_PATH = ROOT / "data" / "test_cases.json"

if not DATABASE_PATH.is_file():
    raise RuntimeError(f"Rubric database does not exist: {DATABASE_PATH}")
if not DATASET_PATH.is_file():
    raise RuntimeError(f"Rubric test dataset does not exist: {DATASET_PATH}")

database_url = URL.create(
    "sqlite+pysqlite",
    database=f"file:{DATABASE_PATH.as_posix()}",
    query={"mode": "ro", "uri": "true"},
)
engine = create_engine(database_url, connect_args={"check_same_thread": False})

with DATASET_PATH.open(encoding="utf-8") as dataset_file:
    DATASET: dict[str, dict[str, Any]] = {
        case["id"]: case for case in json.load(dataset_file)
    }

app = FastAPI(title="Rubric Evaluation API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_connection():
    return engine.connect()


def calculate_metrics(row: Any) -> dict[str, Any]:
    case_count = int(row["case_count"] or 0)
    buggy_cases = int(row["buggy_cases"] or 0)
    clean_cases = int(row["clean_cases"] or 0)
    return {
        "accuracy": row["correct_cases"] / case_count if case_count else None,
        "bug_recall": row["true_positives"] / buggy_cases if buggy_cases else None,
        "false_positive_rate": (
            row["false_positives"] / clean_cases if clean_cases else None
        ),
        "average_judge_score": row["average_judge_score"],
        "average_similarity_score": row["average_similarity_score"],
        "number_of_cases": case_count,
    }


RUN_METRICS_SQL = """
    SELECT
        r.run_id,
        r.model_name,
        r.prompt_variant,
        r.judge_model,
        r.started_at,
        COUNT(e.test_case_id) AS case_count,
        COALESCE(SUM(CASE WHEN e.correct THEN 1 ELSE 0 END), 0) AS correct_cases,
        COALESCE(SUM(CASE WHEN e.actual_has_bug THEN 1 ELSE 0 END), 0) AS buggy_cases,
        COALESCE(SUM(CASE WHEN e.actual_has_bug AND e.predicted_has_bug
                          THEN 1 ELSE 0 END), 0) AS true_positives,
        COALESCE(SUM(CASE WHEN NOT e.actual_has_bug THEN 1 ELSE 0 END), 0) AS clean_cases,
        COALESCE(SUM(CASE WHEN NOT e.actual_has_bug AND e.predicted_has_bug
                          THEN 1 ELSE 0 END), 0) AS false_positives,
        AVG(e.judge_score) AS average_judge_score,
        AVG(e.similarity_score) AS average_similarity_score
    FROM runs AS r
    LEFT JOIN eval_results AS e ON e.run_id = r.run_id
"""


@app.get("/runs")
def list_runs() -> list[dict[str, Any]]:
    query = text(
        f"{RUN_METRICS_SQL} GROUP BY r.run_id ORDER BY r.started_at DESC"
    )
    with get_connection() as connection:
        rows = connection.execute(query).mappings().all()
    response = []
    for row in rows:
        item = {
            "run_id": row["run_id"],
            "model_name": row["model_name"],
            "prompt_variant": row["prompt_variant"],
            "judge_model": row["judge_model"],
            "started_at": row["started_at"],
        }
        item.update(calculate_metrics(row))
        response.append(item)
    return response


@app.get("/runs/{run_id}/results")
def list_run_results(run_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        run_exists = connection.execute(
            text("SELECT 1 FROM runs WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).first()
        if run_exists is None:
            raise HTTPException(status_code=404, detail="Run not found")
        rows = connection.execute(
            text(
                """
                SELECT
                    e.test_case_id,
                    e.model_name,
                    e.predicted_has_bug,
                    e.actual_has_bug,
                    e.model_explanation,
                    e.correct,
                    e.judge_score,
                    e.judge_reasoning,
                    e.similarity_score,
                    e.run_timestamp
                FROM eval_results AS e
                WHERE e.run_id = :run_id
                ORDER BY e.test_case_id
                """
            ),
            {"run_id": run_id},
        ).mappings().all()
    return [
        {
            **dict(row),
            "category": DATASET.get(row["test_case_id"], {}).get("category"),
            "language": DATASET.get(row["test_case_id"], {}).get("language"),
            "bug_description": DATASET.get(row["test_case_id"], {}).get(
                "bug_description"
            ),
        }
        for row in rows
    ]


@app.get("/cases/{case_id}")
def get_case(case_id: str) -> dict[str, Any]:
    case = DATASET.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Test case not found")

    with get_connection() as connection:
        rows = connection.execute(
            text(
                """
                SELECT
                    r.run_id,
                    r.model_name,
                    r.prompt_variant,
                    r.judge_model,
                    r.started_at,
                    e.predicted_has_bug,
                    e.model_explanation,
                    e.correct,
                    e.judge_score,
                    e.judge_reasoning,
                    e.similarity_score
                FROM eval_results AS e
                JOIN runs AS r ON r.run_id = e.run_id
                WHERE e.test_case_id = :case_id
                ORDER BY r.started_at DESC
                """
            ),
            {"case_id": case_id},
        ).mappings().all()
    return {
        "id": case["id"],
        "code": case["code"],
        "language": case["language"],
        "category": case["category"],
        "has_bug": case["has_bug"],
        "bug_description": case.get("bug_description"),
        "runs": [dict(row) for row in rows],
    }


@app.get("/categories")
def list_categories() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            text(
                """
                SELECT e.model_name, e.test_case_id, e.correct, e.judge_score
                FROM eval_results AS e
                JOIN runs AS r ON r.run_id = e.run_id
                """
            ),
        ).mappings().all()

    aggregates: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        case = DATASET.get(row["test_case_id"])
        if case is None:
            continue
        key = (row["model_name"], case["category"])
        aggregate = aggregates.setdefault(
            key,
            {
                "model_name": row["model_name"],
                "category": case["category"],
                "number_of_cases": 0,
                "correct_cases": 0,
                "judge_total": 0.0,
                "judge_count": 0,
            },
        )
        aggregate["number_of_cases"] += 1
        aggregate["correct_cases"] += int(bool(row["correct"]))
        if row["judge_score"] is not None:
            aggregate["judge_total"] += row["judge_score"]
            aggregate["judge_count"] += 1

    response = []
    for aggregate in aggregates.values():
        case_count = aggregate["number_of_cases"]
        response.append(
            {
                "model_name": aggregate["model_name"],
                "category": aggregate["category"],
                "number_of_cases": case_count,
                "accuracy": aggregate["correct_cases"] / case_count,
                "average_judge_score": (
                    aggregate["judge_total"] / aggregate["judge_count"]
                    if aggregate["judge_count"]
                    else None
                ),
            }
        )
    return sorted(response, key=lambda row: (row["category"], row["model_name"]))
