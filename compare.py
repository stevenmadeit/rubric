import argparse
import sqlite3
import textwrap
from pathlib import Path
from typing import Any


DEFAULT_DATABASE = Path(__file__).resolve().parent / "rubric.db"


def format_score(value: Any) -> str:
    return f"{value:.3f}" if value is not None else "N/A"


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [
        max(
            [len(header)]
            + [
                len(line)
                for row in rows
                for line in row[index].splitlines() or [""]
            ]
        )
        for index, header in enumerate(headers)
    ]
    separator = "+-" + "-+-".join("-" * width for width in widths) + "-+"

    def print_row(row: list[str]) -> None:
        lines = [value.splitlines() or [""] for value in row]
        for line_index in range(max(len(value) for value in lines)):
            values = [
                value[line_index] if line_index < len(value) else ""
                for value in lines
            ]
            print(
                "| "
                + " | ".join(value.ljust(width) for value, width in zip(values, widths))
                + " |"
            )

    print(separator)
    print_row(headers)
    print(separator)
    for row in rows:
        print_row(row)
    print(separator)


def comparison_rows(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    rows = connection.execute(
        """
        SELECT
            r.run_id,
            r.model_name,
            r.prompt_variant,
            r.judge_model,
            COUNT(e.test_case_id) AS total_cases,
            AVG(e.correct) AS accuracy,
            SUM(CASE WHEN e.actual_has_bug = 1 THEN 1 ELSE 0 END) AS buggy_cases,
            SUM(CASE WHEN e.actual_has_bug = 1 AND e.predicted_has_bug = 1
                     THEN 1 ELSE 0 END) AS true_positives,
            SUM(CASE WHEN e.actual_has_bug = 0 THEN 1 ELSE 0 END) AS clean_cases,
            SUM(CASE WHEN e.actual_has_bug = 0 AND e.predicted_has_bug = 1
                     THEN 1 ELSE 0 END) AS false_positives,
            AVG(e.judge_score) AS average_judge_score,
            AVG(e.similarity_score) AS average_similarity_score
        FROM runs AS r
        JOIN eval_results AS e ON e.run_id = r.run_id
        GROUP BY r.run_id
        """
    ).fetchall()
    return sorted(
        rows,
        key=lambda row: (
            row[10] is not None,
            row[10] if row[10] is not None else float("-inf"),
        ),
        reverse=True,
    )


def print_comparison(connection: sqlite3.Connection) -> None:
    rows = comparison_rows(connection)
    if not rows:
        print("No completed evaluation results found.")
        return
    output = []
    for row in rows:
        (
            _run_id,
            model_name,
            prompt_variant,
            judge_model,
            total_cases,
            accuracy,
            buggy_cases,
            true_positives,
            clean_cases,
            false_positives,
            average_judge_score,
            average_similarity_score,
        ) = row
        recall = true_positives / buggy_cases if buggy_cases else None
        false_positive_rate = false_positives / clean_cases if clean_cases else None
        output.append(
            [
                model_name,
                prompt_variant,
                judge_model,
                f"{accuracy:.1%}" if accuracy is not None else "N/A",
                f"{recall:.1%}" if recall is not None else "N/A",
                (
                    f"{false_positive_rate:.1%}"
                    if false_positive_rate is not None
                    else "N/A"
                ),
                format_score(average_judge_score),
                format_score(average_similarity_score),
                str(total_cases),
            ]
        )
    print_table(
        [
            "Model",
            "Prompt",
            "Judge",
            "Accuracy",
            "Bug recall",
            "Clean FPR",
            "Avg judge",
            "Avg similarity",
            "Cases",
        ],
        output,
    )


def print_case_comparison(connection: sqlite3.Connection, case_id: str) -> None:
    rows = connection.execute(
        """
        SELECT
            r.model_name,
            r.prompt_variant,
            r.judge_model,
            r.run_id,
            e.predicted_has_bug,
            e.model_explanation,
            e.judge_score,
            e.similarity_score,
            e.judge_reasoning
        FROM eval_results AS e
        JOIN runs AS r ON r.run_id = e.run_id
        WHERE e.test_case_id = ?
        ORDER BY r.started_at, r.model_name, r.prompt_variant
        """,
        (case_id,),
    ).fetchall()
    if not rows:
        print(f"No evaluation results found for test case {case_id!r}.")
        return

    output: list[list[str]] = []
    for (
        model_name,
        prompt_variant,
        judge_model,
        run_id,
        predicted_has_bug,
        explanation,
        judge_score,
        similarity_score,
        judge_reasoning,
    ) in rows:
        output.append(
            [
                model_name,
                prompt_variant,
                judge_model,
                "bug" if predicted_has_bug else "clean",
                textwrap.fill(explanation or "", width=72),
                str(judge_score) if judge_score is not None else "N/A",
                format_score(similarity_score),
                textwrap.fill(judge_reasoning or "N/A", width=48),
                run_id[:8],
            ]
        )
    print(f"Results for test case {case_id}:")
    print_table(
        [
            "Model",
            "Prompt",
            "Judge",
            "Prediction",
            "Explanation",
            "Judge",
            "Similarity",
            "Judge reasoning",
            "Run",
        ],
        output,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare Rubric evaluation runs or inspect one test case."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument(
        "--case",
        metavar="TEST_CASE_ID",
        help="Show every run's prediction, explanation, and scores for this case",
    )
    args = parser.parse_args()

    if not args.database.exists():
        parser.error(f"database file does not exist: {args.database}")
    with sqlite3.connect(args.database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if not {"runs", "eval_results"}.issubset(tables):
            parser.error(f"{args.database} does not contain Rubric run tables")
        if args.case:
            print_case_comparison(connection, args.case)
        else:
            print_comparison(connection)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
