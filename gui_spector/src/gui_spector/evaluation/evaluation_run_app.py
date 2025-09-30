from __future__ import annotations
import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional
import pandas as pd
import shutil
import traceback

from gui_spector.models import (
    Requirements,
    RequirementsPriority,
    AcceptanceCriterion,
    Inputs,
)
from gui_spector.verfication.agent import VerficationRunner, PROMPT_TEMPLATE_V1
from gui_spector.computers.docker import DockerComputer



def acknowledge_safety_check_callback(message: str) -> bool:
    print(f"Safety check: {message}")
    return True


def project_root() -> Path:
    # .../gui_spector/src/gui_spector/evaluation/evaluation_run_app.py -> workspace root
    return Path(__file__).resolve().parents[4]


def load_requirements_from_csv(app_stem: str) -> List[Requirements]:
    base_dir = project_root() / "evaluation" / "annotations" / "csvs"
    # Try both .CSV and .csv
    candidates = [base_dir / f"{app_stem}.CSV", base_dir / f"{app_stem}.csv"]
    csv_path = next((p for p in candidates if p.exists()), None)
    if not csv_path:
        raise FileNotFoundError(f"CSV not found for '{app_stem}' in {base_dir}")
    print(f"[loader] Using CSV: {csv_path}")

    requirements: List[Requirements] = []

    def _parse_rows(encoding: str, errors: str = "strict") -> List[Requirements]:
        parsed: List[Requirements] = []
        with open(csv_path, "r", encoding=encoding, errors=errors, newline="") as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                req_text = (row.get("Requirement") or row.get("requirement") or "").strip()
                if not req_text:
                    continue

                req_id = (row.get("ID") or row.get("Id") or row.get("id") or "").strip()
                rand_id = (row.get("Rand_ID") or row.get("Rand Id") or row.get("RandId") or "").strip()

                # Collect up to three acceptance criteria; ignore empty
                ac_texts = []
                for idx in (1, 2, 3):
                    key = f"Accept. Crit. {idx}"
                    alt_key = f"Accept.Crit.{idx}"
                    text = (row.get(key) or row.get(alt_key) or "").strip()
                    if text:
                        ac_texts.append((idx, text))

                acceptance: List[AcceptanceCriterion] = []
                for idx, text in ac_texts:
                    acceptance.append(AcceptanceCriterion.create(name=f"AC-{idx}", text=text))

                requirement = Requirements.create(
                    title=req_text,
                    description=req_text,
                    source=app_stem,
                    tags=[app_stem],
                    acceptance_criteria=acceptance,
                    priority=RequirementsPriority.MEDIUM,
                    metadata={
                        "csv_row": row,
                        "rand_id": rand_id,
                    },
                )
                parsed.append(requirement)
                print(f"[loader] Parsed req: id={req_id or 'n/a'} rand_id={rand_id or 'n/a'} acs={len(acceptance)}")
        return parsed

    tried = []
    for enc, err_mode in [("utf-8-sig", "strict"), ("cp1252", "strict"), ("latin-1", "replace")]:
        try:
            requirements = _parse_rows(enc, err_mode)
            print(f"[loader] Decoded CSV using encoding='{enc}' (errors='{err_mode}')")
            break
        except UnicodeDecodeError as e:
            tried.append(f"{enc}/{err_mode}")
            print(f"[loader] UnicodeDecodeError with encoding='{enc}' ({e}); trying next...")
            continue
    else:
        raise UnicodeDecodeError("csv", b"", 0, 1, f"Failed to decode using tried encodings: {', '.join(tried)}")

    print(f"[loader] Total parsed requirements: {len(requirements)}")
    return requirements


def print_sample(requirements: List[Requirements], count: int = 3) -> None:
    print("Loaded requirements sample:")
    for req in requirements[: max(0, count)]:
        print(f"- {req.title}: {req.description[:100]}{'...' if len(req.description) > 100 else ''}")
        if req.acceptance_criteria:
            for ac in req.acceptance_criteria:
                print(f"  {ac.name}: {ac.text}")


