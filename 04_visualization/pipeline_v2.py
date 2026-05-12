"""
pipeline_v2.py  (v3 — full per-scenario greedy hub selection)
=============================================================
Generates all CSV/JSON files for the dashboard.

Key changes from v2:
  T5   – Scenario availability fixed: approval mode never inherits hard_exclusion_flag.
           strict mode only excludes when airspace IS active AND score_air < 0.1.
  T6-8 – Real greedy max-coverage hub selection for all 64 scenarios.
           Outputs 384-row final_hubs_by_scenario.csv (64 × 6).
  T10  – New compact JSON format:
           all_hubs_metadata.json   – all 171 candidate lots (lat/lon + scores)
           dashboard_hubs_by_scenario.json   – per-scenario 6 selected lot_ids + ranks
           dashboard_routes_by_scenario.json – per-scenario compact route records
           (coordinates resolved client-side from ALL_HUBS + GRID lookups)

Run: python 04_visualization/pipeline_v2.py
"""
import sys, json, itertools, warnings
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import h3

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT  = Path(__file__).parent.parent
PROC  = ROOT / "processed"
TD    = ROOT / "03_tableau_workspace_v2" / "tableau_data"
TDV2  = ROOT / "03_tableau_workspace_v2" / "tableau_data_v2"
VDATA = ROOT / "04_visualization" / "data"
VDATA.mkdir(parents=True, exist_ok=True)

def rcsv(name_or_path, **kw):
    p = PROC / name_or_path if isinstance(name_or_path, str) else name_or_path
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return pd.read_csv(p, encoding=enc, **kw)
        except (UnicodeDecodeError, LookupError):
            continue
    return pd.read_csv(p, encoding="latin-1", **kw)

def wcsv(df, path, **kw):
    df.to_csv(path, index=False, encoding="utf-8-sig", **kw)
    print(f"  ✓ wrote {Path(path).name}  ({len(df)} rows)")

def wjson(obj, path):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, default=str), encoding="utf-8")
    sz = Path(path).stat().st_size // 1024
    print(f"  ✓ wrote {Path(path).name}  ({sz} KB)")

def norm01(s):
    lo, hi = s.min(), s.max()
    return (s - lo) / (hi - lo) if hi > lo else pd.Series(0.5, index=s.index)

def safe_f(v, d=0.0):
    try: return round(float(v), 5)
    except: return d


# ═══════════════════════════════════════════════════════════════════════════
# T2/T3 – H3 base grid + refactored demand scores
# ═══════════════════════════════════════════════════════════════════════════
print("\n── T2/T3  H3 base grid ──────────────────────────────────────────")

dg = rcsv("demand_grid.csv")
dg.rename(columns={"lat": "centroid_lat", "lon": "centroid_lon"}, inplace=True)
dg["h3_res"] = 9
cell_set = set(dg["h3_index"])
def _is_edge(c):
    try: return int(any(n not in cell_set for n in h3.grid_disk(c, 1) - {c}))
    except: return 0
dg["is_edge_cell"] = dg["h3_index"].apply(_is_edge)
dg["coverage_ratio"] = dg["is_edge_cell"].apply(lambda x: 0.75 if x else 1.0)
dg["h3_marker_radius_px"] = 4
dg["b2b_score"]        = dg["Od"].clip(0, 1)
dg["commercial_score"] = dg["Fp"].clip(0, 1)
dg["b2c_score"]        = dg["Cc"].clip(0, 1)
dg["sales_score"]      = dg["Tp"].clip(0, 1)
dg["base_h3_score"]    = 0.25 * (dg["b2b_score"] + dg["commercial_score"] + dg["b2c_score"] + dg["sales_score"])
dg["Ds"] = dg["base_h3_score"]

# ── New demand layers (from NB08 상권활력지수 upgrade) ────────────────────────
dg["demand_b2b"] = dg.get("demand_b2b", dg["Od"]).clip(0, 1)
dg["demand_b2c"] = dg.get("demand_b2c", dg["Od"]).clip(0, 1)
dg["demand_cv"]  = dg.get("demand_cv", pd.Series(0.0, index=dg.index)).clip(0, 1)

H3_COLS = ["h3_index","h3_res","centroid_lat","centroid_lon","ADM_NM","GU_NM","CSV_ADMI_CD",
           "coverage_ratio","is_edge_cell","h3_marker_radius_px",
           "b2b_score","commercial_score","b2c_score","sales_score","base_h3_score",
           "Ds","Od","Cc","demand_grade","demand_rank","demand_percentile",
           "delivery_demand_index","flow_pop_index"]
h3_base = dg[[c for c in H3_COLS if c in dg.columns]].copy()
wcsv(h3_base, PROC / "h3_base_grid.csv")

