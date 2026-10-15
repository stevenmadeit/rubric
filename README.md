# Rubric

Rubric evaluates an Ollama model's ability to identify bugs in short Python and
JavaScript snippets.

## Run an evaluation

Install Python dependencies and pull the embedding model:

```powershell
pip install -r requirements.txt
ollama pull nomic-embed-text
```

For a complete model/prompt comparison, pull the tested models and independent
judge, then start Ollama and run:

```powershell
ollama pull llama3
ollama pull qwen2.5-coder:7b
ollama pull mistral
ollama pull qwen2.5:3b
python run_eval.py --all
python compare.py
```

`--all` runs each of `llama3`, `qwen2.5-coder:7b`, and `mistral` against the
`basic`, `step_by_step`, and `structured` prompt variants. Use `--model` and
`--prompt-variant` to run one combination; both default to `llama3` and `basic`.
The prompts are defined in `prompts.py`.

All combinations in a single `--all` invocation use one judge model, set by
`JUDGE_MODEL` or defaulting to the independent `qwen2.5:3b`. The all-model run
rejects a judge that is also one of the models under evaluation. A fixed,
independent judge matters because it keeps explanation scores comparable across
models and avoids self-judging bias. For example, set an alternative judge in
PowerShell with `$env:JUDGE_MODEL = "your-judge-model"` before running.

The runner writes each evaluation to a `runs` row and associates its per-case
results through `run_id`. `compare.py` shows the judge model for transparency, sorts runs by average judge
score, and prints accuracy, buggy-case recall, clean-case false-positive rate,
and average judge and similarity scores. Use `python compare.py --case py-15` to see every
run's prediction, explanation, and scores for one test case.

Clean snippets receive null judge and similarity scores. Similarity is clamped
to the 0-to-1 range, and averages include only cases with a score. The database
migration preserves existing results and groups legacy rows by their original
model and evaluation timestamp, labeling their prompt as `basic`. Where old
rows had no recorded judge score, their run's judge is labeled
`not_recorded`. The historical scored run retains its original `llama3` judge;
new `--all` runs use the same independent judge. The comparison table displays
the judge model so historical scores from a different judge are identifiable.