def split_into_batches(requirements: List[Requirements], num_batches: int = 3) -> List[List[Requirements]]:
    if num_batches <= 0:
        return [requirements]
    total = len(requirements)
    if total == 0:
        return [[] for _ in range(num_batches)]
    batch_size = (total + num_batches - 1) // num_batches  # ceil division
    batches: List[List[Requirements]] = []
    for start in range(0, total, batch_size):
        end = start + batch_size
        batches.append(requirements[start:end])
    # Trim to requested number of batches (in case of off-by-one when total < num_batches)
    if len(batches) < num_batches:
        batches.extend([[] for _ in range(num_batches - len(batches))])
    batches = batches[:num_batches]
    print("[batching] Batch sizes:", [len(b) for b in batches])
    return batches


def _results_columns(acceptance_slots: int = 3) -> List[str]:
    headers = [
        "requirement_id",
        "rand_id",
        "title",
        "status",
        "started_at",
        "finished_at",
        "elapsed_s",
        "start_url",
        "current_url",
        "steps_taken",
        "run_dir",
        "error",
        "usage_input_tokens",
        "usage_output_tokens",
        "usage_reasoning_tokens",
        "usage_total_tokens",
        "model_decision_json",
        "interactions_json",
        "requirement_description",
    ]
    for i in range(1, acceptance_slots + 1):
        headers.append(f"ac_{i}_name")
        headers.append(f"ac_{i}_text")
        headers.append(f"ac_{i}_status")
    return headers


def ensure_results_csv_with_header(path: Path, acceptance_slots: int = 3) -> None:
    if path.exists():
        print(f"[results] CSV exists (will append): {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = _results_columns(acceptance_slots)
    df = pd.DataFrame(columns=columns)
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"[results] Created CSV with header: {path}")


def write_result_row(path: Path, result, acceptance_slots: int = 3) -> None:
    usage = result.usage_total.to_dict() if getattr(result, "usage_total", None) else None
    # Map AC name -> status from model_decision if present
    ac_status_map = {}
    try:
        if isinstance(result.model_decision, dict):
            for item in (result.model_decision.get("acceptance_criteria_results") or []):
                name = str(item.get("criterion_name") or item.get("name") or "").strip()
                status_val = item.get("status")
                met = item.get("met")
                if isinstance(met, bool):
                    status_val = "met" if met else "unmet"
                ac_status_map[name] = status_val
    except Exception:
        ac_status_map = {}

    # Try to read rand_id from requirement metadata
    try:
        rand_id_val = str(((getattr(result, "requirement", None) or {}).metadata or {}).get("rand_id") or "")
    except Exception:
        rand_id_val = ""

    row_dict = {
        "requirement_id": str(result.requirement_id),
        "rand_id": rand_id_val,
        "title": getattr(result.requirement, "title", ""),
        "status": getattr(result.status, "value", str(result.status)),
        "started_at": result.started_at.isoformat() if isinstance(result.started_at, datetime) else str(result.started_at),
        "finished_at": result.finished_at.isoformat() if isinstance(result.finished_at, datetime) else str(result.finished_at),
        "elapsed_s": f"{getattr(result, 'elapsed_s', 0.0):.3f}",
        "start_url": result.start_url,
        "current_url": result.current_url or "",
        "steps_taken": getattr(result, "steps_taken", 0),
        "run_dir": str(getattr(result, "run_dir", "")),
        "error": getattr(result, "error", "") or "",
        "usage_input_tokens": (usage or {}).get("input_tokens", ""),
        "usage_output_tokens": (usage or {}).get("output_tokens", ""),
        "usage_reasoning_tokens": (usage or {}).get("reasoning_tokens", ""),
        "usage_total_tokens": (usage or {}).get("total_tokens", ""),
        "model_decision_json": json.dumps(result.model_decision, ensure_ascii=False) if isinstance(result.model_decision, dict) else "",
        "interactions_json": json.dumps([asdict(i) for i in (result.interactions or [])], default=str, ensure_ascii=False) if getattr(result, "interactions", None) else "",
        "requirement_description": getattr(result.requirement, "description", ""),
    }

    # Append AC details (text + status if found)
    acs = list(getattr(result.requirement, "acceptance_criteria", []) or [])
    for idx in range(acceptance_slots):
        if idx < len(acs):
            ac = acs[idx]
            ac_name = getattr(ac, "name", f"AC-{idx+1}")
            ac_text = getattr(ac, "text", "")
            ac_status = ac_status_map.get(str(ac_name), "")
            row_dict[f"ac_{idx+1}_name"] = ac_name
            row_dict[f"ac_{idx+1}_text"] = ac_text
            row_dict[f"ac_{idx+1}_status"] = ac_status
        else:
            row_dict[f"ac_{idx+1}_name"] = ""
            row_dict[f"ac_{idx+1}_text"] = ""
            row_dict[f"ac_{idx+1}_status"] = ""

    df_row = pd.DataFrame([row_dict], columns=_results_columns(acceptance_slots))
    df_row.to_csv(path, mode="a", header=False, index=False, encoding="utf-8")
    print(f"[results] Appended result: req_id={row_dict['requirement_id']} status={row_dict['status']} to {path}")