DASH_COLS = ["h3_index","centroid_lat","centroid_lon","ADM_NM","GU_NM",
             "Ds","Od","Cc","b2b_score","commercial_score","b2c_score","sales_score",
             "demand_b2b","demand_b2c","demand_cv",
             "demand_grade","h3_marker_radius_px","is_edge_cell","coverage_ratio"]
h3_dash = dg[[c for c in DASH_COLS if c in dg.columns]].copy()
wcsv(h3_dash, PROC / "h3_dashboard_points.csv")

try:
    from shapely.geometry import Polygon
    def hex_poly(c):
        return Polygon([(lon, lat) for lat, lon in h3.cell_to_boundary(c)])
    h3_base["geometry"] = h3_base["h3_index"].apply(hex_poly)
    gpd.GeoDataFrame(h3_base, geometry="geometry", crs="EPSG:4326").to_file(
        PROC / "h3_base_grid.gpkg", driver="GPKG")
    print(f"  ✓ wrote h3_base_grid.gpkg")
except Exception as e:
    print(f"  ⚠ gpkg: {e}")

print(f"  ✓ T2/T3 — {len(dg)} cells, Ds=[{dg['Ds'].min():.3f},{dg['Ds'].max():.3f}]")


# ═══════════════════════════════════════════════════════════════════════════
# T4 – Constraint scoring (5 atomic layers)
# ═══════════════════════════════════════════════════════════════════════════
print("\n── T4  Constraint layer refactor ────────────────────────────────")

cg = rcsv("constraint_grid.csv")
cg["airspace_score"]        = cg["score_airspace"]
cg["obstacle_score"]        = cg["score_obstacle"]
if "score_terrain" in cg.columns:
    cg["noise_sensitive_score"] = (0.7*cg["score_noise_proxy"].fillna(0.5) +
                                    0.3*cg["score_terrain"].fillna(0.5)).clip(0, 1)
else:
    cg["noise_sensitive_score"] = cg["score_noise_proxy"].fillna(0.5)
cg["robot_access_score"]    = cg.get("score_robot",   pd.Series(0.5, index=cg.index)).fillna(0.5)
cg["weather_score"]         = cg.get("score_weather", pd.Series(0.5, index=cg.index)).fillna(0.5)
cg["noise_method"]          = "noise_proxy×0.7 + terrain_slope×0.3"
if "constraint_note" not in cg.columns: cg["constraint_note"] = ""

def _excl_reason(row):
    rs = []
    if row.get("hard_exclusion_flag", False):
        if row.get("airspace_score", 1.0) < 0.2: rs.append("관제권내비행금지")
        if row.get("obstacle_score",  1.0) < 0.2: rs.append("장애물밀집")
        if not rs: rs.append("비행불가구역")
    return "|".join(rs)
cg["hard_exclusion_reasons"] = cg.apply(_excl_reason, axis=1)

# Compat aliases
cg["score_airspace"]    = cg["airspace_score"]
cg["score_obstacle"]    = cg["obstacle_score"]
cg["score_noise_proxy"] = cg["noise_sensitive_score"]
cg["score_robot"]       = cg["robot_access_score"]
cg["score_weather"]     = cg["weather_score"]
cg["constraint_score"]  = (cg["airspace_score"] + cg["obstacle_score"] +
                           cg["noise_sensitive_score"] + cg["robot_access_score"] +
                           cg["weather_score"]) / 5.0
wcsv(cg, PROC / "constraint_grid_v2.csv")
print("  ✓ T4 done")


# ═══════════════════════════════════════════════════════════════════════════
# T5 – Constraint scenarios (64 combos) — FIXED availability logic
# ═══════════════════════════════════════════════════════════════════════════
print("\n── T5  Constraint scenarios ─────────────────────────────────────")

LAYER_COLS = ["airspace_score","obstacle_score","noise_sensitive_score",
              "robot_access_score","weather_score"]
LAYER_KR   = ["공역","장애물","소음","로봇접근","기상"]
AIRSPACE_MODES = [("approval_required_allowed","승인허용"),
                  ("strict_exclusion","엄격제외")]

# Merge Ds + layer scores into one frame
cg_full = cg.merge(dg[["h3_index","Ds","base_h3_score","demand_grade"]], on="h3_index", how="left")

# --- FIXED: airspace score = 0 means "in control zone" (needs approval), NOT "permanently banned"
# Permanently banned cells are rare edge cases; we treat hard_exclusion_flag conservatively.
# In approval mode: ALL cells are potentially available (approval covers airspace).
# In strict mode:  cells with airspace active AND score_air < 0.1 are excluded.
PERM_EXCL_SCORE = 0.05   # score_air below this = genuinely hard-excluded (e.g. military zones)

