"""
Build full_cube.json from full CSV for exact 8.5M filtering basis.

Outputs:
  - full_cube.json with:
      ymh_type[year][month][hour][type] = count
      comm_ymh_type[comm][year][month][hour][type] = count
"""

import csv
import json
from collections import defaultdict
from datetime import datetime

CSV_FILE = "Crimes_-_2001_to_Present_20260421.csv"
OUT_FILE = "full_cube.json"


def parse_date(s):
    try:
        dt = datetime.strptime(s, "%m/%d/%Y %I:%M:%S %p")
        return dt.year, dt.month, dt.hour
    except Exception:
        return None


def nested():
    return defaultdict(nested)


def main():
    ymh_type = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int))))
    comm_ymh_type = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int)))))

    total = 0
    used = 0

    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            if total % 500000 == 0:
                print(f"processed {total:,}, valid {used:,}", flush=True)

            parsed = parse_date(row.get("Date", ""))
            if not parsed:
                continue
            year, month, hour = parsed
            ctype = (row.get("Primary Type") or "OTHER").strip().upper()
            comm_raw = (row.get("Community Area") or "").strip()
            comm = int(comm_raw) if comm_raw.isdigit() else 0

            ys, ms, hs = str(year), str(month), str(hour)
            ymh_type[ys][ms][hs][ctype] += 1
            if comm > 0:
                cs = str(comm)
                comm_ymh_type[cs][ys][ms][hs][ctype] += 1
            used += 1

    out = {
        "meta": {
            "built_at": datetime.now().isoformat(timespec="seconds"),
            "source_csv": CSV_FILE,
            "rows_total": total,
            "rows_used": used,
        },
        "ymh_type": {y: {m: {h: dict(t) for h, t in mh.items()} for m, mh in mm.items()} for y, mm in ymh_type.items()},
        "comm_ymh_type": {
            c: {y: {m: {h: dict(t) for h, t in mh.items()} for m, mh in mm.items()} for y, mm in yy.items()}
            for c, yy in comm_ymh_type.items()
        },
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    print(f"done: {OUT_FILE}")


if __name__ == "__main__":
    main()

