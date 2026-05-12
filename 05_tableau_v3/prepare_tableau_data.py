"""
prepare_tableau_data.py — Generate 5 clean CSVs for Tableau Dashboard v3

Reads pipeline outputs (processed/ + 04_visualization/data/) and produces:
  1. grid_master.csv      — 1,947 H3 cells with demand + constraint scores
  2. scenario_hubs.csv    — 64 scenarios × 6 hubs (384 rows)
  3. scenario_routes.csv  — 18,718 routes × 2 path points (~37,436 rows)
  4. scenario_lookup.csv  — 64 scenario definitions
  5. charts_bundle.csv    — 8 chart datasets stacked (~175 rows)

All CSVs use UTF-8-sig encoding (BOM) for Tableau Korean text compatibility.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent          # 1_Seongnam_reset/
PROC = ROOT / "processed"
VIZ  = ROOT / "04_visualization" / "data"
OUT  = Path(__file__).resolve().parent / "data"
OUT.mkdir(exist_ok=True)

ENC = "utf-8-sig"   # BOM for Tableau

def rjson(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. grid_master.csv
# ═══════════════════════════════════════════════════════════════════════════════
print("─── 1. Building grid_master.csv ───")

# Primary grid: lat/lon + demand scores
grid_pts = pd.read_csv(PROC / "h3_dashboard_points.csv")
grid_pts.rename(columns={"centroid_lat": "lat", "centroid_lon": "lon"}, inplace=True)

# Constraint scores
cg = pd.read_csv(PROC / "constraint_grid_v2.csv")
cg_cols = {
    "score_airspace":       cg.get("score_airspace",       cg.get("airspace_score")),
    "score_obstacle":       cg.get("score_obstacle",       cg.get("obstacle_score")),
    "score_noise":          cg.get("score_noise_proxy",    cg.get("noise_sensitive_score")),
    "score_robot":          cg.get("score_robot",          cg.get("robot_access_score")),
    "score_weather":        cg.get("score_weather",        cg.get("weather_score")),
    "hard_exclusion":       cg.get("hard_exclusion_flag",  pd.Series(False, index=cg.index)),
}
cg_clean = pd.DataFrame({"h3_index": cg["h3_index"], **cg_cols})

# Delivery zones
dz = pd.read_csv(PROC / "delivery_zones.csv")
dz_clean = dz[["h3_index", "delivery_zone", "drone_score", "robot_score"]].copy()

# Merge all three on h3_index
grid = grid_pts.merge(cg_clean, on="h3_index", how="left")
grid = grid.merge(dz_clean, on="h3_index", how="left")

# Select final columns
GRID_COLS = [
    "h3_index", "lat", "lon", "ADM_NM", "GU_NM",
    "demand_b2b", "demand_b2c", "demand_cv", "Ds", "demand_grade",
    "score_airspace", "score_obstacle", "score_noise", "score_robot", "score_weather",
    "delivery_zone", "drone_score", "robot_score", "hard_exclusion",
]
# Keep only columns that exist
grid_out = grid[[c for c in GRID_COLS if c in grid.columns]].copy()

# Fill NaN scores with 0.5 (safe neutral)
for sc in ["score_airspace", "score_obstacle", "score_noise", "score_robot", "score_weather"]:
    if sc in grid_out.columns:
        grid_out[sc] = grid_out[sc].fillna(0.5).clip(0, 1)

# Fill NaN demand with 0
for dc in ["demand_b2b", "demand_b2c", "demand_cv"]:
    if dc in grid_out.columns:
        grid_out[dc] = grid_out[dc].fillna(0).clip(0, 1)

grid_out["hard_exclusion"] = grid_out.get("hard_exclusion", False).fillna(False).astype(bool)
grid_out["delivery_zone"] = grid_out["delivery_zone"].fillna("부적합")

grid_out.to_csv(OUT / "grid_master.csv", index=False, encoding=ENC)
print(f"  grid_master.csv: {len(grid_out)} rows × {len(grid_out.columns)} cols")
print(f"  lat range: {grid_out['lat'].min():.4f} ~ {grid_out['lat'].max():.4f}")
print(f"  null lat: {grid_out['lat'].isna().sum()}, null lon: {grid_out['lon'].isna().sum()}")
print(f"  score_airspace: {grid_out['score_airspace'].min():.3f} ~ {grid_out['score_airspace'].max():.3f}")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. scenario_hubs.csv
# ═══════════════════════════════════════════════════════════════════════════════
print("\n─── 2. Building scenario_hubs.csv ───")

hubs_raw = rjson(VIZ / "dashboard_hubs_by_scenario.json")
hubs_by_scen = hubs_raw["hubs_by_scenario"]
meta_raw = rjson(VIZ / "all_hubs_metadata.json")

hub_rows = []
for scen_id, hub_list in hubs_by_scen.items():
    for h in hub_list:
        lot_id = str(h["lot_id"])
        m = meta_raw.get(lot_id, {})
        hub_rows.append({
            "scenario_id":   scen_id,
            "lot_id":        lot_id,
            "lot_name":      m.get("lot_name", lot_id),
            "lat":           m.get("lat", 0),
            "lon":           m.get("lon", 0),
            "gu":            m.get("gu", ""),
            "dong":          m.get("dong", ""),
            "rank":          h.get("rank", 0),
            "cover_n":       h.get("cover_n", 0),
            "cover_ds":      round(h.get("cover_ds", 0), 4),
            "route_fi":      round(h.get("route_fi", 0), 5),
            "delivery_zone": m.get("delivery_zone", "부적합"),
            "explanation":   h.get("explanation", ""),
        })

hubs_df = pd.DataFrame(hub_rows)
hubs_df.to_csv(OUT / "scenario_hubs.csv", index=False, encoding=ENC)
print(f"  scenario_hubs.csv: {len(hubs_df)} rows × {len(hubs_df.columns)} cols")
print(f"  Scenarios: {hubs_df['scenario_id'].nunique()}")
print(f"  S001 hubs: {len(hubs_df[hubs_df['scenario_id']=='S001'])}")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. scenario_routes.csv
# ═══════════════════════════════════════════════════════════════════════════════
print("\n─── 3. Building scenario_routes.csv ───")

routes_raw = rjson(VIZ / "dashboard_routes_by_scenario.json")
routes_by_scen = routes_raw["routes_by_scenario"]

# We also need hub rank per scenario for the hub_rank column
hub_rank_lookup = {}
for scen_id, hub_list in hubs_by_scen.items():
    for h in hub_list:
        hub_rank_lookup[(scen_id, str(h["lot_id"]))] = h.get("rank", 0)

route_rows = []
route_counter = 0
for scen_id, route_list in routes_by_scen.items():
    for r in route_list:
        route_counter += 1
        rid = f"R{route_counter:06d}"
        lot_id = str(r.get("lot_id", ""))
        h_rank = hub_rank_lookup.get((scen_id, lot_id), 0)

        # Point 1: hub endpoint
        route_rows.append({
            "scenario_id":  scen_id,
            "route_id":     rid,
            "lot_id":       lot_id,
            "dong":         r.get("dong", ""),
            "path_order":   1,
            "route_lat":    r.get("h_lat", 0),
            "route_lon":    r.get("h_lon", 0),
            "approval":     bool(r.get("approval", False)),
            "drone_t":      round(r.get("drone_t", 0), 2),
            "time_saving":  round(r.get("ts", 0), 2),
            "co2_saving":   round(r.get("co2", 0), 1),
            "hub_rank":     h_rank,
        })
        # Point 2: target endpoint
        route_rows.append({
            "scenario_id":  scen_id,
            "route_id":     rid,
            "lot_id":       lot_id,
            "dong":         r.get("dong", ""),
            "path_order":   2,
            "route_lat":    r.get("t_lat", 0),
            "route_lon":    r.get("t_lon", 0),
            "approval":     bool(r.get("approval", False)),
            "drone_t":      round(r.get("drone_t", 0), 2),
            "time_saving":  round(r.get("ts", 0), 2),
            "co2_saving":   round(r.get("co2", 0), 1),
            "hub_rank":     h_rank,
        })

routes_df = pd.DataFrame(route_rows)
routes_df.to_csv(OUT / "scenario_routes.csv", index=False, encoding=ENC)

n_unique_routes = routes_df["route_id"].nunique()
s001_routes = routes_df[routes_df["scenario_id"] == "S001"]["route_id"].nunique()
print(f"  scenario_routes.csv: {len(routes_df)} rows × {len(routes_df.columns)} cols")
print(f"  Unique routes: {n_unique_routes}")
print(f"  S001 routes: {s001_routes}")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. scenario_lookup.csv
# ═══════════════════════════════════════════════════════════════════════════════
print("\n─── 4. Building scenario_lookup.csv ───")

scen_raw = rjson(VIZ / "dashboard_scenarios.json")
scenarios = scen_raw["scenarios"]

lookup_rows = []
for s in scenarios:
    lookup_rows.append({
        "scenario_id":   s["scenario_id"],
        "use_airspace":  s["use_airspace"],
        "use_obstacle":  s["use_obstacle"],
        "use_noise":     s["use_noise"],
        "use_robot":     s["use_robot"],
        "use_weather":   s["use_weather"],
        "airspace_mode": s["airspace_mode"],
    })

lookup_df = pd.DataFrame(lookup_rows)
lookup_df.to_csv(OUT / "scenario_lookup.csv", index=False, encoding=ENC)
print(f"  scenario_lookup.csv: {len(lookup_df)} rows")

# Verify bit-pattern formula
print("  Verifying scenario ID formula...")
mismatches = 0
for _, row in lookup_df.iterrows():
    combo = (
        (0 if row["use_weather"] else 1)
        + (0 if row["use_robot"] else 2)
        + (0 if row["use_noise"] else 4)
        + (0 if row["use_obstacle"] else 8)
        + (0 if row["use_airspace"] else 16)
    )
    mode_offset = 1 if row["airspace_mode"] == "strict_exclusion" else 0
    predicted = f"S{combo * 2 + mode_offset + 1:03d}"
    if predicted != row["scenario_id"]:
        print(f"    MISMATCH: {row['scenario_id']} != {predicted}")
        mismatches += 1
print(f"  Formula mismatches: {mismatches} / {len(lookup_df)}")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. charts_bundle.csv
# ═══════════════════════════════════════════════════════════════════════════════
print("\n─── 5. Building charts_bundle.csv ───")

eda = rjson(VIZ / "dashboard_eda.json")

bundle_rows = []

# 5a: dong_top15
for item in eda.get("dong_top15", []):
    bundle_rows.append({
        "chart_id": "dong_top15",
        "rank":     item.get("rank", 0),
        "label":    item.get("label", item.get("ADM_NM", "")),
        "GU_NM":    item.get("GU_NM", ""),
        "value1":   item.get("composite", 0),
        "value2":   item.get("total_demand_Ds", 0),
        "value3":   item.get("n_cells", 0),
        "category": "",
    })

# 5b: hourly
for item in eda.get("hourly", []):
    bundle_rows.append({
        "chart_id": "hourly",
        "rank":     item.get("hour_code", 0),
        "label":    item.get("hour_label", ""),
        "GU_NM":    "",
        "value1":   item.get("dw_total", 0),
        "value2":   None,
        "value3":   None,
        "category": item.get("period", ""),
    })

# 5c: mode_compare
for i, item in enumerate(eda.get("mode_compare", [])):
    bundle_rows.append({
        "chart_id": "mode_compare",
        "rank":     i + 1,
        "label":    item.get("label", item.get("assigned_lot_name", "")),
        "GU_NM":    "",
        "value1":   item.get("drone", 0),
        "value2":   item.get("motorcycle", 0),
        "value3":   item.get("delta", 0),
        "category": "",
    })

# 5d: esg
for item in eda.get("esg", []):
    bundle_rows.append({
        "chart_id": "esg",
        "rank":     item.get("rank", 0),
        "label":    item.get("assigned_lot_name", ""),
        "GU_NM":    "",
        "value1":   item.get("e_index", 0),
        "value2":   item.get("n_routes", 0),
        "value3":   None,
        "category": "",
    })

# 5e: dong_zone_pct — filter to 드론우선 only, sorted desc by pct
dzp_items = [d for d in eda.get("dong_zone_pct", [])
             if "드론" in str(d.get("delivery_zone", ""))]
dzp_items.sort(key=lambda x: x.get("pct", 0), reverse=True)
for i, item in enumerate(dzp_items[:15]):
    bundle_rows.append({
        "chart_id": "dong_zone_pct",
        "rank":     i + 1,
        "label":    item.get("ADM_NM", ""),
        "GU_NM":    item.get("GU_NM", ""),
        "value1":   item.get("pct", 0),
        "value2":   item.get("n_cells", 0),
        "value3":   None,
        "category": item.get("delivery_zone", ""),
    })

# 5f: b2b_top15
for item in eda.get("b2b_top15", []):
    bundle_rows.append({
        "chart_id": "b2b",
        "rank":     item.get("rank", 0),
        "label":    item.get("label", item.get("ADM_NM", "")),
        "GU_NM":    item.get("GU_NM", ""),
        "value1":   item.get("score", 0),
        "value2":   item.get("n_cells", 0),
        "value3":   None,
        "category": "",
    })

# 5g: b2c_top15
for item in eda.get("b2c_top15", []):
    bundle_rows.append({
        "chart_id": "b2c",
        "rank":     item.get("rank", 0),
        "label":    item.get("label", item.get("ADM_NM", "")),
        "GU_NM":    item.get("GU_NM", ""),
        "value1":   item.get("score", 0),
        "value2":   item.get("n_cells", 0),
        "value3":   None,
        "category": "",
    })

# 5h: robot_top15
for item in eda.get("robot_top15", []):
    bundle_rows.append({
        "chart_id": "robot",
        "rank":     item.get("rank", 0),
        "label":    item.get("label", item.get("ADM_NM", "")),
        "GU_NM":    item.get("GU_NM", ""),
        "value1":   item.get("score", 0),
        "value2":   item.get("n_cells", 0),
        "value3":   None,
        "category": "",
    })

bundle_df = pd.DataFrame(bundle_rows)
bundle_df.to_csv(OUT / "charts_bundle.csv", index=False, encoding=ENC)
print(f"  charts_bundle.csv: {len(bundle_df)} rows")
for cid in bundle_df["chart_id"].unique():
    n = len(bundle_df[bundle_df["chart_id"] == cid])
    print(f"    {cid}: {n} rows")


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("TABLEAU DATA PREPARATION COMPLETE")
print("=" * 60)
print(f"Output directory: {OUT}")
print()
for f in sorted(OUT.glob("*.csv")):
    df = pd.read_csv(f, encoding=ENC, nrows=0)
    size = f.stat().st_size
    nrows = sum(1 for _ in open(f, encoding=ENC)) - 1
    print(f"  {f.name:30s}  {nrows:>7,} rows  {len(df.columns):>3} cols  {size//1024:>5} KB")

print()
print("Next: Open Tableau Desktop and follow TABLEAU_BUILD_GUIDE.md")