def compute_cell_scenario(row, bits, am_code):
    scores = []
    for col, used in zip(LAYER_COLS, bits):
        if used:
            s = row[col]
            if col == "airspace_score" and am_code == "strict_exclusion":
                # In strict mode: airspace zones with near-zero score are excluded
                scores.append(0.0 if s < 0.1 else s)
            else:
                # In approval mode: airspace zones are flyable (with approval)
                # score still affects constraint_score but does NOT exclude the cell
                scores.append(max(s, 0.15) if col == "airspace_score" else s)
        else:
            scores.append(1.0)   # layer inactive → no constraint
    return float(np.mean(scores))

def cell_available(row, scen_cs, bits, am_code):
    # Strict mode + airspace active: exclude genuine no-fly cells
    if am_code == "strict_exclusion" and bits[0] and row["airspace_score"] < 0.1:
        return False
    # Score threshold: must have some flyable score
    return scen_cs >= 0.25

scenario_rows, h3_scenario_rows = [], []
sid = 1

# Pre-vectorise: build numpy arrays for speed
air_arr   = cg_full["airspace_score"].values
obs_arr   = cg_full["obstacle_score"].values
noise_arr = cg_full["noise_sensitive_score"].values
robot_arr = cg_full["robot_access_score"].values
wx_arr    = cg_full["weather_score"].values
ds_arr    = cg_full["base_h3_score"].values
h3_idx    = cg_full["h3_index"].values
excl_air  = air_arr < 0.1   # boolean mask for genuine airspace exclusion

for bits in itertools.product([True, False], repeat=5):
    for am_code, am_kr in AIRSPACE_MODES:
        active_kr = [LAYER_KR[i] for i, b in enumerate(bits) if b]
        label = "+".join(active_kr) if active_kr else "제약없음"
        label += f" ({am_kr})"
        scenario_id = f"S{sid:03d}"; sid += 1
        use_flags = dict(zip(
            ["use_airspace","use_obstacle","use_noise","use_robot","use_weather"], bits))

        # Compute constraint score per cell
        b_air, b_obs, b_noise, b_robot, b_wx = bits
        strict = am_code == "strict_exclusion"

        # Air component: approval mode floors at 0.15 to avoid excluding approval-mode cells
        if b_air:
            if strict:
                air_c = np.where(excl_air, 0.0, air_arr)
            else:
                air_c = np.maximum(air_arr, 0.15)
        else:
            air_c = np.ones(len(cg_full))

        obs_c   = obs_arr   if b_obs   else np.ones(len(cg_full))
        noise_c = noise_arr if b_noise else np.ones(len(cg_full))
        robot_c = robot_arr if b_robot else np.ones(len(cg_full))
        wx_c    = wx_arr    if b_wx    else np.ones(len(cg_full))

        scen_cs = (air_c + obs_c + noise_c + robot_c + wx_c) / 5.0

        # Availability: strict+airspace active → exclude excl_air cells
        if strict and b_air:
            avail = (~excl_air) & (scen_cs >= 0.25)
        else:
            avail = scen_cs >= 0.25   # all other scenarios: score threshold only

        scen_h3 = ds_arr * scen_cs

        scenario_rows.append({
            "scenario_id": scenario_id,
            "scenario_label_kr": label,
            **use_flags,
            "airspace_mode": am_code,
            "scenario_constraint_score": round(float(scen_cs.mean()), 4),
            "scenario_h3_score": round(float(scen_h3.mean()), 4),
            "n_available_cells": int(avail.sum()),
            "n_excluded_cells":  int((~avail).sum()),
        })

        for i in range(len(cg_full)):
            h3_scenario_rows.append({
                "scenario_id": scenario_id,
                "h3_index": h3_idx[i],
                "scenario_constraint_score": round(float(scen_cs[i]), 4),
                "scenario_h3_score": round(float(scen_h3[i]), 4),
                "scenario_available_flag": bool(avail[i]),
                "scenario_exclusion_reason":
                    "관제권엄격제외" if (strict and b_air and excl_air[i]) else "",
            })

scenarios_df = pd.DataFrame(scenario_rows)
h3_scen_df   = pd.DataFrame(h3_scenario_rows)
wcsv(scenarios_df, PROC / "constraint_scenarios.csv")
wcsv(h3_scen_df,   PROC / "h3_scenario_scores.csv")

# Validate
S_all_approval = scenarios_df[scenarios_df["use_airspace"] & scenarios_df["use_obstacle"] &
                               scenarios_df["use_noise"] & scenarios_df["use_robot"] &
                               scenarios_df["use_weather"] &
                               (scenarios_df["airspace_mode"]=="approval_required_allowed")]
