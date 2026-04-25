"""
Build full binary records for frontend full-data mode.

Outputs:
  - full_records.bin  (fixed-size records, little-endian, 16 bytes each)
  - full_meta.json    (type dictionary + format metadata)

Record layout (48 bytes; v2 adds description; readers must use record_size_bytes from meta):
  0..3   float32  lat
  4..7   float32  lng
  8..9   uint16   year
  10     uint8    month
  11     uint8    hour
  12..13 uint16   type_id
  14     uint8    community_id (1..77, 0 unknown)
  15     uint8    reserved
  16..47 utf-8    description (truncated to fit 32 bytes, zero-padded)
"""

import csv
import json
import os
import struct
from datetime import datetime

CSV_FILE = "Crimes_-_2001_to_Present_20260421.csv"
OUT_BIN = "full_records.bin"
OUT_META = "full_meta.json"


def parse_date(s):
    try:
        dt = datetime.strptime(s, "%m/%d/%Y %I:%M:%S %p")
        return dt.year, dt.month, dt.hour
    except Exception:
        return None


def main():
    if not os.path.exists(CSV_FILE):
        raise FileNotFoundError(f"Missing CSV file: {CSV_FILE}")

    type_to_id = {}
    id_to_type = {}
    next_type_id = 1
    total = 0
    written = 0

    pack = struct.Struct("<ffHBBHBB")
    DESC_BYTES = 32
    RECORD_BYTES = 16 + DESC_BYTES

    with open(CSV_FILE, "r", encoding="utf-8") as f_in, open(OUT_BIN, "wb") as f_out:
        reader = csv.DictReader(f_in)
        for row in reader:
            total += 1
            if total % 500000 == 0:
                print(f"processed {total:,}, written {written:,}", flush=True)

            parsed = parse_date(row.get("Date", ""))
            if not parsed:
                continue
            year, month, hour = parsed

            lat_s = (row.get("Latitude") or "").strip()
            lng_s = (row.get("Longitude") or "").strip()
            if not lat_s or not lng_s:
                continue
            try:
                lat = float(lat_s)
                lng = float(lng_s)
            except Exception:
                continue

            ctype = (row.get("Primary Type") or "OTHER").strip().upper()
            if ctype not in type_to_id:
                type_to_id[ctype] = next_type_id
                id_to_type[str(next_type_id)] = ctype
                next_type_id += 1
            type_id = type_to_id[ctype]

            comm_raw = (row.get("Community Area") or "").strip()
            comm = int(comm_raw) if comm_raw.isdigit() else 0
            if comm < 0 or comm > 255:
                comm = 0

            desc_raw = (row.get("Description") or "").strip()
            desc_b = desc_raw.encode("utf-8")[:DESC_BYTES]
            desc_b = desc_b + b"\x00" * (DESC_BYTES - len(desc_b))

            f_out.write(pack.pack(lat, lng, year, month, hour, type_id, comm, 0) + desc_b)
            written += 1

    meta = {
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "source_csv": CSV_FILE,
        "record_count": written,
        "record_size_bytes": RECORD_BYTES,
        "bin_file": OUT_BIN,
        "type_to_id": type_to_id,
        "id_to_type": id_to_type,
    }
    with open(OUT_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, separators=(",", ":"))

    print(f"done: {OUT_BIN} ({os.path.getsize(OUT_BIN)/1e6:.1f} MB), records={written:,}")
    print(f"done: {OUT_META}")


if __name__ == "__main__":
    main()

