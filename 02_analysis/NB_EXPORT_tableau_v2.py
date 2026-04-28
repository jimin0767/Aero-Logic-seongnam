"""
NB_EXPORT_tableau_v2.py
=========================
Tableau 시각화용 최종 데이터 export (v3 기반 완성본)

포함 데이터:
  1. H3 그리드 — Ds_v3 수요지수 + 7레이어 composite_v3 + Zoning
  2. 최적 거점 — final_hubs_v3 (v2도 포함, 비교용)
  3. ESG 지수 — E_reduction, T_efficiency
  4. ETA 비교 — 드론/로봇/오토바이
  5. 기상 현황 — 드론 Go/No-Go
  6. 행정동별 요약 — 수요·커버·인프라 종합

출력 경로: processed/tableau/
  - TB01_h3_grid.csv          ← H3 셀 레벨 (주요 시각화)
  - TB02_hubs.csv             ← 거점 레벨
  - TB03_dong_summary.csv     ← 행정동 레벨
  - TB04_esg_comparison.csv   ← ESG 배송모드 비교
  - TB05_weather.csv          ← 기상 데이터
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

BASE = Path(r"C:\Users\pasoh\OneDrive\문서\GitHub\Aero-Logic-seongnam")
OUT  = BASE / "processed"
TB   = OUT / "tableau"
TB.mkdir(exist_ok=True)

print("=" * 60)
print("NB_EXPORT_tableau_v2 — Tableau 최종 데이터 export")
print("=" * 60)

# ── TB01: H3 그리드 레벨 ──────────────────────────────────────
print("\n[TB01] H3 그리드 레벨...")

# v4(7레이어) 기본 데이터
grid = pd.read_csv(OUT / "constraint_layers_v4.csv", encoding="utf-8-sig")

# Zoning 병합
if (OUT / "delivery_zones.csv").exists():
    zone_df = pd.read_csv(OUT / "delivery_zones.csv", encoding="utf-8-sig",
                           usecols=["h3_index", "zone"])
    grid = grid.merge(zone_df, on="h3_index", how="left")
    grid["zone"] = grid["zone"].fillna("부적합")

# 거점 여부 플래그
hubs_v3 = None
if (OUT / "final_hubs_v3.csv").exists():
    hubs_v3 = pd.read_csv(OUT / "final_hubs_v3.csv", encoding="utf-8-sig")
    hub_h3s_v3 = set(hubs_v3["h3_index"])
    grid["is_hub_v3"] = grid["h3_index"].isin(hub_h3s_v3).astype(int)
    grid["hub_rank_v3"] = grid["h3_index"].map(
        dict(zip(hubs_v3["h3_index"], hubs_v3["step"]))
    )
else:
    grid["is_hub_v3"] = 0
    grid["hub_rank_v3"] = np.nan

hubs_v2 = None
if (OUT / "final_hubs_v2.csv").exists():
    hubs_v2 = pd.read_csv(OUT / "final_hubs_v2.csv")
    hub_h3s_v2 = set(hubs_v2["h3_index"])
    grid["is_hub_v2"] = grid["h3_index"].isin(hub_h3s_v2).astype(int)

# Ds_v3 등급 (Tableau 색상 필터용)
def ds_grade(ds):
    if ds >= 0.5:  return "A-최우선"
    elif ds >= 0.35: return "B-높음"
    elif ds >= 0.20: return "C-보통"
    elif ds >= 0.10: return "D-낮음"
    else:            return "E-부적합"
grid["demand_grade"] = grid["Ds_v3"].apply(ds_grade)

# Tableau 출력 컬럼 선택
tb01_cols = [
    "h3_index", "lat", "lon",
    "CSV_ADMI_CD", "ADM_NM", "GU_NM",
    # 수요 지수
    "Ds_v3", "Hr", "Fp", "Cc", "Ec", "Od_v2",
    # 제약 레이어
    "score_airspace", "score_obstacle", "score_noise",
    "score_terrain", "score_weather",
    "score_construction", "score_protected",
    "Ra", "composite_v3",
    # 분류
    "zone", "demand_grade",
    # 거점
    "is_hub_v3", "hub_rank_v3", "is_hub_v2",
]
tb01_cols = [c for c in tb01_cols if c in grid.columns]
tb01 = grid[tb01_cols].copy()

# NaN → 0 처리
num_cols = tb01.select_dtypes(include=[np.number]).columns
tb01[num_cols] = tb01[num_cols].fillna(0).round(4)

tb01.to_csv(TB / "TB01_h3_grid.csv", index=False, encoding="utf-8-sig")
print(f"  ✅ TB01_h3_grid.csv: {len(tb01)}행 × {len(tb01.columns)}컬럼")

# ── TB02: 거점 레벨 ──────────────────────────────────────────
print("\n[TB02] 거점 레벨...")

hub_rows = []
for version, hubs in [("v2", hubs_v2), ("v3", hubs_v3)]:
    if hubs is None:
        continue
    for _, row in hubs.iterrows():
        hub_rows.append({
            "version"    : version,
            "rank"       : int(row["step"]),
            "h3_index"   : row["h3_index"],
            "lat"        : round(row["lat"], 6),
            "lon"        : round(row["lon"], 6),
            "dong"       : row["ADM_NM"],
            "gu"         : row["GU_NM"],
            "Ds_v3"      : round(row["Ds_v3"], 4),
            "Ra"         : round(row["Ra"], 4),
            "composite"  : round(row.get("composite_v3", row.get("composite_v2", 0)), 4),
            "zone"       : row.get("zone", ""),
            "coverage_pct": round(row["coverage_pct"] * 100, 1),
            "score_construction": round(row.get("score_construction", 1.0), 3),
            "score_protected"   : round(row.get("score_protected", 1.0), 3),
        })

tb02 = pd.DataFrame(hub_rows)
tb02.to_csv(TB / "TB02_hubs.csv", index=False, encoding="utf-8-sig")
print(f"  ✅ TB02_hubs.csv: {len(tb02)}행")

# ── TB03: 행정동 레벨 요약 ────────────────────────────────────
print("\n[TB03] 행정동 레벨 요약...")

dong_grp = grid.groupby(["GU_NM", "ADM_NM"]).agg(
    cell_count    = ("h3_index", "count"),
    avg_ds3       = ("Ds_v3", "mean"),
    max_ds3       = ("Ds_v3", "max"),
    avg_ra        = ("Ra", "mean"),
    avg_cv3       = ("composite_v3", "mean"),
    hub_v3_count  = ("is_hub_v3", "sum"),
    hub_v2_count  = ("is_hub_v2", "sum") if "is_hub_v2" in grid.columns else ("is_hub_v3", "sum"),
    feasible_cells = ("composite_v3", lambda x: (x > 0).sum()),
).reset_index()

# Zoning 분포
zone_pivot = grid.groupby(["ADM_NM", "zone"]).size().unstack(fill_value=0).reset_index()
zone_cols  = ["드론전용", "로봇전용", "Hybrid", "일반", "부적합"]
for z in zone_cols:
    if z not in zone_pivot.columns:
        zone_pivot[z] = 0
dong_grp = dong_grp.merge(
    zone_pivot[["ADM_NM"] + [z for z in zone_cols if z in zone_pivot.columns]],
    on="ADM_NM", how="left"
).fillna(0)

dong_grp["feasible_pct"] = (dong_grp["feasible_cells"] / dong_grp["cell_count"] * 100).round(1)
dong_grp = dong_grp.round(4)

dong_grp.to_csv(TB / "TB03_dong_summary.csv", index=False, encoding="utf-8-sig")
print(f"  ✅ TB03_dong_summary.csv: {len(dong_grp)}행 (행정동별)")

# ── TB04: ESG / 배송모드 비교 ────────────────────────────────
print("\n[TB04] ESG 배송모드 비교...")

esg_rows = []
# ESG 시나리오 데이터
if (OUT / "esg_index.csv").exists():
    esg_df = pd.read_csv(OUT / "esg_index.csv", encoding="utf-8-sig")
    esg_df["data_type"] = "scenario"
    esg_rows.append(esg_df)

# ETA 비교
if (OUT / "mode_comparison_v2.csv").exists():
    mode_df = pd.read_csv(OUT / "mode_comparison_v2.csv", encoding="utf-8-sig")
    mode_df["data_type"] = "mode_comparison"
    esg_rows.append(mode_df)

if esg_rows:
    tb04 = pd.concat(esg_rows, ignore_index=True)
    tb04.to_csv(TB / "TB04_esg_comparison.csv", index=False, encoding="utf-8-sig")
    print(f"  ✅ TB04_esg_comparison.csv: {len(tb04)}행")

# ESG 핵심 요약 (KPI용)
esg_kpi = {
    "지표"     : ["탄소절감률", "시간단축률", "드론가용률", "연간탄소절감(365K건)"],
    "값"       : [],
    "단위"     : ["%", "%", "%", "톤CO2"],
    "비고"     : ["오토바이 대비", "오토바이 대비", "기상청 실측(90일)", "하루 365,000건 기준"],
}
if (OUT / "weather_sim_summary.json").exists():
    ws = json.loads((OUT / "weather_sim_summary.json").read_text(encoding="utf-8"))
    esg_kpi["값"] = [
        ws.get("E_reduction_pct", 87.0),
        abs(ws.get("T_efficiency_pct", 39.8)),
        round(ws.get("P_drone_available_observed", ws.get("P_drone_available", 0.78)) * 100, 1),
        ws.get("annual_carbon_1M_ton_1000d", 115.8) * 365,
    ]
else:
    esg_kpi["값"] = [87.0, 39.8, 78.1, 115.8]

pd.DataFrame(esg_kpi).to_csv(TB / "TB04_esg_kpi.csv", index=False, encoding="utf-8-sig")
print(f"  ✅ TB04_esg_kpi.csv 저장")

# ── TB05: 기상 데이터 ────────────────────────────────────────
print("\n[TB05] 기상 데이터...")

# 현재 기상
if (OUT / "weather_current.json").exists():
    wc = json.loads((OUT / "weather_current.json").read_text(encoding="utf-8"))
    wc_row = {
        "timestamp"    : wc.get("timestamp", ""),
        "location"     : wc.get("location", "성남시 분당구"),
        "wind_speed"   : wc.get("wind_speed", 0),
        "rain_1h"      : wc.get("rain_1h", 0),
        "temperature"  : wc.get("temperature", 0),
        "humidity"     : wc.get("humidity", 0),
        "go_nogo"      : wc.get("go_nogo", "GO"),
        "data_type"    : "current",
    }
    tb05 = pd.DataFrame([wc_row])
else:
    tb05 = pd.DataFrame()

# 과거 관측
if (OUT / "weather_history.csv").exists():
    hist = pd.read_csv(OUT / "weather_history.csv", encoding="utf-8-sig")
    hist["data_type"] = "history"
    hist["go_nogo"]   = hist.apply(
        lambda r: "NO-GO" if (pd.notna(r.get("ws")) and r.get("ws", 0) >= 10)
                          or r.get("rn", 0) >= 5 else "GO",
        axis=1
    )
    hist["go_nogo_bin"] = (hist["go_nogo"] == "GO").astype(int)
    tb05 = pd.concat([tb05, hist], ignore_index=True)

tb05.to_csv(TB / "TB05_weather.csv", index=False, encoding="utf-8-sig")
print(f"  ✅ TB05_weather.csv: {len(tb05)}행")

# ── 내보내기 요약 ─────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"[Tableau export 완료]  → processed/tableau/")
print(f"  TB01_h3_grid.csv     : {len(tb01):,}행  ← 지도 주요 레이어")
print(f"  TB02_hubs.csv        : {len(tb02):,}행  ← 거점 v2/v3 비교")
print(f"  TB03_dong_summary.csv: {len(dong_grp):,}행  ← 행정동 집계")
print(f"  TB04_esg_*.csv       : ESG KPI + 시나리오")
print(f"  TB05_weather.csv     : 기상 Go/No-Go")
print(f"\n💡 Tableau 연동 순서:")
print(f"  1. TB01을 기본 데이터소스 (h3_index = 지도 ID)")
print(f"  2. TB02 JOIN on h3_index → 거점 위치 표시")
print(f"  3. TB03 별도 시트 → 행정동 막대차트")
print(f"  4. TB04 KPI 카드 + 시나리오 라인차트")
print(f"  5. TB05 시계열 → 기상 가용률 추이")