S_none = scenarios_df[~scenarios_df["use_airspace"] & ~scenarios_df["use_obstacle"] &
                       ~scenarios_df["use_noise"] & ~scenarios_df["use_robot"] &
                       ~scenarios_df["use_weather"] &
                       (scenarios_df["airspace_mode"]=="approval_required_allowed")]
S_strict = scenarios_df[scenarios_df["use_airspace"] & scenarios_df["use_obstacle"] &
                         scenarios_df["use_noise"] & scenarios_df["use_robot"] &
                         scenarios_df["use_weather"] &
                         (scenarios_df["airspace_mode"]=="strict_exclusion")]

DEFAULT_SCENARIO = S_all_approval.iloc[0]["scenario_id"]
print(f"  All-ON approval  n_available={S_all_approval.iloc[0]['n_available_cells']} (want >29)")
print(f"  No-constraint    n_available={S_none.iloc[0]['n_available_cells']} (want all cells)")
print(f"  All-ON strict    n_available={S_strict.iloc[0]['n_available_cells']} (want ~29)")
print(f"  ✓ T5 — {len(scenarios_df)} scenarios, default={DEFAULT_SCENARIO}")


# ═══════════════════════════════════════════════════════════════════════════
# T6-T8 – Per-scenario greedy hub selection (all 64 scenarios)
# ═══════════════════════════════════════════════════════════════════════════
print("\n── T6-T8  Per-scenario greedy hub selection ─────────────────────")

K_RECOMMENDED = 6

# ── Load inputs ───────────────────────────────────────────────────────────
# Candidate-H3 route data (all 171 lots × reachable H3 cells)
nb11 = rcsv("nb11_route_pairs.csv")
pk   = pd.read_parquet(PROC / "parking_candidates.parquet")
cs   = rcsv("candidate_site_summary.csv")

# Hub lat/lon from parking_candidates
pk_ll = pk[["lot_id","lot_name","lat","lon","parking_candidate_score"]].drop_duplicates("lot_id")

# Candidate meta (scores for weighting)
cand_meta = cs[["lot_id","lot_name","GU_NM","ADM_NM",
                  "candidate_score_for_ranking","candidate_score_primary",
                  "parking_site_score"]].copy()
cand_meta = cand_meta.merge(pk_ll[["lot_id","lat","lon","parking_candidate_score"]],
                             on="lot_id", how="left")

# H3 centroids for GeoJSON
h3_ll = h3_dash[["h3_index","centroid_lat","centroid_lon","ADM_NM","GU_NM"]].copy()
h3_ll.rename(columns={"ADM_NM":"target_ADM_NM","GU_NM":"target_GU_NM"}, inplace=True)

# nb11 essential columns
nb11_cols = {
    "lot_id": "lot_id", "lot_name": "lot_name",
    "target_h3_index": "h3_index",
    "target_ADM_NM": "target_ADM_NM", "target_GU_NM": "target_GU_NM",
    "drone_time_min": "drone_time_min",
    "route_mean_constraint_score": "route_constraint",
    "service_priority_score": "service_priority",
    "airspace_approval_required": "approval_required",
    "drone_direct_feasible_strict": "strict_feasible",
}
nb11_slim = nb11[[c for c in nb11_cols if c in nb11.columns]].rename(columns=nb11_cols)

# Normalise drone_time for scoring (shorter = better)
max_t = nb11_slim["drone_time_min"].max() if "drone_time_min" in nb11_slim else 30.0
nb11_slim["time_score"] = 1.0 - (nb11_slim["drone_time_min"] / (max_t + 1e-6)).clip(0, 1)

# Normalise parking score
cand_meta["park_norm"] = norm01(cand_meta["parking_candidate_score"].fillna(0.5))

# Coverage count score (how many H3 cells each lot can reach)
lot_cover_count = nb11_slim.groupby("lot_id")["h3_index"].nunique().rename("cover_count")
lot_cover_count = (lot_cover_count / lot_cover_count.max()).rename("cover_count_score")

# Build lot-level lookup for parking and coverage scores
cand_meta = cand_meta.merge(lot_cover_count.reset_index(), on="lot_id", how="left")
cand_meta["cover_count_score"] = cand_meta["cover_count_score"].fillna(0)
cand_meta.set_index("lot_id", inplace=True)

# H3 → scenario scores lookup (indexed h3_index × scenario_id)
print("  Building H3×scenario score matrix...")
h3_scen_pivot = h3_scen_df.pivot(index="h3_index", columns="scenario_id",
                                   values="scenario_h3_score").fillna(0)
h3_avail_pivot = h3_scen_df.pivot(index="h3_index", columns="scenario_id",
                                    values="scenario_available_flag").fillna(False)

