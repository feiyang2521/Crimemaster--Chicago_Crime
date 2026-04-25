"""
build_data.py
-------------
从 Crimes CSV 生成 crime_data.json，供 index.html 加载。

输出结构：
{
  "meta": { "total": N, "built_at": "..." },

  "by_year":  { "2001": 482879, ... },           # 全局按年统计
  "by_month": { "1": 55000, ... },               # 全局按月统计
  "by_hour":  { "0": 12000, ... },               # 全局按时统计
  "by_type":  { "THEFT": 180000, ... },          # 全局按类型统计（已排序）

  "ym_type":  { "2001": { "1": { "THEFT": 300, ... }, ... }, ... },
               # 按年×月×类型 cube（用于时间筛选后 crime type 联动）

  "yh_type":  { "2001": { "14": { "THEFT": 50, ... }, ... }, ... },
               # 按年×小时×类型 cube（Year↔Hour 双向联动）

  "mh_type":  { "1": { "14": { "THEFT": 40, ... }, ... }, ... },
               # 按月×小时×类型 cube（Month↔Hour 双向联动）

  "hour_type":{ "14": { "THEFT": 2000, ... }, ... },
               # 按小时×类型（Hour 滑块→Crime Type 联动）

  "comm_type": { "1": { "THEFT": 500, ... }, ... },
               # 按社区×类型（用于悬停 Tooltip）

  "comm_risk": { "1": { "score": 0.85, "name": "Rogers Park", "total": 12000 }, ... },
               # 每个社区的危险度分数（0-1 归一化，全芝加哥范围）

  "dist_risk": { "9": { "score": 0.72, "name": "Deering", "total": 320000 }, ... },
               # 每个 District 的危险度分数（Level 0 热力图颜色）

  "dist_agg":  {
    "9": {
      "by_year":  { "2001": 5000, ... },
      "by_month": { "1": 400, ... },
      "by_hour":  { "0": 200, ... },
      "by_type":  { "THEFT": 8000, ... },
      "comm_ids": [61, 62, ...],
      "total": 98000
    }, ...
  },
               # 按 District 的所有维度聚合（用于选中 District 后切换柱状图）

  "sample_points": {
    "1": [
      { "date": "2023-01-15T14:30:00", "lat": 41.77, "lng": -87.65,
        "type": "THEFT", "desc": "RETAIL THEFT", "loc": "GROCERY FOOD STORE",
        "block": "001XX N STATE ST" },
      ...
    ], ...
  }
               # 每个社区采样至多 200 条案件点（用于 Drill-down 红点）
}
"""

import csv, json, random, math
from collections import defaultdict
from datetime import datetime

CSV_FILE   = "Crimes_-_2001_to_Present_20260421.csv"
OUT_FILE   = "crime_data.json"
SAMPLE_PER_COMM = 200          # 每社区最多采样多少条红点
RANDOM_SEED     = 42

SEVERITY = {
    "HOMICIDE": 10, "KIDNAPPING": 9, "HUMAN TRAFFICKING": 9,
    "ROBBERY": 8, "SEX OFFENSE": 8, "CRIM SEXUAL ASSAULT": 8,
    "ASSAULT": 7, "BATTERY": 7, "STALKING": 7,
    "BURGLARY": 6, "ARSON": 6,
    "MOTOR VEHICLE THEFT": 5, "WEAPONS VIOLATION": 5, "INTIMIDATION": 5,
    "THEFT": 4, "DECEPTIVE PRACTICE": 4,
    "CRIMINAL DAMAGE": 3, "OFFENSE INVOLVING CHILDREN": 3,
    "CRIMINAL TRESPASS": 2, "LIQUOR LAW VIOLATION": 2,
    "NARCOTICS": 2, "OTHER NARCOTIC VIOLATION": 2,
}

COMM_NAMES = {
    1:"Rogers Park",2:"West Ridge",3:"Uptown",4:"Lincoln Square",5:"North Center",
    6:"Lake View",7:"Lincoln Park",8:"Near North Side",9:"Edison Park",10:"Norwood Park",
    11:"Jefferson Park",12:"Forest Glen",13:"North Park",14:"Albany Park",15:"Portage Park",
    16:"Irving Park",17:"Dunning",18:"Montclare",19:"Belmont Cragin",20:"Hermosa",
    21:"Avondale",22:"Logan Square",23:"Humboldt Park",24:"West Town",25:"Austin",
    26:"West Garfield Park",27:"East Garfield Park",28:"Near West Side",29:"North Lawndale",
    30:"South Lawndale",31:"Lower West Side",32:"Loop",33:"Near South Side",34:"Armour Square",
    35:"Douglas",36:"Oakland",37:"Fuller Park",38:"Grand Boulevard",39:"Kenwood",
    40:"Washington Park",41:"Hyde Park",42:"Woodlawn",43:"South Shore",44:"Chatham",
    45:"Avalon Park",46:"South Chicago",47:"Burnside",48:"Calumet Heights",49:"Roseland",
    50:"Pullman",51:"South Deering",52:"East Side",53:"West Pullman",54:"Riverdale",
    55:"Hegewisch",56:"Garfield Ridge",57:"Archer Heights",58:"Brighton Park",
    59:"McKinley Park",60:"Bridgeport",61:"New City",62:"West Elsdon",63:"Gage Park",
    64:"Clearing",65:"West Lawn",66:"Chicago Lawn",67:"West Englewood",68:"Englewood",
    69:"Greater Grand Crossing",70:"Ashburn",71:"Auburn Gresham",72:"Beverly",
    73:"Washington Heights",74:"Mount Greenwood",75:"Morgan Park",76:"O'Hare",77:"Edgewater",
}

