"""Capture the offline demo snapshots from the current backend (manual, authorised use only).

The frontend shows these files only when the backend is unreachable, always labelled as saved
snapshots of earlier live retrievals. They are never refreshed automatically.

Usage (from backend/, with the local Earth Engine credentials and EE_PROJECT_ID in .env):

    .venv/Scripts/python.exe scripts/capture_snapshots.py            # dry run: fetch and validate only
    .venv/Scripts/python.exe scripts/capture_snapshots.py --write    # also write frontend/public/snapshots/

What it does:
* calls the application's own /api/v2 endpoints in-process (one request per investigation, so the
  existing NASA POWER / Earth Engine pipelines and the current scientific engine produce the results);
* keeps every response exactly as returned, except the per-process `cache` block, and marks the file
  `data_status: "saved_snapshot"`; the original retrieval status and time are recorded in index.json;
* never overwrites a snapshot whose request failed: the old file stays and the failure is reported;
* refuses to write if any response contains the Earth Engine project ID, a key-file path or key material.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402

OUT = BACKEND.parent / "frontend" / "public" / "snapshots"
LATITUDE, LONGITUDE = 16.8661, 96.1951
START, END = "2015-01-01", "2025-01-01"  # end-exclusive
NOTE = ("Saved outputs of live NASA retrievals through this application's API. Shown only when the backend "
        "is unreachable and clearly labelled; not a fresh query.")

INVESTIGATIONS = [
    {"variable": "temperature", "file": "yangon-2015-2024-temperature.json"},
    {"variable": "relative_humidity", "file": "yangon-2015-2024-relative_humidity.json"},
    {"variable": "extreme_heat", "file": "yangon-2015-2024-extreme_heat.json"},
    {"variable": "precipitation", "file": "yangon-2015-2024-precipitation.json"},
    {"variable": "ndvi", "file": "yangon-2015-2024-ndvi.json"},
    {"variable": "soil_moisture", "dataset": "gldas_2_1_noah_0_10cm", "file": "yangon-2015-2024-soil_moisture-gldas_2_1_noah_0_10cm.json"},
    {"variable": "soil_moisture", "dataset": "smap_l3e_v006_am", "file": "yangon-2015-2024-soil_moisture-smap_l3e_v006_am.json"},
]


def forbidden_strings() -> list[str]:
    settings = get_settings()
    values = [settings.ee_project_id, settings.ee_service_account_key_file, "PRIVATE KEY", "private_key", "client_email"]
    return [v for v in values if v]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="write the snapshot files (default: dry run)")
    args = parser.parse_args()

    client = TestClient(create_app())
    secrets = forbidden_strings()
    index_path = OUT / "index.json"
    old_index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"entries": []}
    old_entries = {e["file"]: e for e in old_index.get("entries", [])}
    captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    entries, files, failures = [], {}, []

    for inv in INVESTIGATIONS:
        params = {"variable": inv["variable"], "latitude": LATITUDE, "longitude": LONGITUDE,
                  "start_date": START, "end_date": END, "mode": "point"}
        if "dataset" in inv:
            params["dataset"] = inv["dataset"]
        response = client.get("/api/v2/analysis", params=params)
        if response.status_code != 200:
            failures.append(f"{inv['file']}: HTTP {response.status_code} {response.text[:160]}")
            if inv["file"] in old_entries:
                entries.append(old_entries[inv["file"]])  # keep the previous snapshot and its own dates
            continue
        body = response.json()
        text = json.dumps(body)
        leaked = [s for s in secrets if s in text]
        if leaked:
            print(f"REFUSING: {inv['file']} contains configuration values that must not be published.")
            return 2
        retrieved_at = (body.get("cache") or {}).get("retrieved_at") or captured_at
        original_status = body.get("data_status")
        body.pop("cache", None)
        body["data_status"] = "saved_snapshot"
        files[inv["file"]] = body
        entry = {"variable": inv["variable"], "latitude": LATITUDE, "longitude": LONGITUDE,
                 "startYear": 2015, "endYear": 2025, "mode": "point", "file": inv["file"],
                 "retrieved_at": retrieved_at, "original_data_status": original_status,
                 "dataset_id": body["dataset"]["id"], "dataset_version": body["dataset"]["version"]}
        if "dataset" in inv:
            entry["dataset"] = inv["dataset"]
        entries.append(entry)
        trend = body.get("trend") or {}
        print(f"{inv['file']}: {original_status}; {trend.get('result_level')}; slope={trend.get('slope')}; "
              f"method={trend.get('method', 'theil_sen')}; methods_lab={'methods_lab' in body}")

    variables = client.get("/api/v2/variables")
    if variables.status_code == 200:
        files["variables.json"] = variables.json()
    else:
        failures.append(f"variables.json: HTTP {variables.status_code}")

    for failure in failures:
        print("FAILED (previous file kept):", failure)
    if not args.write:
        print("Dry run: nothing written. Re-run with --write to save.")
        return 1 if failures else 0

    for name, body in files.items():
        (OUT / name).write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    index = {"captured_at": captured_at, "note": NOTE, "generator": "backend/scripts/capture_snapshots.py",
             "request": {"latitude": LATITUDE, "longitude": LONGITUDE, "start_date": START, "end_date_exclusive": END},
             "entries": entries}
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {len(files)} files and index.json (captured_at {captured_at}).")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
