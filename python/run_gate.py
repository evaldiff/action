"""evaldiff gate driver — runs inside the GitHub Action.

Reads env (ED_*) set by action.yml, drives the public evaldiff API,
prints the report to the GitHub log, sets outputs, and exits non-zero
when the gate fails.

Stdlib only — the runner image already has python3 + urllib.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("ED_API_URL", "https://api.evaldiff.io").rstrip("/")
KEY = os.environ.get("ED_API_KEY", "")
DATASET_JSON = os.environ.get("ED_DATASET_JSON", "").strip()
RUN_ID = os.environ.get("ED_RUN_ID", "").strip()
MODEL = os.environ.get("ED_MODEL", "gpt-4o-mini")
ENDPOINT = os.environ.get("ED_MODEL_URL", "").strip() or "https://api.openai.com/v1"
MODEL_KEY = os.environ.get("ED_MODEL_KEY", "")
THRESHOLD = float(os.environ.get("ED_THRESHOLD", "0.8") or 0)
TIMEOUT = int(os.environ.get("ED_TIMEOUT", "600") or 600)
FAIL_ON_REGRESS = os.environ.get("ED_FAIL_ON_REGRESS", "false").strip().lower() in ("1", "true", "yes")


def api(method: str, path: str, body=None, timeout=30):
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        try:
            detail = json.loads(detail).get("detail", detail)
        except Exception:
            pass
        raise SystemExit(f"::error::evaldiff API {method} {path} -> {e.code}: {detail}")


def set_output(name: str, value: str) -> None:
    print(f"::set-output name={name}::{value}")
    g = os.environ.get("GITHUB_OUTPUT")
    if g:
        with open(g, "a") as f:
            f.write(f"{name}={value}\n")


def load_dataset() -> dict:
    with open(DATASET_JSON) as f:
        raw = json.load(f)
    if isinstance(raw, list):
        return {"name": os.path.basename(DATASET_JSON), "cases": raw}
    if isinstance(raw, dict) and "cases" in raw:
        return raw
    raise SystemExit(
        f"::error::Could not parse dataset {DATASET_JSON}: "
        "expected a list of cases or {name, cases:[...]}."
    )


def main() -> int:
    if not KEY:
        print("::error::ED_API_KEY is empty. Pass api_key to the action.")
        return 2

    # --- 1. obtain a run ----------------------------------------------------
    if RUN_ID:
        run = api("GET", f"/v1/runs/{RUN_ID}")
        print(f"::notice::Using existing run {RUN_ID} ({run['status']}, model {run.get('model')}).")
        fresh = run["status"] in ("queued", "running")
    else:
        ds = load_dataset()
        print(f"::notice::Uploading dataset '{ds['name']}' with {len(ds['cases'])} cases.")
        d = api("POST", "/v1/datasets", ds)
        r = api(
            "POST",
            "/v1/runs",
            {
                "dataset_id": d["id"],
                "model": MODEL,
                "endpoint": ENDPOINT,
                "api_key": MODEL_KEY,
                "threshold": THRESHOLD,
            },
        )
        run_id = r["id"]
        print(f"::notice::Started run {run_id} on {MODEL} (threshold {THRESHOLD:.0%}).")
        fresh = True

    # --- 2. wait for completion --------------------------------------------
    if fresh:
        deadline = time.time() + TIMEOUT
        last = ""
        while time.time() < deadline:
            run = api("GET", f"/v1/runs/{run_id}")
            line = (
                f"run {run_id}: {run['status']} "
                f"passed={run.get('passed_cases')}/{run.get('total_cases')}"
            )
            if line != last:
                print(line)
                last = line
            if run["status"] == "done":
                break
            if run["status"] == "failed":
                print(f"::error::Run failed: {run.get('error')}")
                set_output("passed", "false")
                return 3
            time.sleep(3)
        else:
            print(f"::error::Timed out after {TIMEOUT}s waiting for run {run_id}.")
            set_output("passed", "false")
            return 4

    run = api("GET", f"/v1/runs/{run_id}")
    total = run.get("total_cases") or 0
    passed = run.get("passed_cases") or 0
    pass_rate = (passed / total) if total else 0.0

    # --- 3. report ----------------------------------------------------------
    req = urllib.request.Request(
        f"{API}/v1/runs/{run_id}/report.md",
        headers={"Authorization": f"Bearer {KEY}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        report = r.read().decode()
    print("::group::evaldiff report")
    print(report)
    print("::endgroup::")

    # --- 4. gate -------------------------------------------------------------
    ok = pass_rate >= THRESHOLD if THRESHOLD > 0 else True
    regress = False
    if FAIL_ON_REGRESS:
        # compare against the account's previous best run on the same dataset
        runs = api("GET", "/v1/runs")
        prior = [
            x
            for x in runs
            if x["id"] != run_id and x.get("dataset_id") == run.get("dataset_id") and x.get("total_cases")
        ]
        if prior:
            best = max(prior, key=lambda x: (x.get("avg_score") or 0))
            regress = (run.get("avg_score") or 0) < (best.get("avg_score") or 0)
            print(
                f"::notice::Baseline best avg_score {best.get('avg_score')} "
                f"(run {best['id']}); this run {run.get('avg_score')}."
            )
            if regress:
                ok = False

    print(
        f"::notice::GATE {'PASS' if ok else 'FAIL'}: "
        f"pass_rate={pass_rate:.2%} (threshold {THRESHOLD:.0%})"
        + (" + regressions" if regress else "")
    )
    set_output("run_id", str(run_id))
    set_output("passed", "true" if ok else "false")
    set_output("pass_rate", f"{pass_rate:.4f}")
    set_output("report", report)
    return 0 if ok else 5


if __name__ == "__main__":
    sys.exit(main())