def run_batch(batch_id: int, requirements: List[Requirements], display: str, start_url: str, results_dir: Path, inputs: Optional[Inputs] = None, max_retries: int = 0) -> None:
    batch_dir = results_dir / f"batch_{batch_id}"
    csv_dir = batch_dir / "csv"
    runs_dir = batch_dir / "runs"
    csv_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    csv_path = csv_dir / f"batch_{batch_id}.csv"
    ensure_results_csv_with_header(csv_path)
    print(f"[runner] Starting batch {batch_id} with {len(requirements)} requirements on display {display}")
    print(f"[runner] Paths: batch_dir={batch_dir} csv_dir={csv_dir} runs_dir={runs_dir}")
    with DockerComputer(display=display) as computer:
        total = len(requirements)
        errors: List[dict] = []
        for i, req in enumerate(requirements, start=1):
            rand_id = ""
            try:
                rand_id = str((req.metadata or {}).get("rand_id") or "").strip()
            except Exception:
                rand_id = ""
            req_id_str = rand_id if rand_id else str(getattr(req, "id", "unknown"))

            attempt = 0
            while attempt <= max_retries:
                try:
                    per_run_dir = runs_dir / req_id_str
                    if per_run_dir.exists():
                        print(f"[runner] Clearing existing run dir: {per_run_dir}")
                        shutil.rmtree(per_run_dir, ignore_errors=True)
                    per_run_dir.mkdir(parents=True, exist_ok=True)
                    print("\n" + "-" * 75)
                    print(f"[progress] Batch {batch_id} | Item {i}/{total} | attempt {attempt+1}/{max_retries+1} | display={display}")
                    print("-" * 75)
                    print(f"[runner] Running requirement id={req_id_str} dir={per_run_dir}")

                    runner = VerficationRunner(
                        computer=computer,
                        acknowledge_safety_check_callback=acknowledge_safety_check_callback,
                        prompt_name=PROMPT_TEMPLATE_V1,
                        run_dir=per_run_dir,
                    )

                    result = runner.run(
                        requirement=req,
                        start_url=start_url,
                        inputs=inputs,
                        print_steps=False,
                        show_images=False,
                        debug=False,
                    )
                    write_result_row(csv_path, result)
                    print(f"[batch {batch_id}] Saved result for {req.title}")
                    try:
                        status_str = getattr(result.status, "value", str(result.status))
                    except Exception:
                        status_str = "?"
                    print(f"[progress] Completed {i}/{total} | status={status_str}")
                    print("-" * 75 + "\n")
                    break  # success
                except Exception as e:
                    err_text = f"{type(e).__name__}: {e}"
                    tb = traceback.format_exc()
                    print(f"[batch {batch_id}] Error for {getattr(req, 'title', '?')} on attempt {attempt+1}: {err_text}")
                    errors.append({
                        "batch_id": batch_id,
                        "rand_id": (req.metadata or {}).get("rand_id") if getattr(req, "metadata", None) else "",
                        "requirement_id": str(getattr(req, "id", "")),
                        "title": getattr(req, "title", ""),
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "error": err_text,
                        "traceback": tb,
                    })
                    attempt += 1
                    if attempt <= max_retries:
                        print(f"[retry] Retrying ({attempt}/{max_retries}) for {req_id_str}...")
                    else:
                        print(f"[giveup] Max retries reached for {req_id_str}")
    print(f"[runner] Finished batch {batch_id}")
    # Persist errors if any
    if 'errors' in locals() and errors:
        errors_csv = csv_dir / f"errors_batch_{batch_id}.csv"
        df_err = pd.DataFrame(errors)
        if errors_csv.exists():
            df_err.to_csv(errors_csv, mode="a", header=False, index=False, encoding="utf-8")
        else:
            df_err.to_csv(errors_csv, index=False, encoding="utf-8")
        print(f"[runner] Wrote {len(errors)} error records to {errors_csv}")


