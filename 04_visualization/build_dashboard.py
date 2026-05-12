"""
build_dashboard.py  (v2 — pipeline_v2 compatible)
==================================================
Generates a self-contained dashboard.html for 1_Seongnam_reset.

Data sources (all from pipeline_v2.py outputs):
  04_visualization/data/dashboard_h3_points.json   – 283 H3 cells
  04_visualization/data/dashboard_hubs.json         – 6 selected hubs
  04_visualization/data/dashboard_routes.json       – 77 route GeoJSON
  04_visualization/data/dashboard_eda.json          – EDA tables
  processed/constraint_grid_v2.csv                  – 5 atomic layer scores
  processed/constraint_scenarios.csv                – 64 scenario metadata
  03_tableau_workspace_v2/tableau_data_v2/          – KPI / narrative CSVs

Key changes vs v1:
  * H3 markers: FIXED radius = 6 (was variable 4 + Ds*4)
  * Constraint toggles compute scenario scores in JS (no server needed)
  * All data read from pipeline_v2 outputs, not old tableau CSVs
  * UTF-8 throughout
"""
import sys, json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd, numpy as np

ROOT  = Path(__file__).parent.parent
PROC  = ROOT / "processed"
TDV2  = ROOT / "03_tableau_workspace_v2" / "tableau_data_v2"
VDATA = Path(__file__).parent / "data"
OUT   = Path(__file__).parent / "dashboard.html"