# Precompute lot→H3 mapping
lot_h3_map = nb11_slim.groupby("lot_id").apply(
    lambda df: dict(zip(df["h3_index"], df["route_constraint"]))).to_dict()


def greedy_select(scen_id, k=K_RECOMMENDED):
    """Greedy maximum-coverage selection for one scenario."""
    # Available H3 cells in this scenario
    if scen_id not in h3_avail_pivot.columns:
        return []
    avail_mask = h3_avail_pivot[scen_id]
    avail_h3 = set(avail_mask[avail_mask].index)
    scen_scores = h3_scen_pivot[scen_id]   # h3 → scenario_h3_score

    # Filter nb11_slim to available cells only
    nb11_avail = nb11_slim[nb11_slim["h3_index"].isin(avail_h3)].copy()
    nb11_avail["scen_h3_score"] = nb11_avail["h3_index"].map(scen_scores).fillna(0)

    # Route score per edge: 0.45*scen_h3 + 0.25*route_constraint + 0.20*time + 0.10*(co2 proxy)
    nb11_avail["route_score"] = (
        0.45 * nb11_avail["scen_h3_score"] +
        0.25 * nb11_avail.get("route_constraint", pd.Series(0.5, index=nb11_avail.index)).fillna(0.5) +
        0.20 * nb11_avail.get("time_score", pd.Series(0.5, index=nb11_avail.index)).fillna(0.5) +
        0.10 * nb11_avail.get("service_priority", pd.Series(0.5, index=nb11_avail.index)).fillna(0.5)
    )

    # Greedy selection
    selected = []
    covered_h3 = set()

    # Pre-group by lot for speed
    lot_groups = {lid: grp for lid, grp in nb11_avail.groupby("lot_id")}
    all_lots = set(lot_groups.keys())
    selected_lots = set()

    for step in range(k):
        best_lot, best_gain, best_new_h3 = None, -1.0, set()
        for lid in all_lots - selected_lots:
            grp = lot_groups[lid]
            new_h3 = set(grp["h3_index"]) - covered_h3
            if not new_h3: continue
            gain = grp[grp["h3_index"].isin(new_h3)]["scen_h3_score"].sum()
            if gain > best_gain:
                best_gain, best_lot, best_new_h3 = gain, lid, new_h3

        if best_lot is None:
            # Coverage saturated — fill remaining slots from all_lots by parking score
            remaining = sorted(all_lots - selected_lots,
                               key=lambda lid: cand_meta.loc[lid, "park_norm"]
                               if (lid in cand_meta.index and "park_norm" in cand_meta.columns) else 0,
                               reverse=True)
            for lid in remaining:
                if len(selected) >= k:
                    break
                grp = lot_groups.get(lid)
                if grp is None:
                    # lot has no routes in this scenario — create a stub
                    grp = pd.DataFrame({"h3_index": [], "scen_h3_score": [],
                                        "route_score": []})
                selected.append((lid, set(), 0.0))
                selected_lots.add(lid)
            break
        selected.append((best_lot, best_new_h3, best_gain))
        selected_lots.add(best_lot)
        covered_h3 |= best_new_h3

    return selected


# ── Run for all 64 scenarios ──────────────────────────────────────────────
print("  Running greedy selection for 64 scenarios...")
hub_rows, assign_rows, route_rows = [], [], []