def main() -> None:
    # Limits and defaults
    APP_STEM: str = "02"
    START_URL: str = "http://192.168.178.40:8010/"
    NUM_BATCHES: int = 3
    DEFAULT_DISPLAYS: Tuple[str, str, str] = (":99", ":100", ":101")
    # Requirement slice configuration (start, end) pairs and selected index
    BATCH_SLICES: List[Tuple[int, int]] = [(0, 10), (10, 20), (20, 30)]
    BATCH_INDEX: int = 2
    MAX_RETRIES: int = 3
    # Provide realistic test inputs for the agent to use in forms
    inputs = Inputs.create({
        "name": "John Doe",
        "email": "john.doe@doesnotexist.org",
        "phone": "155512345678",
        "address": "123 Test Street, Testville, TX 75001",
        "city": "Testville",
        "zip code": "75001",
        "card number": "4242424242424242",
        "card expiry": "12/30",
        "card cvc": "123",
        "promo code 1": "SAVE10",
        "promo code 2": "FRESH20",
        "license plate": "ABC-123",
    })

    print(f"[config] APP_STEM={APP_STEM} START_URL={START_URL} NUM_BATCHES={NUM_BATCHES}")
    print(f"[config] BATCH_SLICES={BATCH_SLICES} BATCH_INDEX={BATCH_INDEX}")
    requirements = load_requirements_from_csv(APP_STEM)
    print(f"[load] Total loaded: {len(requirements)}")
    try:
        start_idx, end_idx = BATCH_SLICES[BATCH_INDEX]
    except Exception:
        start_idx, end_idx = 0, len(requirements)
    requirements = requirements[start_idx:end_idx]
    print(f"[load] Using sliced requirements [{start_idx}:{end_idx}] -> {len(requirements)} items")
    print_sample(requirements)
    batches = split_into_batches(requirements, num_batches=NUM_BATCHES)

    results_root = project_root() / "evaluation" / "results" / APP_STEM
    results_root.mkdir(parents=True, exist_ok=True)
    print(f"[paths] Results root: {results_root}")

    display_triplet = DEFAULT_DISPLAYS
    print(f"[config] Displays: {display_triplet} | NUM_BATCHES={NUM_BATCHES} | MAX_RETRIES={MAX_RETRIES}")
    tasks = []
    with ThreadPoolExecutor(max_workers=NUM_BATCHES) as executor:
        for idx, reqs in enumerate(batches, start=1):
            if not reqs:
                continue
            display = display_triplet[(idx - 1) % len(display_triplet)]
            tasks.append(
                executor.submit(
                    run_batch,
                    batch_id=idx,
                    requirements=reqs,
                    display=display,
                    start_url=START_URL,
                    results_dir=results_root,
                    inputs=inputs,
                    max_retries=MAX_RETRIES,
                )
            )
            print(f"[schedule] Submitted batch {idx} with {len(reqs)} reqs to display {display}")

        for fut in as_completed(tasks):
            _ = fut.result()
            print("[schedule] One batch future completed")


if __name__ == "__main__":
    main()


