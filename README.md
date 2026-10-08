# Rubric

Rubric evaluates an Ollama model's ability to identify bugs in short Python and
JavaScript snippets.

## Run an evaluation

Install Python dependencies and pull the embedding model:

```powershell
pip install -r requirements.txt
ollama pull nomic-embed-text
```

Then start Ollama and run:

```powershell
python run_eval.py
```

The default tested model and judge are `llama3`. Set `JUDGE_MODEL` to choose a
different judge; the prediction model can be selected with `--model`. Because
the default uses the same model to generate explanations and judge them,
self-judging can introduce bias in judge scores. The embedding model defaults to
`nomic-embed-text` and can be changed with `--embedding-model`.

The runner writes per-case prediction accuracy, judge scores and reasoning, and
cosine similarity to `rubric.db`. Clean snippets receive null judge and
similarity scores. Similarity is clamped to the requested 0-to-1 range. The summary
reports averages over cases with an available score. A disagreement is counted
when the judge score is 1–2 while semantic similarity is above 0.7.

Existing `eval_results` tables are migrated in place by adding nullable scoring
columns; existing result rows are preserved.