for _, scen_row in scenarios_df.iterrows():
    scen_id = scen_row["scenario_id"]
    am      = scen_row["airspace_mode"]
    label   = scen_row["scenario_label_kr"]

    selections = greedy_select(scen_id, K_RECOMMENDED)

    for rank, (lot_id, covered_h3, gain) in enumerate(selections, 1):
        # Hub meta
        meta = cand_meta.loc[lot_id] if lot_id in cand_meta.index else {}
        lot_name   = str(meta.get("lot_name", lot_id))
        lat        = safe_f(meta.get("lat"))
        lon        = safe_f(meta.get("lon"))
        gu         = str(meta.get("GU_NM", ""))
        dong       = str(meta.get("ADM_NM", ""))
        cand_score = safe_f(meta.get("candidate_score_primary", 0))
        park_score = safe_f(meta.get("park_norm", 0))

        # Coverage stats
        cover_n  = len(covered_h3)
        cover_ds = safe_f(sum(h3_scen_pivot.loc[h, scen_id]
                              for h in covered_h3 if h in h3_scen_pivot.index))

        # Route feasibility (mean route_constraint for this lot's available routes)
        lot_routes = nb11_slim[(nb11_slim["lot_id"] == lot_id) &
                                (nb11_slim["h3_index"].isin(covered_h3))]
        route_fi  = safe_f(lot_routes["route_constraint"].mean() if len(lot_routes) else 0.5)
        approval_req_count = int(lot_routes["approval_required"].sum()) if "approval_required" in lot_routes else 0

        expl = f"수요커버 Ds={cover_ds:.2f} | {cover_n}셀 | 선정순위#{rank} | 경로타당성{route_fi:.0%}"

        hub_rows.append({
            "scenario_id": scen_id,
            "scenario_label_kr": label,
            "airspace_mode": am,
            "lot_id": lot_id,
            "lot_name": lot_name,
            "lat": lat, "lon": lon,
            "site_GU_NM": gu, "site_ADM_NM": dong,
            "selected_order": rank,
            "assigned_Ds_sum": cover_ds,
            "coverage_cell_count": cover_n,
            "route_feasibility": route_fi,
            "approval_required_routes": approval_req_count,
            "candidate_score": cand_score,
            "hub_explanation": expl,
        })

        # Assignments: each covered H3 → this hub
        for h3_idx_val in covered_h3:
            h3_meta = h3_ll[h3_ll["h3_index"] == h3_idx_val]
            t_dong = str(h3_meta["target_ADM_NM"].iloc[0]) if len(h3_meta) else ""
            t_gu   = str(h3_meta["target_GU_NM"].iloc[0])  if len(h3_meta) else ""
            t_lat  = safe_f(h3_meta["centroid_lat"].iloc[0]) if len(h3_meta) else 0
            t_lon  = safe_f(h3_meta["centroid_lon"].iloc[0]) if len(h3_meta) else 0
            scen_h3 = safe_f(h3_scen_pivot.loc[h3_idx_val, scen_id]
                              if h3_idx_val in h3_scen_pivot.index else 0)

            # Route data for this edge
            edge = lot_routes[lot_routes["h3_index"] == h3_idx_val]
            drone_t  = safe_f(edge["drone_time_min"].iloc[0]) if len(edge) else 0
            approval = bool(edge["approval_required"].iloc[0]) if len(edge) else False
            strict_f = bool(edge["strict_feasible"].iloc[0]) if (len(edge) and "strict_feasible" in edge) else False
            r_const  = safe_f(edge["route_constraint"].iloc[0]) if (len(edge) and "route_constraint" in edge) else 0.5
            time_sav = round(max(0, 25 - drone_t), 2)
            co2_sav  = round(time_sav * 45, 1)

            assign_rows.append({
                "scenario_id": scen_id,
                "lot_id": lot_id, "lot_name": lot_name,
                "hub_lat": lat, "hub_lon": lon,
                "target_h3_index": h3_idx_val,
                "target_ADM_NM": t_dong, "target_GU_NM": t_gu,
                "target_lat": t_lat, "target_lon": t_lon,
                "scenario_h3_score": scen_h3,
                "drone_time_min": drone_t,
                "time_saving_min": time_sav,
                "co2_saving_g": co2_sav,
                "airspace_approval_required": approval,
                "drone_direct_feasible_strict": strict_f,
                "route_constraint_score": r_const,
                "hub_rank": rank,
            })

print(f"  Hub rows: {len(hub_rows)}  (want 64×6={64*6})")

hubs_scen_df  = pd.DataFrame(hub_rows)
assign_scen_df = pd.DataFrame(assign_rows)

wcsv(hubs_scen_df,   PROC / "final_hubs_by_scenario.csv")
wcsv(assign_scen_df, PROC / "hub_service_assignments_by_scenario.csv")

# Coverage by hub-dong
hub_dong = assign_scen_df.groupby(
    ["scenario_id","lot_id","lot_name","target_ADM_NM"]
).agg(h3_cell_count=("target_h3_index","nunique"),
      total_Ds=("scenario_h3_score","sum"),
      mean_drone_min=("drone_time_min","mean")).reset_index()
wcsv(hub_dong, PROC / "coverage_by_hub_dong.csv")

print(f"  ✓ T6-T8 done — {len(hubs_scen_df)} hub rows / {len(assign_scen_df)} assignment rows")


# ═══════════════════════════════════════════════════════════════════════════
# T9 – EDA outputs
# ═══════════════════════════════════════════════════════════════════════════
print("\n── T9  EDA outputs ──────────────────────────────────────────────")

dong_rank = (dg.groupby(["GU_NM","ADM_NM"])
             .agg(composite=("base_h3_score","mean"), total_demand_Ds=("Ds","sum"),
                  b2b_score=("b2b_score","mean"), b2c_score=("b2c_score","mean"),
                  n_cells=("h3_index","nunique"))
             .reset_index().sort_values("composite", ascending=False).reset_index(drop=True))
dong_rank["rank"] = dong_rank.index + 1
dong_rank["label"] = dong_rank["ADM_NM"]
wcsv(dong_rank.head(15), PROC / "dong_top15_v2.csv")