DIST_NAMES = {
    "001":"Central","002":"Wentworth","003":"Grand Crossing","004":"South Chicago",
    "005":"Calumet","006":"Gresham","007":"Englewood","008":"Chicago Lawn",
    "009":"Deering","010":"Ogden","011":"Harrison","012":"Near West",
    "014":"Shakespeare","015":"Austin","016":"Jefferson Park","017":"Albany Park",
    "018":"Near North","019":"Town Hall","020":"Morgan Park","022":"Morgan Park",
    "024":"Rogers Park","025":"Grand Central",
}

def parse_date(s):
    """Return (year, month, hour) or None."""
    try:
        dt = datetime.strptime(s, "%m/%d/%Y %I:%M:%S %p")
        return dt.year, dt.month, dt.hour
    except Exception:
        return None

def main():
    random.seed(RANDOM_SEED)

    # Accumulators
    by_year   = defaultdict(int)
    by_month  = defaultdict(int)
    by_hour   = defaultdict(int)
    by_type   = defaultdict(int)

    # ym_type[year][month][type] = count
    ym_type = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    # yh_type[year][hour][type] = count  (Year↔Hour cross-filtering)
    yh_type = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    # mh_type[month][hour][type] = count  (Month↔Hour cross-filtering)
    mh_type = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    # hour_type[hour][type] = count  (Hour滑块 → Crime Type联动)
    hour_type = defaultdict(lambda: defaultdict(int))

    # comm_type[comm][type] = count
    comm_type = defaultdict(lambda: defaultdict(int))

    # comm_totals[comm] = total crimes
    comm_totals = defaultdict(int)

    # dist_year[dist][year], dist_month[dist][month], etc.
    dist_year  = defaultdict(lambda: defaultdict(int))
    dist_month = defaultdict(lambda: defaultdict(int))
    dist_hour  = defaultdict(lambda: defaultdict(int))
    dist_type  = defaultdict(lambda: defaultdict(int))
    dist_comms = defaultdict(set)
    dist_total = defaultdict(int)

    # reservoir sampling per community for sample_points
    reservoirs = defaultdict(list)   # comm -> list of dicts
    counts_per_comm = defaultdict(int)

    total_rows = 0

    print("Reading CSV...", flush=True)
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1
            if total_rows % 500000 == 0:
                print(f"  {total_rows:,} rows processed...", flush=True)

            # Parse date
            parsed = parse_date(row.get("Date",""))
            if not parsed:
                continue
            year, month, hour = parsed

            ctype = (row.get("Primary Type") or "OTHER").strip().upper()
            dist  = (row.get("District") or "").strip().lstrip("0") or None
            comm_raw = row.get("Community Area","").strip()
            comm  = int(comm_raw) if comm_raw.isdigit() else None
            lat_s = row.get("Latitude","").strip()
            lng_s = row.get("Longitude","").strip()

            # Global aggregations
            by_year[str(year)]  += 1
            by_month[str(month)] += 1
            by_hour[str(hour)]   += 1
            by_type[ctype]       += 1

            # YM_TYPE cube
            ym_type[str(year)][str(month)][ctype] += 1

            # YH_TYPE cube (Year↔Hour cross-filtering)
            yh_type[str(year)][str(hour)][ctype] += 1

            # MH_TYPE cube (Month↔Hour cross-filtering)
            mh_type[str(month)][str(hour)][ctype] += 1

            # HOUR_TYPE (Hour滑块→Crime Type联动)
            hour_type[str(hour)][ctype] += 1

            # Community aggregations
            if comm:
                comm_type[str(comm)][ctype] += 1
                comm_totals[str(comm)]       += 1

            # District aggregations
            if dist:
                dist_year[dist][str(year)]   += 1
                dist_month[dist][str(month)] += 1
                dist_hour[dist][str(hour)]   += 1
                dist_type[dist][ctype]        += 1
                dist_total[dist]              += 1
                if comm:
                    dist_comms[dist].add(comm)

            # Reservoir sampling for red dots
            if comm and lat_s and lng_s:
                try:
                    lat = round(float(lat_s), 5)
                    lng = round(float(lng_s), 5)
                except ValueError:
                    lat = lng = None

                if lat and lng:
                    counts_per_comm[str(comm)] += 1
                    k = counts_per_comm[str(comm)]
                    entry = {
                        "date": row.get("Date",""),
                        "lat": lat,
                        "lng": lng,
                        "type": ctype,
                        "desc": (row.get("Description") or "").strip(),
                        "loc":  (row.get("Location Description") or "").strip(),
                        "block":(row.get("Block") or "").strip()
                    }
                    if len(reservoirs[str(comm)]) < SAMPLE_PER_COMM:
                        reservoirs[str(comm)].append(entry)
                    else:
                        j = random.randint(0, k - 1)
                        if j < SAMPLE_PER_COMM:
                            reservoirs[str(comm)][j] = entry

    print(f"Done reading. Total rows: {total_rows:,}", flush=True)

    # ---- Compute community risk scores ----
    print("Computing community risk scores...", flush=True)
    comm_raw_scores = {}
    for comm_id, types in comm_type.items():
        raw = sum(SEVERITY.get(t, 1) * c for t, c in types.items())
        comm_raw_scores[comm_id] = raw

    # Quantile normalisation to [0, 1]
    scores_sorted = sorted(comm_raw_scores.values())
    n = len(scores_sorted)
    def quantile_rank(v):
        # percentile rank
        idx = scores_sorted.index(v) if v in scores_sorted else 0
        return round(idx / max(n - 1, 1), 4)

    comm_risk = {}
    for comm_id, raw in comm_raw_scores.items():
        cid = int(comm_id)
        comm_risk[comm_id] = {
            "score": quantile_rank(raw),
            "raw":   raw,
            "name":  COMM_NAMES.get(cid, f"Community {cid}"),
            "total": comm_totals.get(comm_id, 0)
        }

    # ---- Build dist_agg ----
    print("Building dist_agg...", flush=True)
    dist_agg = {}
    for dist in dist_year:
        dist_agg[dist] = {
            "name":     DIST_NAMES.get(str(dist).zfill(3), f"District {dist}"),
            "by_year":  dict(dist_year[dist]),
            "by_month": dict(dist_month[dist]),
            "by_hour":  dict(dist_hour[dist]),
            "by_type":  dict(sorted(dist_type[dist].items(), key=lambda x:-x[1])),
            "comm_ids": sorted(dist_comms[dist]),
            "total":    dist_total[dist]
        }

    # ---- Compute district risk scores (Level 0 heatmap) ----
    print("Computing district risk scores...", flush=True)
    # dist_risk_raw[dist] = Σ severity(type) × count(type) in this district
    dist_raw_scores = {}
    for dist, types in dist_type.items():
        raw = sum(SEVERITY.get(t, 1) * c for t, c in types.items())
        dist_raw_scores[dist] = raw

    # Quantile normalisation across 25 districts
    dscores = sorted(dist_raw_scores.values())
    dn = len(dscores)
    def dquantile_rank(v):
        idx = dscores.index(v) if v in dscores else 0
        return round(idx / max(dn - 1, 1), 4)

    dist_risk = {}
    for dist, raw in dist_raw_scores.items():
        dist_risk[dist] = {
            "score": dquantile_rank(raw),
            "raw":   raw,
            "name":  DIST_NAMES.get(str(dist).zfill(3), f"District {dist}"),
            "total": dist_total[dist]
        }

    # ---- Finalize by_type sorted ----
    by_type_sorted = dict(sorted(by_type.items(), key=lambda x:-x[1]))

    # ---- Assemble output ----
    print("Assembling output...", flush=True)
    out = {
        "meta": {
            "total": total_rows,
            "built_at": datetime.now().isoformat(timespec="seconds"),
            "sample_per_comm": SAMPLE_PER_COMM
        },
        "by_year":  dict(sorted(by_year.items())),
        "by_month": dict(sorted(by_month.items(), key=lambda x: int(x[0]))),
        "by_hour":  dict(sorted(by_hour.items(),  key=lambda x: int(x[0]))),
        "by_type":  by_type_sorted,
        "ym_type":  {y: {m: dict(t) for m,t in mv.items()} for y,mv in ym_type.items()},
        "yh_type":  {y: {h: dict(t) for h,t in hv.items()} for y,hv in yh_type.items()},
        "mh_type":  {m: {h: dict(t) for h,t in hv.items()} for m,hv in mh_type.items()},
        "hour_type": {h: dict(t) for h,t in hour_type.items()},
        "comm_type": {c: dict(t) for c,t in comm_type.items()},
        "comm_risk": comm_risk,
        "dist_risk": dist_risk,
        "dist_agg":  dist_agg,
        "sample_points": dict(reservoirs)
    }

    print(f"Writing {OUT_FILE}...", flush=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",",":"))

    size_mb = round(__import__("os").path.getsize(OUT_FILE) / 1e6, 1)
    print(f"Done! {OUT_FILE} = {size_mb} MB", flush=True)

    # Print summary
    print("\n=== Summary ===")
    print(f"Total records: {total_rows:,}")
    print(f"Years: {sorted(by_year.keys())[:3]} ... {sorted(by_year.keys())[-3:]}")
    print(f"Crime types: {len(by_type)}")
    print(f"Communities: {len(comm_type)}")
    print(f"Districts: {len(dist_agg)}")
    print(f"Sample points: {sum(len(v) for v in reservoirs.values()):,} total")
    print(f"New: dist_risk ({len(dist_risk)} districts), yh_type, mh_type, hour_type added")

if __name__ == "__main__":
    main()
