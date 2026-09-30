# evaldiff — CI gate for LLM prompts

[evaldiff.io](https://evaldiff.io) runs your prompt dataset against a model
and **fails your CI job** when quality drops below your threshold.

```yaml
# .github/workflows/evaldiff.yml
name: prompt-quality
on:
  pull_request:
    paths:
      - 'prompts/**'
      - 'src/**'
jobs:
  evaldiff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: evaldiff/action@v1
        with:
          api_key: ${{ secrets.EVALDIFF_API_KEY }}
          dataset_json: prompts/regression.json
          model: gpt-4o-mini            # model id under test
          model_url: https://api.openai.com/v1
          api_key_model: ${{ secrets.OPENAI_API_KEY }}
          threshold: 0.8                # fail if pass rate < 80%
```

That's the whole integration. The action:

1. uploads your dataset to evaldiff.io (or re-evaluates an existing run),
2. starts a run and waits for it,
3. prints the full report in the job log,
4. **fails the job** if the pass rate is below `threshold`.

## Inputs

| input | default | description |
|---|---|---|
| `api_url` | `https://api.evaldiff.io` | evaldiff API base URL |
| `api_key` | — | your evaldiff key (`eval_…`), get one from the API |
| `dataset_json` | — | path to a dataset: a list of cases, or `{"name":…, "cases":[…]}` |
| `run_id` | — | re-evaluate an existing run (e.g. a main-branch baseline) instead of uploading |
| `model` | `gpt-4o-mini` | model id under test |
| `model_url` | OpenAI | OpenAI-compatible base URL for the model under test |
| `api_key_model` | env | key for the model under test (falls back to `MODEL_API_KEY` / `OPENAI_API_KEY`) |
| `threshold` | `0.8` | min pass rate to pass the gate (0 = no gating) |
| `timeout_seconds` | `600` | max wait for the run |
| `fail_on_regressions` | `false` | also fail when the run scores below the account's best prior run |

## Dataset format

Each case: `input` (the prompt) and `expected` (what a correct answer looks like).
Prefix `expected` with `[[exact]]` for exact-match scoring; otherwise the check is
"answer contains expected". Add a `rubric` list for LLM-judged criteria.

```json
[
  {"input": "Translate to Swedish: Hello, how are you?",
   "expected": "Hej, hur mår du?"},
  {"input": "Summarize in one word: the sea is blue and calm",
   "expected": "[[exact]] calm"},
  {"input": "Write a haiku about snow",
   "expected": "",
   "rubric": ["exactly three lines", "references snow"]}
]
```

## Outputs

`run_id`, `passed`, `pass_rate`, `report` (markdown).

## Self-serve

evaldiff.io is self-serve: `POST /v1/auth/signup` with an email returns an
API key. No sales call, no setup.
