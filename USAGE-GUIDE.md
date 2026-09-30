# Testing evaldiff, step by step

This walks you through the whole product as a brand-new user.
You only need `curl` and `python3` (for reading the JSON).
Every command is copy-paste ready — replace the marked values.

**What you'll do:** sign up → make a dataset → run it on a model →
read the pass/fail report. Then wire it into CI so it gates your code.

---

## Step 1 — Confirm the API is alive

No login needed.

```bash
curl https://api.evaldiff.io/health
```

**Expected:** `{"status":"ok","version":"0.0.5","storage":"S3Storage"}`

If you see that, we're good. If not, stop and tell me the output.

---

## Step 2 — Create your account (one request)

```bash
curl -s -X POST https://api.evaldiff.io/v1/auth/signup \
  -H 'Content-Type: application/json' \
  -d '{"email":"YOU@example.com"}'
```

> ⚠️ Replace `YOU@example.com` with your real email. Use a different
> email each time to get a fresh key, or reuse one to keep the same key.

**Expected output:**
```json
{"key":"eval_abc123...","email":"YOU@example.com","quota":1000}
```

**Save the `key` value** — that's your API key. You get 1,000 case-runs/month free.

```bash
export KEY="***"   # ← paste your key between the quotes
echo "$KEY"        # ← verify it printed (should be eval_...)
```

---

## Step 3 — Create a dataset

A dataset is just a list of test cases. Each case is:
- `input` — the question/prompt the model sees
- `expected` — a short phrase you expect to appear in the answer
  (or `[[exact]] answer` if you want an exact match)

```bash
curl -s -X POST https://api.evaldiff.io/v1/datasets \
  -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "my-first-dataset",
    "cases": [
      {"input": "What is the capital of France?", "expected": "Paris"},
      {"input": "In one word, what color is the sky?", "expected": "blue"},
      {"input": "What does HTTP stand for?", "expected": "protocol"}
    ]
  }'
```

> These 3 cases use general knowledge so a model *can* get them right.
> For your real use, make `input` a real prompt and `expected` the phrase
> a correct answer must contain.

**Expected output:** `{"id": 42, "name":"my-first-dataset", "case_count":3, ...}`

**Copy the `id` number** (e.g. `42`).

```bash
export DATA_ID=42          # ← paste YOUR dataset id number (no quotes needed)
```

*Lost the id?* List your datasets:
```bash
curl -s https://api.evaldiff.io/v1/datasets -H "Authorization: Bearer $KEY"
```

---

## Step 4 — Run the dataset against a model

You need an **API key for the model** you want to test (here, OpenAI).
Put it in a file so we can read it:

```bash
# If you already have it saved:
#   cat ~/.config/openai.token
# Otherwise, put your OpenAI key in that file first, or set it directly:
export OPENAI_KEY="***"   # ← your model provider's key
```

Now start the run:

```bash
RUN_ID=$(curl -s -X POST https://api.evaldiff.io/v1/runs \
  -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "dataset_id": '"$DATA_ID"',
    "model": "gpt-4o-mini",
    "endpoint": "https://api.openai.com/v1",
    "api_key": "'"$OPENAI_KEY"'",
    "threshold": 0.5
  }' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

echo "run: $RUN_ID"
```

**Expected:** `run: 18` (some number).

> If you get a `KeyError: 'id'`, the API rejected the request.
> Re-run the same `curl` **without** the `| python3 ...` pipe — the raw
> JSON error will tell you exactly what's wrong (see Troubleshooting below).

**What each field means:**
| field | what it is |
|---|---|
| `dataset_id` | the number from Step 3 |
| `model` | the model id to test (`gpt-4o-mini`, `gpt-4o`, etc.) |
| `endpoint` | where that model lives (`https://api.openai.com/v1` for OpenAI) |
| `api_key` | the key for *that* model (not your evaldiff key) |
| `threshold` | 0–1. A case "passes" if its score ≥ this. Lower = more lenient. |

---

## Step 5 — Watch it finish and read the report

The run takes a few seconds (one call per case). Poll until it's done:

```bash
# Wait ~10s then check status:
sleep 10
curl -s "https://api.evaldiff.io/v1/runs/$RUN_ID" -H "Authorization: Bearer $KEY"
```

**Expected (when done):**
```json
{"id":18,"status":"done","model":"gpt-4o-mini","total_cases":3,
 "passed_cases":3,"avg_score":1.0,"error":null}
```

`status` goes `queued → running → done`. If it says `done`, it finished.

Now the human-readable report:

```bash
curl -s "https://api.evaldiff.io/v1/runs/$RUN_ID/report.md" -H "Authorization: Bearer $KEY"
```

**Expected:**
```
# evaldiff report — run 18 (gpt-4o-mini)

| metric    | value |
|---|---|
| avg score | 1.000 |
| cases     | 3 |
| passed    | 3 |
| pass rate | 100.0% |
```

🎉 **That's the whole API product.** Dataset in → scored run out → pass/fail.

---

## Step 6 (optional) — Wire it into CI so it gates your code

This is where evaldiff becomes a *gate* instead of just a report.
Your CI job turns **red** when the pass rate drops below your threshold.

1. Create `prompts/regression.json` in your repo (same shape as Step 3):
   ```json
   [
     {"input": "What is the capital of France?", "expected": "Paris"},
     {"input": "What does HTTP stand for?", "expected": "protocol"}
   ]
   ```

2. Create `.github/workflows/evaldiff.yml`:
   ```yaml
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
             api_key: ${{ secrets.EVALDIFF_API_KEY }}      # your eval_ key
             dataset_json: prompts/regression.json
             model: gpt-4o-mini
             model_url: https://api.openai.com/v1
             api_key_model: ${{ secrets.OPENAI_API_KEY }}  # the model's key
             threshold: 0.8
   ```

3. Add two secrets to the repo (GitHub → Settings → Secrets):
   - `EVALDIFF_API_KEY` = your `eval_...` key
   - `OPENAI_API_KEY` = your OpenAI key

4. Push a change to a prompt that breaks one case → **the PR goes red**
   with the failing case in the log. That's the product in one line of YAML.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `KeyError: 'id'` on the run step | API rejected the request | Re-run the run `curl` **without** the python pipe and read the raw JSON error |
| `404 dataset not found` | `DATA_ID` wrong, or key is from a different account | Re-check the id from Step 3; make sure `$KEY` created that dataset |
| `401` | Bad/empty evaldiff key | Re-run Step 2 and re-`export KEY` |
| `run: ` (blank) + no id | `OPENAI_KEY` empty | Check `echo -n "$OPENAI_KEY" | wc -c` — should be > 20 |
| All cases fail (0 passed) | `expected` phrase not in the model's answer, or model lacks the knowledge | Keep `expected` a short phrase; or use cases the model can answer (like Step 3's examples) |
| `status` stuck on `queued`/`running` | Still working, or model is slow/unreachable | Wait longer, or check the model endpoint/key is correct |

**The golden rule:** whenever a step's output looks wrong, re-run that same
`curl` **without** the `| python3 ...` pipe. The raw JSON tells you exactly
what's wrong.