try:
    hourly_raw = pd.read_parquet(PROC / "card_hourly_demand.parquet")
    cnt_col = "total_del_cnt" if "total_del_cnt" in hourly_raw.columns else "cnt"
    if cnt_col in hourly_raw.columns:
        hourly = (hourly_raw.groupby(["hour_code","hour_label"], dropna=False)
                  .agg(dw_total=(cnt_col,"sum")).reset_index().sort_values("hour_code"))
        PERIOD = {"01":"새벽/심야","02":"오전","03":"오전","04":"점심",
                  "05":"오후","06":"저녁/야간","07":"저녁/야간","08":"새벽/심야"}
        hourly["period"] = hourly["hour_code"].astype(str).map(PERIOD).fillna("기타")
        wcsv(hourly, PROC / "hourly_pattern_v2.csv")
except Exception as e:
    print(f"  ⚠ hourly: {e}")

try:
    nb13 = rcsv("nb13_route_comparison.csv")
    mode_df = nb13[["assigned_lot_name","target_ADM_NM","drone_time_min","moto_time_est_min",
                     "time_saving_min","time_saving_pct","drone_faster","co2_saving_g",
                     "airspace_approval_required","robot_handoff_feasible"]].copy()
    mode_df.rename(columns={"moto_time_est_min":"motorcycle","drone_time_min":"drone",
                             "time_saving_min":"delta","target_ADM_NM":"label"}, inplace=True)
    wcsv(mode_df, PROC / "mode_compare_v2.csv")
except Exception as e:
    print(f"  ⚠ mode compare: {e}")

try:
    esg = rcsv("nb14_esg_efficiency_index.csv")
    if "esg_index" in esg.columns:
        esg_hub = (esg.groupby("assigned_lot_name")
                   .agg(e_index=("esg_index","mean"),n_routes=("target_h3_index","nunique"))
                   .reset_index().sort_values("e_index", ascending=False).reset_index(drop=True))
        esg_hub["scenario_label_kr"] = "기본시나리오"
        esg_hub["rank"] = esg_hub.index + 1
        wcsv(esg_hub, PROC / "esg_efficiency_v2.csv")
except Exception as e:
    print(f"  ⚠ esg: {e}")

for score_col, fn, title in [("b2b_score","b2b_top15_v2.csv","B2B기업활동"),
                               ("b2c_score","b2c_top15_v2.csv","B2C소비수요")]:
    top = (dg.groupby(["GU_NM","ADM_NM"]).agg(score=(score_col,"mean"),n_cells=("h3_index","nunique"))
           .reset_index().sort_values("score",ascending=False).head(15).reset_index(drop=True))
    top["rank"] = top.index+1; top["kr_title"] = title; top["label"] = top["ADM_NM"]
    wcsv(top, PROC / fn)

try:
    rag = rcsv("robot_access_grid.csv")
    rob = (rag.groupby(["GU_NM","ADM_NM"]).agg(score=("Ra","mean"),n_cells=("h3_index","nunique"))
           .reset_index().sort_values("score",ascending=False).head(15).reset_index(drop=True))
    rob["rank"] = rob.index+1; rob["kr_title"] = "로봇배송용이성"; rob["label"] = rob["ADM_NM"]
    wcsv(rob, PROC / "robot_top15_v2.csv")
except Exception as e:
    print(f"  ⚠ robot: {e}")

print("  ✓ T9 done")


# ═══════════════════════════════════════════════════════════════════════════
# T10 – Dashboard JSON files (new compact scenario-keyed format)
# ═══════════════════════════════════════════════════════════════════════════
print("\n── T10  Dashboard JSON ──────────────────────────────────────────")

# ── dashboard_h3_points.json (unchanged) ──────────────────────────────────
h3_json = [{k: (round(v,5) if isinstance(v,float) else v)
            for k,v in rec.items()} for rec in h3_dash.to_dict(orient="records")]
wjson(h3_json, VDATA / "dashboard_h3_points.json")

# ── all_hubs_metadata.json (171 candidate lots) ────────────────────────────
# Load delivery_zone per lot from final_candidate_sites (NB10 output)
try:
    _fcs = rcsv("final_candidate_sites.csv")
    _lot_zone = dict(zip(_fcs["lot_id"].astype(str), _fcs["delivery_zone"].astype(str)))
except Exception:
    _lot_zone = {}

all_hubs = {}
for lot_id, row in cand_meta.iterrows():
    all_hubs[str(lot_id)] = {
        "lot_name": str(row.get("lot_name","")),
        "lat":  safe_f(row.get("lat")),
        "lon":  safe_f(row.get("lon")),
        "gu":   str(row.get("GU_NM","")),
        "dong": str(row.get("ADM_NM","")),
        "score": safe_f(row.get("candidate_score_primary",0)),
        "delivery_zone": _lot_zone.get(str(lot_id), "부적합"),
    }