def rj(name):
    p = VDATA / name
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def rcsv(p):
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return pd.read_csv(p, encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return pd.read_csv(p, encoding="latin-1")

def rtdv2(name):
    p = TDV2 / f"{name}.csv"
    if p.exists():
        return rcsv(p)
    return pd.DataFrame()

# ── Load data ──────────────────────────────────────────────────────────────
print("Loading data from pipeline_v2 outputs...")

h3_raw    = rj("dashboard_h3_points.json")          # list of dicts
eda       = rj("dashboard_eda.json")                # dict of lists

# New scenario-aware data
_hubs_json    = rj("dashboard_hubs_by_scenario.json")
_routes_json  = rj("dashboard_routes_by_scenario.json")
_scen_json    = rj("dashboard_scenarios.json")
_all_hubs_raw = rj("all_hubs_metadata.json")         # lot_id → meta dict

HUBS_BY_SCENARIO  = _hubs_json["hubs_by_scenario"]
ROUTES_BY_SCENARIO= _routes_json["routes_by_scenario"]
DEFAULT_SCEN_ID   = _hubs_json.get("default_scenario", "S001")
SCENARIOS_LIST    = _scen_json.get("scenarios", [])

# Constraint layer scores (5 atomic)
cg = rcsv(PROC / "constraint_grid_v2.csv")
cg_map = {r["h3_index"]: r for _, r in cg.iterrows()}

# Scenario metadata
scen_df = rcsv(PROC / "constraint_scenarios.csv")
DEFAULT_SCENARIO = "S001"   # all-on + approval_required_allowed

# delivery_zones for display (from the processed data)
try:
    dz = rcsv(PROC / "delivery_zones.csv")
    dz_map = {r["h3_index"]: r.get("delivery_zone","부적합")
              for _, r in dz.iterrows()}
except Exception:
    dz_map = {}

# KPI / narrative from TDV2 if available; otherwise synthesise
kpi_df   = rtdv2("kpi_cards")
narr_df  = rtdv2("narrative_callouts")

print(f"  H3 cells : {len(h3_raw)}")
print(f"  Scenarios: {len(SCENARIOS_LIST)}")
print(f"  Default  : {DEFAULT_SCEN_ID} — {len(HUBS_BY_SCENARIO.get(DEFAULT_SCEN_ID,[]))} hubs / {len(ROUTES_BY_SCENARIO.get(DEFAULT_SCEN_ID,[]))} routes")

# ── Build GRID (H3 cells with constraint scores) ───────────────────────────
def _safe_f(v, d=0.0):
    try: return round(float(v), 5)
    except: return d

GRID = []
for g in h3_raw:
    idx = g["h3_index"]
    cr  = cg_map.get(idx, {})
    GRID.append({
        "h3_index": idx,
        "lat": _safe_f(g.get("centroid_lat")),
        "lon": _safe_f(g.get("centroid_lon")),
        "ADM_NM": g.get("ADM_NM",""),
        "GU_NM":  g.get("GU_NM",""),
        "Ds":  _safe_f(g.get("Ds", g.get("base_h3_score", 0))),
        "Od":  _safe_f(g.get("Od", g.get("b2b_score", 0))),
        "Cc":  _safe_f(g.get("Cc", g.get("b2c_score", 0))),
        "b2b": _safe_f(g.get("b2b_score", g.get("Od", 0))),
        "b2c": _safe_f(g.get("b2c_score", g.get("Cc", 0))),
        "commercial": _safe_f(g.get("commercial_score", g.get("Fp", 0))),
        "demand_grade": g.get("demand_grade",""),
        "delivery_zone": dz_map.get(idx, g.get("delivery_zone","부적합")),
        # 5 constraint layer scores (1=no constraint, 0=fully blocked)
        "score_air":    _safe_f(cr.get("airspace_score",       cr.get("score_airspace", 0.5))),
        "score_obs":    _safe_f(cr.get("obstacle_score",       cr.get("score_obstacle", 0.5))),
        "score_noise":  _safe_f(cr.get("noise_sensitive_score",cr.get("score_noise_proxy", 0.5))),
        "score_robot":  _safe_f(cr.get("robot_access_score",   cr.get("score_robot", 0.5))),
        "score_wx":     _safe_f(cr.get("weather_score",        cr.get("score_weather", 0.5))),
        "constraint_score": _safe_f(cr.get("constraint_score", 0.5)),
        "hard_excl":    bool(cr.get("hard_exclusion_flag", False)),
        "excl_reasons": str(cr.get("hard_exclusion_reasons","")),
        # Demand layers for toggle-based scoring
        "demand_b2b": _safe_f(g.get("demand_b2b", g.get("Od", 0))),
        "demand_b2c": _safe_f(g.get("demand_b2c", g.get("Od", 0))),
        "demand_cv":  _safe_f(g.get("demand_cv", 0)),
    })

# ── Build ALL_HUBS (lot_id → meta) ─────────────────────────────────────────
ALL_HUBS = {}
for lot_id, meta in _all_hubs_raw.items():
    ALL_HUBS[str(lot_id)] = {
        "lot_name": str(meta.get("lot_name", lot_id)),
        "lat":  _safe_f(meta.get("lat")),
        "lon":  _safe_f(meta.get("lon")),
        "gu":   str(meta.get("gu","")),
        "dong": str(meta.get("dong","")),
        "score": _safe_f(meta.get("score", 0)),
        "delivery_zone": str(meta.get("delivery_zone", "부적합")),
    }

# Convenience: default scenario hubs/routes for KPI
_def_hubs   = HUBS_BY_SCENARIO.get(DEFAULT_SCEN_ID, [])
_def_routes = ROUTES_BY_SCENARIO.get(DEFAULT_SCEN_ID, [])

# ── EDA: slim for embedding ────────────────────────────────────────────────
def safe_eda(key, cols):
    rows = eda.get(key, [])
    if not rows: return []
    out = []
    for r in rows:
        rec = {}
        for c in cols:
            v = r.get(c)
            if isinstance(v, float): v = round(v, 4)
            rec[c] = v
        out.append(rec)
    return out

DONG_T15 = safe_eda("dong_top15",  ["rank","label","ADM_NM","GU_NM","composite","total_demand_Ds","n_cells"])
HOURLY   = safe_eda("hourly",      ["hour_code","hour_label","period","dw_total"])
MODE     = safe_eda("mode_compare",["label","drone","motorcycle","delta","pct_drone_faster"])
ESG      = safe_eda("esg",         ["assigned_lot_name","e_index","n_routes","scenario_label_kr"])
B2B      = safe_eda("b2b_top15",   ["rank","label","ADM_NM","GU_NM","score"])
B2C      = safe_eda("b2c_top15",   ["rank","label","ADM_NM","GU_NM","score"])
ROBOT    = safe_eda("robot_top15", ["rank","label","ADM_NM","GU_NM","score"])
DONG_ZP  = safe_eda("dong_zone_pct",["ADM_NM","GU_NM","delivery_zone","pct"])

# ── KPIs ───────────────────────────────────────────────────────────────────
if len(kpi_df):
    # kpi_cards.csv uses 'value_raw' (not 'metric_value')
    val_col = "value_raw" if "value_raw" in kpi_df.columns else "metric_value"
    kmap = {r["metric_name"]:r for _, r in kpi_df.iterrows()} if "metric_name" in kpi_df.columns else {}
    def km(n): return kmap.get(n, {})
    def kv(n, default=0.0): return _safe_f(km(n).get(val_col, default))
    # hub_count/route_count are dynamic (updated per-scenario in JS), use default for init
    _ts_vals  = [r.get("ts",0)  for r in _def_routes if r.get("ts",0)]
    _co2_vals = [r.get("co2",0) for r in _def_routes if r.get("co2",0)]
    KPI = {
        "hub_count":        int(len(_def_hubs)),
        "route_count":      int(len(_def_routes)),
        "median_save":      kv("median_time_saving_min") or
                            round(float(np.median(_ts_vals)) if _ts_vals else 0, 2),
        "co2_ton":          kv("base_co2_saved_ton") or
                            round(sum(_co2_vals) / 1e6, 2),
        "weather_pct":      round(kv("P_drone_weather_available") * 100, 1)
                            if kv("P_drone_weather_available") <= 1
                            else kv("P_drone_weather_available"),
        "drone_faster_pct": kv("pct_routes_drone_faster"),
        "esg_mean":         kv("esg_index_mean") or (
            round(float(np.mean([r["e_index"] for r in ESG if r.get("e_index")])), 3) if ESG else 0
        ),
    }
else:
    # Synthesise from default-scenario routes
    ts_vals  = [r.get("ts",0)  for r in _def_routes if r.get("ts",0)]
    co2_vals = [r.get("co2",0) for r in _def_routes if r.get("co2",0)]
    drone_pct = (sum(1 for r in _def_routes if r.get("ts",0) > 0) / max(len(_def_routes),1)) * 100
    esg_vals  = [r["e_index"] for r in ESG if r.get("e_index")] if ESG else []
    KPI = {
        "hub_count":     len(_def_hubs),
        "route_count":   len(_def_routes),
        "median_save":   round(float(np.median(ts_vals)) if ts_vals else 0, 2),
        "co2_ton":       round(sum(co2_vals) / 1e6, 2) if co2_vals else 0,
        "weather_pct":   85.0,
        "drone_faster_pct": round(drone_pct, 1),
        "esg_mean":      round(float(np.mean(esg_vals)) if esg_vals else 0.0, 3),
    }

# ── Narrative callouts ─────────────────────────────────────────────────────
if len(narr_df):
    NARR_COLS = ["slot","icon","title_kr","body_kr","accent"]
    NARR = narr_df[[c for c in NARR_COLS if c in narr_df.columns]].head(6).to_dict(orient="records")
else:
    NARR = [
        {"slot":1,"icon":"🚁","title_kr":"드론 배송 최적화","body_kr":f"성남시 {len(_def_hubs)}개 거점에서 {len(_def_routes)}개 배송 경로를 커버합니다.","accent":"#4fc3f7"},
        {"slot":2,"icon":"⚡","title_kr":"시간 절감","body_kr":f"중간 시간 절감 {KPI['median_save']:.1f}분, 드론 우세 {KPI['drone_faster_pct']:.0f}%","accent":"#53d769"},
        {"slot":3,"icon":"🌿","title_kr":"ESG 효과","body_kr":f"CO₂ 절감 {KPI['co2_ton']:.2f}t/연, ESG 지수 {KPI['esg_mean']:.3f}","accent":"#53d769"},
        {"slot":4,"icon":"🌤","title_kr":"기상 가용성","body_kr":f"드론 비행 가능 일수 약 {KPI['weather_pct']:.0f}%","accent":"#4fc3f7"},
        {"slot":5,"icon":"🗺","title_kr":"수요+제약 레이어","body_kr":"3개 수요 + 5개 제약 레이어 토글 → 수요×제약 연속 그라디언트","accent":"#ffb74d"},
        {"slot":6,"icon":"📍","title_kr":"H3 고해상도","body_kr":"~2,000개 H3(res9) 셀, 연속 빨강→초록 그라디언트 표시","accent":"#e94560"},
    ]

# ── JSON embedding helper ─────────────────────────────────────────────────
def emb(name, obj):
    return f"const {name} = {json.dumps(obj, ensure_ascii=False)};"

embedded = "\n".join([
    emb("KPI",               KPI),
    emb("GRID",              GRID),
    emb("ALL_HUBS",          ALL_HUBS),
    emb("HUBS_BY_SCENARIO",  HUBS_BY_SCENARIO),
    emb("ROUTES_BY_SCENARIO",ROUTES_BY_SCENARIO),
    emb("SCENARIOS",         SCENARIOS_LIST),
    f"const DEFAULT_SCENARIO = {json.dumps(DEFAULT_SCEN_ID)};",
    emb("DONG_T15", DONG_T15),
    emb("DONG_ZP",  DONG_ZP),
    emb("HOURLY",   HOURLY),
    emb("MODE",     MODE),
    emb("ESG",      ESG),
    emb("B2B",      B2B),
    emb("B2C",      B2C),
    emb("ROBOT",    ROBOT),
    emb("NARR",     NARR),
])

print(f"  Embedded data: {len(embedded)//1024} KB")
print(f"  GRID: {len(GRID)} | ALL_HUBS: {len(ALL_HUBS)} | Scenarios: {len(SCENARIOS_LIST)}")

# ═══════════════════════════════════════════════════════════════════════════
# HTML TEMPLATE
# ═══════════════════════════════════════════════════════════════════════════
HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>성남시 드론·로봇 배송 거점 최적 입지 분석 (Reset v2)</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Noto Sans KR',sans-serif; background:#0f0f1a; color:#e0e0e0; overflow-x:hidden; }
::-webkit-scrollbar { width:8px; }
::-webkit-scrollbar-track { background:#1a1a2e; }
::-webkit-scrollbar-thumb { background:#0f3460; border-radius:4px; }

.hero {
  background: linear-gradient(135deg, #0f3460 0%, #1a1a2e 50%, #16213e 100%);
  padding: 22px 40px 16px;
  border-bottom: 2px solid #0f3460;
}
.hero h1 { font-size:22px; font-weight:700; color:#4fc3f7; letter-spacing:-0.5px; }
.hero p  { font-size:13px; color:#8899aa; margin-top:4px; }
.hero .badge { display:inline-block; background:#e94560; color:#fff; font-size:11px; padding:3px 12px; border-radius:20px; margin-top:6px; font-weight:500; }
.hero .badge-ok { background:#1b5e3b; color:#53d769; border:1px solid #53d769;
  padding:5px 14px; border-radius:20px; font-size:12px; font-weight:600; margin-top:8px; margin-left:12px; }

/* KPI strip */
.kpi-strip { display:flex; gap:12px; padding:14px 40px; background:#0d0d1c; flex-wrap:wrap; }
.kpi-card {
  flex:1; min-width:120px;
  background:#16213e; border:1px solid #0f3460; border-radius:12px;
  padding:16px 14px; text-align:center;
}
.kpi-value { font-size:26px; font-weight:700; color:#4fc3f7; line-height:1; }
.kpi-unit  { font-size:10px; color:#8899aa; margin-top:2px; }
.kpi-label { font-size:11px; color:#aabbcc; margin-top:6px; font-weight:500; }

/* Main layout */
.main-grid {
  display:grid;
  grid-template-columns: 320px 1fr;
  gap:0; height:calc(100vh - 180px); min-height:520px;
}
.sidebar { background:#0d0d1c; border-right:1px solid #0f3460; overflow-y:auto; padding:12px; display:flex; flex-direction:column; gap:10px; }
.map-col  { position:relative; }
#map      { width:100%; height:100%; }

/* Panels */
.panel {
  background:#16213e; border:1px solid #0f3460; border-radius:12px;
  padding:14px 16px;
}
.panel-title { font-size:12px; font-weight:700; color:#4fc3f7; margin-bottom:10px; letter-spacing:0.5px; }
.layer-grid  { display:grid; grid-template-columns:1fr 1fr; gap:7px; }
.layer-toggle {
  display:flex; align-items:center; gap:7px; padding:7px 10px;
  background:#0f1928; border:1px solid #1a3a5c; border-radius:8px;
  cursor:pointer; transition:.15s;
}
.layer-toggle.active  { background:#0f3460; border-color:#4fc3f7; }
.layer-toggle input   { display:none; }
.layer-dot { width:10px; height:10px; border-radius:50%; flex-shrink:0; }
.layer-toggle span    { font-size:11px; font-weight:500; }

.formula-box { margin-top:8px; padding:7px 10px; background:#0a1020; border-radius:6px;
               border:1px solid #1a3a5c; font-size:10px; color:#7ba; line-height:1.5; }

/* Hub list */
.hub-item { padding:10px 12px; border-bottom:1px solid #1a2a3a; cursor:pointer; transition:.12s; }
.hub-item:hover { background:#1a2a3a; }
.hub-rank  { display:inline-block; background:#0f3460; color:#4fc3f7;
             font-size:11px; font-weight:700; padding:1px 6px; border-radius:4px; margin-right:6px; }
.hub-name  { font-weight:600; font-size:13px; display:inline; }
.hub-detail{ font-size:11px; color:#8899aa; margin-top:2px; }
.hub-coverage-bar { height:4px; border-radius:2px; margin-top:6px; background:#1a3a5c; overflow:hidden; }
.hub-coverage-fill{ height:100%; border-radius:2px;
                    background:linear-gradient(90deg,#53d769,#4fc3f7); transition:width .6s; }

/* Charts section */
.charts-section { padding:16px 24px 24px; background:#0a0a16; }
.chart-row       { display:flex; gap:14px; margin-top:14px; flex-wrap:wrap; }
.chart-card {
  flex:1; min-width:280px;
  background:linear-gradient(145deg,#16213e,#1a1a2e);
  border:1px solid #0f3460; border-radius:12px; padding:16px 18px;
}
.chart-title { font-size:12px; font-weight:700; color:#4fc3f7; margin-bottom:10px; }
.chart-div   { width:100%; height:220px; }

/* Narrative cards */
.narr-grid   { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:12px; padding:16px 24px; }
.narr-card   { background:#16213e; border-left:3px solid var(--accent,#4fc3f7);
               border-radius:8px; padding:14px; }
.narr-icon   { font-size:20px; margin-bottom:6px; }
.narr-title  { font-size:12px; font-weight:700; color:var(--accent,#4fc3f7); margin-bottom:4px; }
.narr-body   { font-size:11px; color:#aabbcc; line-height:1.5; }

.filter-badge { font-size:11px; color:#8899aa; margin-top:6px; }
.section-sep  { border:none; border-top:1px solid #1a2a3a; margin:0; }

/* Scenario score legend */
.scen-score-legend { display:flex; gap:6px; flex-wrap:wrap; margin-top:6px; }
.scen-dot { display:inline-flex; align-items:center; gap:4px; font-size:10px; }
.scen-circle { width:10px; height:10px; border-radius:50%; display:inline-block; }

/* Leaflet popup */
.leaflet-popup-content-wrapper { background:#16213e; color:#e0e0e0; border:1px solid #0f3460; border-radius:8px; }
.leaflet-popup-tip { background:#16213e; }
</style>
</head>
<body>

<!-- HERO -->
<div class="hero">
  <h1>🚁 성남시 드론·로봇 배송 거점 최적 입지 분석</h1>
  <p>성남시 ~2,000개 H3(res9) 셀 분석 · 3개 수요 + 5개 제약 레이어 토글 · 최적 거점 · 배송 경로</p>
  <span class="badge">BITAmin 16기 리셋 v2</span>
  <span class="badge-ok">✓ 수요×제약 연속 그라디언트</span>
</div>

<!-- KPI STRIP -->
<div class="kpi-strip">
  <div class="kpi-card">
    <div class="kpi-value" id="kv-hubs">—</div>
    <div class="kpi-unit">개소</div>
    <div class="kpi-label">최적 거점</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value" id="kv-routes">—</div>
    <div class="kpi-unit">경로</div>
    <div class="kpi-label">배송 경로</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value" id="kv-save">—</div>
    <div class="kpi-unit">분</div>
    <div class="kpi-label">중간 시간 절감</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value" id="kv-co2">—</div>
    <div class="kpi-unit">t/연</div>
    <div class="kpi-label">CO₂ 절감</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value" id="kv-wx">—</div>
    <div class="kpi-unit">%</div>
    <div class="kpi-label">기상 가용일</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value" id="kv-drone">—</div>
    <div class="kpi-unit">%</div>
    <div class="kpi-label">드론 우세 경로</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-value" id="kv-esg">—</div>
    <div class="kpi-unit">지수</div>
    <div class="kpi-label">ESG 효율 지수</div>
  </div>
</div>

<!-- MAIN GRID -->
<div class="main-grid">
  <!-- SIDEBAR -->
  <div class="sidebar">

    <!-- Demand layer toggles (FIRST) -->
    <div class="panel">
      <div class="panel-title">📊 수요 레이어</div>
      <div class="layer-grid">
        <label class="layer-toggle active" id="lt-b2b">
          <input type="checkbox" id="cb-b2b" checked onchange="applyScenario()">
          <div class="layer-dot" style="background:#ff6b35"></div>
          <span>B2B 기업수요</span>
        </label>
        <label class="layer-toggle active" id="lt-b2c">
          <input type="checkbox" id="cb-b2c" checked onchange="applyScenario()">
          <div class="layer-dot" style="background:#a855f7"></div>
          <span>B2C 소비수요</span>
        </label>
        <label class="layer-toggle active" id="lt-cv" style="grid-column:1/-1">
          <input type="checkbox" id="cb-cv" checked onchange="applyScenario()">
          <div class="layer-dot" style="background:#2dc653"></div>
          <span>상권활력지수</span>
        </label>
      </div>
      <div class="formula-box">
        수요점수 = 활성 수요 레이어 평균 (0~1)
      </div>
    </div>

    <!-- Constraint layer toggles (SECOND) -->
    <div class="panel">
      <div class="panel-title">⚙ 제약 레이어 (5개)</div>
      <div class="layer-grid">
        <label class="layer-toggle active" id="lt-air">
          <input type="checkbox" id="cb-air" checked onchange="applyScenario()">
          <div class="layer-dot" style="background:#e94560"></div>
          <span>공역</span>
        </label>
        <label class="layer-toggle active" id="lt-obs">
          <input type="checkbox" id="cb-obs" checked onchange="applyScenario()">
          <div class="layer-dot" style="background:#ff6b35"></div>
          <span>장애물</span>
        </label>
        <label class="layer-toggle active" id="lt-noise">
          <input type="checkbox" id="cb-noise" checked onchange="applyScenario()">
          <div class="layer-dot" style="background:#ffb74d"></div>
          <span>소음</span>
        </label>
        <label class="layer-toggle active" id="lt-robot">
          <input type="checkbox" id="cb-robot" checked onchange="applyScenario()">
          <div class="layer-dot" style="background:#42a5f5"></div>
          <span>로봇접근</span>
        </label>
        <label class="layer-toggle active" id="lt-wx" style="grid-column:1/-1">
          <input type="checkbox" id="cb-wx" checked onchange="applyScenario()">
          <div class="layer-dot" style="background:#7e57c2"></div>
          <span>기상</span>
        </label>
      </div>
      <div style="margin-top:8px;">
        <label style="font-size:11px;color:#aabbcc;">공역 모드: </label>
        <select id="airspace-mode" onchange="applyScenario()"
                style="background:#1a2a3a;color:#e0e0e0;border:1px solid #0f3460;border-radius:4px;font-size:11px;padding:2px 6px;">
          <option value="approval">승인허용</option>
          <option value="strict">엄격제외</option>
        </select>
      </div>
      <div class="formula-box">
        최종 적합성 = 수요점수 × 제약점수<br>
        셀 색상: 연속 그라디언트 (빨강→노랑→초록)
      </div>
      <!-- Gradient legend bar -->
      <div style="margin-top:8px;">
        <div style="display:flex;align-items:center;gap:6px;">
          <span style="font-size:10px;color:#aabbcc;">부적합</span>
          <div style="flex:1;height:10px;border-radius:5px;background:linear-gradient(90deg,hsl(0,75%,48%),hsl(60,75%,48%),hsl(120,75%,48%));"></div>
          <span style="font-size:10px;color:#aabbcc;">적합</span>
        </div>
      </div>
      <div class="filter-badge">활성 셀: <span id="filter-summary">—</span></div>
    </div>

    <!-- Hub list -->
    <div class="panel" style="padding:0; overflow:hidden;">
      <div class="panel-title" style="padding:12px 16px 0; margin:0;">
        📍 최적 거점
        <span id="hub-count-badge" style="background:#e9456033;color:#e94560;border-radius:10px;padding:1px 8px;font-size:12px;">6</span>
      </div>
      <div id="hub-list" style="max-height:220px; overflow-y:auto;"></div>
    </div>

  </div><!-- /sidebar -->

  <!-- MAP -->
  <div class="map-col">
    <div id="map" style="width:100%;height:100%;"></div>
  </div>
</div><!-- /main-grid -->

<hr class="section-sep">

<!-- NARRATIVE CARDS -->
<div class="narr-grid" id="narr-grid"></div>

<hr class="section-sep">

<!-- CHARTS -->
<div class="charts-section">
  <!-- Row 1 -->
  <div class="chart-row">
    <div class="chart-card" style="flex:2;">
      <div class="chart-title">📊 동별 종합 적합도 순위 (Top 15)</div>
      <div class="chart-div" id="chart-dong"></div>
    </div>
    <div class="chart-card" style="flex:1.5;">
      <div class="chart-title">🕐 시간대별 배송 수요 패턴</div>
      <div class="chart-div" id="chart-hourly"></div>
    </div>
  </div>
  <!-- Row 2 -->
  <div class="chart-row">
    <div class="chart-card">
      <div class="chart-title">🔄 배송 모드 비교 (드론 vs 오토바이)</div>
      <div class="chart-div" id="chart-mode"></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">⚡ ESG 효율 지수 (거점별)</div>
      <div class="chart-div" id="chart-esg"></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">📈 동별 드론우선 셀 비율 (%)</div>
      <div class="chart-div" id="chart-dong-zone"></div>
    </div>
  </div>
  <!-- Row 3 -->
  <div class="chart-row">
    <div class="chart-card">
      <div class="chart-title">🏢 B2B 기업 활동 지수 (Top 15)</div>
      <div class="chart-div" id="chart-b2b"></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">🛍 B2C 소비 수요 지수 (Top 15)</div>
      <div class="chart-div" id="chart-b2c"></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">🤖 로봇 배송 용이성 지수 (Top 15)</div>
      <div class="chart-div" id="chart-robot"></div>
    </div>
  </div>
</div>

<!-- EMBEDDED DATA -->
<script>
__EMBEDDED__
</script>

<!-- MAP & CHART LOGIC -->
<script>
// ════════════════════════════════════════════════════════
// KPI
// ════════════════════════════════════════════════════════
document.getElementById('kv-hubs').textContent   = KPI.hub_count;
document.getElementById('kv-routes').textContent = KPI.route_count;
document.getElementById('kv-save').textContent   = (KPI.median_save||0).toFixed(1);
document.getElementById('kv-co2').textContent    = (KPI.co2_ton||0).toFixed(2);
document.getElementById('kv-wx').textContent     = (KPI.weather_pct||0).toFixed(0);
document.getElementById('kv-drone').textContent  = (KPI.drone_faster_pct||0).toFixed(1);
document.getElementById('kv-esg').textContent    = (KPI.esg_mean||0).toFixed(3);

// ════════════════════════════════════════════════════════
// MAP
// ════════════════════════════════════════════════════════
const map = L.map('map', { zoomControl:true }).setView([37.42, 127.13], 12);
L.tileLayer('https://cartodb-basemaps-{s}.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png', {
  attribution:'© OpenStreetMap · CARTO Dark', subdomains:'abcd', maxZoom:19
}).addTo(map);

// Layer groups
const groupH3      = L.layerGroup().addTo(map);
const groupHubs    = L.layerGroup().addTo(map);   // always visible
const groupRoutes  = L.layerGroup().addTo(map);   // always visible

// Scenario state
let currentScenarioId = DEFAULT_SCENARIO;

// Build a lookup from (air,obs,noise,robot,wx,mode) → scenario_id
const scenLookup = {};
SCENARIOS.forEach(s => {
  const key = [s.use_airspace, s.use_obstacle, s.use_noise, s.use_robot, s.use_weather,
               s.airspace_mode].join('|');
  scenLookup[key] = s.scenario_id;
});

function findScenarioId() {
  const useAir   = document.getElementById('cb-air').checked;
  const useObs   = document.getElementById('cb-obs').checked;
  const useNoise = document.getElementById('cb-noise').checked;
  const useRobot = document.getElementById('cb-robot').checked;
  const useWx    = document.getElementById('cb-wx').checked;
  const strict   = document.getElementById('airspace-mode').value === 'strict';
  const amCode   = strict ? 'strict_exclusion' : 'approval_required_allowed';
  const key = [useAir, useObs, useNoise, useRobot, useWx, amCode].join('|');
  return scenLookup[key] || DEFAULT_SCENARIO;
}

function renderScenarioHubsRoutes(scenId) {
  groupHubs.clearLayers();
  groupRoutes.clearLayers();

  const hubList   = HUBS_BY_SCENARIO[scenId]   || [];
  const routeList = ROUTES_BY_SCENARIO[scenId] || [];

  // ── Draw hub markers (zone-based coloring) ─────────────────
  hubList.forEach(h => {
    const meta = ALL_HUBS[h.lot_id] || {};
    const lat = meta.lat, lon = meta.lon;
    if (!lat || !lon) return;
    const zone = meta.delivery_zone || '부적합';
    const hubCol = (zone === '드론우선')   ? '#2196F3' :
                   (zone === '하이브리드') ? '#9C27B0' : '#78909C';
    const popup =
      `<b>#${h.rank} ${meta.lot_name || h.lot_id}</b><br>` +
      `${meta.gu} · ${meta.dong}<br>` +
      `구역: <b style="color:${hubCol}">${zone}</b><br>` +
      `커버 <b>${h.cover_n}셀</b> · Ds합 <b>${(h.cover_ds||0).toFixed(2)}</b><br>` +
      `경로타당성: ${((h.route_fi||0)*100).toFixed(0)}%<br>` +
      `<small>${h.explanation||''}</small>`;
    groupHubs.addLayer(
      L.circleMarker([lat, lon], {
        radius:13, color:hubCol, fillColor:hubCol, fillOpacity:0.88, weight:2
      }).bindPopup(popup)
    );
    groupHubs.addLayer(
      L.circleMarker([lat, lon], {radius:4, color:'#fff', fillColor:'#fff', fillOpacity:1, weight:0})
    );
  });

  // ── Draw route lines ──────────────────────────────────────────
  routeList.forEach(r => {
    if (!r.h_lat || !r.t_lat) return;
    const p1 = [r.h_lat, r.h_lon];
    const p2 = [r.t_lat, r.t_lon];
    const hubMeta = ALL_HUBS[r.lot_id] || {};
    const popup =
      `<b>${hubMeta.lot_name||r.lot_id} → ${r.dong}</b><br>` +
      `드론 ${(r.drone_t||0).toFixed(1)}분 · 절감 <b>${(r.ts||0).toFixed(1)}분</b><br>` +
      `CO₂ 절감: ${(r.co2||0).toFixed(0)}g<br>` +
      (r.approval ? '<span style="color:#ffb74d">⚠ 관제권 승인 필요</span>' : '<span style="color:#53d769">✓ 즉시 비행 가능</span>');
    groupRoutes.addLayer(
      L.polyline([p1, p2], {
        color: r.approval ? '#ffb74d' : '#53d769',
        weight: 2, opacity: 0.55, dashArray: r.approval ? '4 4' : null
      }).bindPopup(popup)
    );
  });

  // ── Refresh hub list panel ────────────────────────────────────
  const totalDs = hubList.reduce((a, h) => a + (h.cover_ds||0), 0) || 1;
  document.getElementById('hub-list').innerHTML = hubList.map(h => {
    const meta = ALL_HUBS[h.lot_id] || {};
    const pct  = ((h.cover_ds||0) / totalDs * 100).toFixed(1);
    return `<div class="hub-item" onclick="map.flyTo([${meta.lat||37.42},${meta.lon||127.13}],14)">
      <span class="hub-rank">#${h.rank}</span>
      <span class="hub-name">${meta.lot_name||h.lot_id}</span>
      <div class="hub-detail">${meta.gu||''} · ${meta.dong||''}</div>
      <div class="hub-detail">커버 ${h.cover_n}셀 · Ds합 ${(h.cover_ds||0).toFixed(2)}</div>
      <div class="hub-coverage-bar">
        <div class="hub-coverage-fill" style="width:${pct}%"></div>
      </div>
    </div>`;
  }).join('');

  // ── Update dynamic KPI badges ─────────────────────────────────
  document.getElementById('kv-hubs').textContent    = hubList.length;
  document.getElementById('kv-routes').textContent  = routeList.length;
  document.getElementById('hub-count-badge').textContent = hubList.length;
}

// ── Continuous HSL gradient: 0=red, 0.5=yellow, 1.0=green ──
function scenColor(score, hardExcl) {
  if (hardExcl) return '#555';
  const hue = Math.round(Math.max(0, Math.min(1, score)) * 120);
  return `hsl(${hue}, 75%, 48%)`;
}

// ── Two-stage scoring: Demand × Constraint ──────────────────
function computeDemandScore(g) {
  const scores = [];
  if (document.getElementById('cb-b2b').checked) scores.push(g.demand_b2b || 0);
  if (document.getElementById('cb-b2c').checked) scores.push(g.demand_b2c || 0);
  if (document.getElementById('cb-cv').checked)  scores.push(g.demand_cv  || 0);
  if (scores.length === 0) return 1.0;  // no demand filter → neutral
  return scores.reduce((a,b) => a+b, 0) / scores.length;
}

function computeConstraintScore(g) {
  const useAir   = document.getElementById('cb-air').checked;
  const useObs   = document.getElementById('cb-obs').checked;
  const useNoise = document.getElementById('cb-noise').checked;
  const useRobot = document.getElementById('cb-robot').checked;
  const useWx    = document.getElementById('cb-wx').checked;
  const strict   = document.getElementById('airspace-mode').value === 'strict';

  let scores = [];
  if (useAir) {
    let s = g.score_air;
    if (strict && s < 0.3) s = 0;
    scores.push(s);
  } else { scores.push(1.0); }
  scores.push(useObs   ? g.score_obs   : 1.0);
  scores.push(useNoise ? g.score_noise : 1.0);
  scores.push(useRobot ? g.score_robot : 1.0);
  scores.push(useWx    ? g.score_wx    : 1.0);
  return scores.reduce((a,b)=>a+b,0) / scores.length;
}

function computeFinalScore(g) {
  return computeDemandScore(g) * computeConstraintScore(g);
}

// H3 circle markers — radius=4 for res-9 density
const h3Markers = [];
GRID.forEach(g => {
  if (!g.lat || !g.lon) return;
  const finalScore = computeFinalScore(g);
  const col = scenColor(finalScore, g.hard_excl);
  const m = L.circleMarker([g.lat, g.lon], {
    radius: 4,
    color: col, fillColor: col,
    fillOpacity: 0.65, weight: 1, opacity: 0.9,
  });
  // Popup will be set dynamically in applyScenario()
  h3Markers.push({ m, g });
  groupH3.addLayer(m);
});

// Apply scenario: recolor H3 markers AND refresh hub/route layers
function applyScenario() {
  const useAir = document.getElementById('cb-air').checked;
  const strict = document.getElementById('airspace-mode').value === 'strict';
  let high = 0, mid = 0, low = 0;

  h3Markers.forEach(({m, g}) => {
    const dScore = computeDemandScore(g);
    const cScore = computeConstraintScore(g);
    const fScore = dScore * cScore;
    const permExcl = strict && useAir && g.score_air < 0.1;
    const col = permExcl ? '#555' : scenColor(fScore, false);
    m.setStyle({ color:col, fillColor:col });

    // Dynamic popup with all scoring details
    m.bindPopup(
      `<b>${g.ADM_NM} (${g.GU_NM})</b><br>` +
      `B2B: ${(g.demand_b2b||0).toFixed(3)} · B2C: ${(g.demand_b2c||0).toFixed(3)}<br>` +
      `상권활력: ${(g.demand_cv||0).toFixed(3)}<br>` +
      `수요점수: <b>${dScore.toFixed(3)}</b><br>` +
      `제약점수: <b>${cScore.toFixed(3)}</b><br>` +
      `최종적합성: <b style="color:${col}">${fScore.toFixed(3)}</b><br>` +
      `${permExcl ? '<span style="color:#e94560">⛔ 비행불가구역</span><br>' : ''}` +
      `<small>${g.h3_index}</small>`
    );

    if (permExcl || fScore < 0.30) low++;
    else if (fScore >= 0.55) high++;
    else mid++;
  });
  document.getElementById('filter-summary').textContent =
    `높음(≥0.55) ${high} · 중간 ${mid} · 낮음(<0.30) ${low} / 전체 ${GRID.length}`;

  // Update toggle button styles — demand + constraint toggles
  ['b2b','b2c','cv','air','obs','noise','robot','wx'].forEach(k => {
    const cb = document.getElementById('cb-'+k);
    const lt = document.getElementById('lt-'+k);
    if (cb && lt) lt.classList.toggle('active', cb.checked);
  });

  // Refresh hub/route layers for the new scenario
  currentScenarioId = findScenarioId();
  renderScenarioHubsRoutes(currentScenarioId);
}
applyScenario();

// Demand scoring is now integrated into cell coloring via toggles — no separate overlay needed.

// Hub list is rendered by renderScenarioHubsRoutes() on every scenario change.

// ════════════════════════════════════════════════════════
// NARRATIVE CARDS
// ════════════════════════════════════════════════════════
document.getElementById('narr-grid').innerHTML = NARR.map(n =>
  `<div class="narr-card" style="--accent:${n.accent||'#4fc3f7'}">
    <div class="narr-icon">${n.icon||'📌'}</div>
    <div class="narr-title">${n.title_kr||''}</div>
    <div class="narr-body">${n.body_kr||''}</div>
  </div>`
).join('');

// ════════════════════════════════════════════════════════
// PLOTLY CONFIG
// ════════════════════════════════════════════════════════
const PLY = {
  bg:    '#16213e', paper: '#16213e',
  fg:    '#e0e0e0', grid:  '#1a3a5c',
  font:  { family:'Noto Sans KR', color:'#e0e0e0', size:11 },
};
function plyLayout(extra) {
  return Object.assign({
    paper_bgcolor: PLY.paper, plot_bgcolor: PLY.bg,
    font: PLY.font, margin:{l:40,r:12,t:20,b:60},
    xaxis: { gridcolor:PLY.grid, tickfont:{color:'#8899aa',size:10}, linecolor:'#1a3a5c' },
    yaxis: { gridcolor:PLY.grid, tickfont:{color:'#8899aa',size:10}, linecolor:'#1a3a5c' },
    showlegend: false,
  }, extra||{});
}
const CFG = { responsive:true, displayModeBar:false };

// ── Dong Top-15 bar chart ─────────────────────────────────────────────────
if (DONG_T15.length) {
  const labels = DONG_T15.map(d => d.label || d.ADM_NM);
  Plotly.newPlot('chart-dong', [{
    type:'bar', orientation:'h',
    x: DONG_T15.map(d => +(d.composite||0)),
    y: labels,
    text: DONG_T15.map(d => (+(d.composite||0)).toFixed(3)),
    textposition:'outside',
    marker:{ color:'#4fc3f7', opacity:0.8 },
  }], plyLayout({
    yaxis:{ autorange:'reversed', tickfont:{color:'#8899aa',size:9}, gridcolor:'#1a3a5c' },
    margin:{l:80,r:40,t:20,b:30},
  }), CFG);
}

// ── Hourly pattern ────────────────────────────────────────────────────────
if (HOURLY.length) {
  const hmax = Math.max(...HOURLY.map(h => h.dw_total||0), 1);
  Plotly.newPlot('chart-hourly', [{
    type:'bar',
    x: HOURLY.map(h => h.hour_label || h.hour_code),
    y: HOURLY.map(h => h.dw_total||0),
    marker:{ color: HOURLY.map(h => {
      const p = h.period||'';
      return p.includes('점심') ? '#e94560' : p.includes('저녁') ? '#ffb74d' : '#4fc3f7';
    })},
    text: HOURLY.map(h => (h.dw_total||0).toLocaleString()),
    textposition:'auto',
  }], plyLayout({ margin:{l:40,r:12,t:20,b:80} }), CFG);
}

// ── Mode compare ──────────────────────────────────────────────────────────
if (MODE.length) {
  const drones = MODE.map(r => +(r.drone||0));
  const motos  = MODE.map(r => +(r.motorcycle||0));
  const labels = MODE.map(r => r.label||'').slice(0,15);
  const dn = drones.slice(0,15), mn = motos.slice(0,15);
  Plotly.newPlot('chart-mode', [
    { type:'bar', name:'드론',      x:labels, y:dn, marker:{color:'#53d769',opacity:0.8} },
    { type:'bar', name:'오토바이',  x:labels, y:mn, marker:{color:'#e94560',opacity:0.8} },
  ], plyLayout({
    barmode:'group', showlegend:true,
    legend:{font:{color:'#e0e0e0',size:10}, bgcolor:'transparent'},
    xaxis:{tickangle:-40, tickfont:{size:9}},
    yaxis:{title:{text:'시간(분)',font:{size:10}}},
    margin:{l:50,r:12,t:20,b:80},
  }), CFG);
}

// ── ESG bar chart ─────────────────────────────────────────────────────────
if (ESG.length) {
  Plotly.newPlot('chart-esg', [{
    type:'bar', orientation:'h',
    x: ESG.map(e => +(e.e_index||0)),
    y: ESG.map(e => e.assigned_lot_name||''),
    marker:{ color:'#53d769', opacity:0.8 },
    text: ESG.map(e => (+(e.e_index||0)).toFixed(3)),
    textposition:'outside',
  }], plyLayout({
    yaxis:{ autorange:'reversed', tickfont:{size:9,color:'#8899aa'}, gridcolor:'#1a3a5c' },
    margin:{l:120,r:40,t:20,b:30},
    xaxis:{title:{text:'ESG 지수',font:{size:10}}},
  }), CFG);
}

// ── Dong zone % ───────────────────────────────────────────────────────────
const dronePctDong = {};
(DONG_ZP||[]).forEach(r => {
  if ((r.delivery_zone||'').includes('드론')) {
    dronePctDong[r.ADM_NM] = r.pct||0;
  }
});
const dpKeys = Object.keys(dronePctDong).sort((a,b) => dronePctDong[b]-dronePctDong[a]).slice(0,15);
if (dpKeys.length) {
  Plotly.newPlot('chart-dong-zone', [{
    type:'bar', orientation:'h',
    x: dpKeys.map(k => dronePctDong[k]),
    y: dpKeys,
    marker:{ color:'#53d769', opacity:0.75 },
    text: dpKeys.map(k => dronePctDong[k].toFixed(1)+'%'),
    textposition:'outside',
  }], plyLayout({
    yaxis:{autorange:'reversed', tickfont:{size:9,color:'#8899aa'}},
    xaxis:{title:{text:'드론우선 셀 비율(%)',font:{size:10}},range:[0,105]},
    margin:{l:80,r:50,t:20,b:30},
  }), CFG);
}

// ── B2B / B2C / Robot Top-15 ──────────────────────────────────────────────
function renderTop15(divId, data, color, title) {
  if (!data || !data.length) return;
  const labels = data.map(d => d.label || d.ADM_NM);
  Plotly.newPlot(divId, [{
    type:'bar', orientation:'h',
    x: data.map(d => +(d.score||0)),
    y: labels,
    marker:{color, opacity:0.8},
    text: data.map(d => (+(d.score||0)).toFixed(3)),
    textposition:'outside',
  }], plyLayout({
    yaxis:{autorange:'reversed', tickfont:{size:9,color:'#8899aa'}},
    xaxis:{title:{text:title,font:{size:10}}},
    margin:{l:80,r:50,t:20,b:30},
  }), CFG);
}
renderTop15('chart-b2b',   B2B,   '#ff6b35', 'B2B 지수');
renderTop15('chart-b2c',   B2C,   '#a855f7', 'B2C 지수');
renderTop15('chart-robot', ROBOT, '#42a5f5', '로봇접근 지수');

</script>
</body>
</html>"""

# Replace placeholder with embedded data
HTML = HTML.replace("__EMBEDDED__", embedded)

OUT.write_text(HTML, encoding="utf-8")
print(f"\n✅ dashboard.html written ({OUT.stat().st_size // 1024} KB)")
print(f"   Open: {OUT}")
print(f"   Or serve: python -m http.server 8765 --directory 04_visualization")