wjson(all_hubs, VDATA / "all_hubs_metadata.json")

# ── dashboard_hubs_by_scenario.json ───────────────────────────────────────
hubs_by_scen = {}
for scen_id, grp in hubs_scen_df.groupby("scenario_id"):
    hubs_by_scen[scen_id] = [
        {
            "lot_id":       str(r["lot_id"]),
            "rank":         int(r["selected_order"]),
            "cover_n":      int(r["coverage_cell_count"]),
            "cover_ds":     safe_f(r["assigned_Ds_sum"]),
            "route_fi":     safe_f(r["route_feasibility"]),
            "explanation":  str(r["hub_explanation"]),
        }
        for _, r in grp.sort_values("selected_order").iterrows()
    ]
wjson({"default_scenario": DEFAULT_SCENARIO, "hubs_by_scenario": hubs_by_scen},
      VDATA / "dashboard_hubs_by_scenario.json")

# ── dashboard_routes_by_scenario.json (compact) ───────────────────────────
# Format: {scenario_id: [{lot_id, h3_index, approval, drone_t, time_save, co2_save}, ...]}
routes_by_scen = {}
for scen_id, grp in assign_scen_df.groupby("scenario_id"):
    routes_by_scen[scen_id] = [
        {
            "lot_id":   str(r["lot_id"]),
            "h3":       str(r["target_h3_index"]),
            "h_lat":    safe_f(r["hub_lat"]),
            "h_lon":    safe_f(r["hub_lon"]),
            "t_lat":    safe_f(r["target_lat"]),
            "t_lon":    safe_f(r["target_lon"]),
            "dong":     str(r["target_ADM_NM"]),
            "approval": bool(r["airspace_approval_required"]),
            "drone_t":  safe_f(r["drone_time_min"]),
            "ts":       safe_f(r["time_saving_min"]),
            "co2":      safe_f(r["co2_saving_g"]),
            "rank":     int(r["hub_rank"]),
        }
        for _, r in grp.iterrows()
    ]
wjson({"default_scenario": DEFAULT_SCENARIO, "routes_by_scenario": routes_by_scen},
      VDATA / "dashboard_routes_by_scenario.json")

# ── dashboard_scenarios.json ───────────────────────────────────────────────
scen_records = []
for _, r in scenarios_df.iterrows():
    rec = r.to_dict()
    for k,v in rec.items():
        if isinstance(v, (np.bool_,)): rec[k] = bool(v)
        elif isinstance(v, float): rec[k] = round(v, 4)
    scen_records.append(rec)
wjson({"default_scenario": DEFAULT_SCENARIO, "scenarios": scen_records},
      VDATA / "dashboard_scenarios.json")

# ── dashboard_eda.json ─────────────────────────────────────────────────────
eda = {}
eda["dong_top15"] = dong_rank.head(15)[["rank","label","ADM_NM","GU_NM",
                                         "composite","total_demand_Ds","n_cells"]].to_dict(orient="records")
for fn, key in [("hourly_pattern_v2.csv","hourly"),("mode_compare_v2.csv","mode_compare"),
                ("esg_efficiency_v2.csv","esg"),("b2b_top15_v2.csv","b2b_top15"),
                ("b2c_top15_v2.csv","b2c_top15"),("robot_top15_v2.csv","robot_top15")]:
    try:
        df_ = pd.read_csv(PROC/fn, encoding="utf-8-sig")
        eda[key] = [{k:(round(v,4) if isinstance(v,float) else v)
                     for k,v in r.items()} for r in df_.to_dict(orient="records")]
    except Exception:
        eda[key] = []
try:
    dz = rcsv("delivery_zones.csv")
    dong_zone = dz.groupby(["GU_NM","ADM_NM","delivery_zone"]).size().reset_index(name="n_cells")
    tot = dong_zone.groupby("ADM_NM")["n_cells"].sum().rename("total")
    dong_zone = dong_zone.merge(tot, on="ADM_NM")
    dong_zone["pct"] = (dong_zone["n_cells"]/dong_zone["total"]*100).round(1)
    eda["dong_zone_pct"] = dong_zone.to_dict(orient="records")
except Exception:
    eda["dong_zone_pct"] = []
wjson(eda, VDATA / "dashboard_eda.json")

print(f"\n✅ pipeline_v2.py complete")
print(f"   {len(scenarios_df)} scenarios | {len(hubs_scen_df)} hub rows | {len(assign_scen_df)} assignment rows")
print(f"   JSON files in: {VDATA}")
