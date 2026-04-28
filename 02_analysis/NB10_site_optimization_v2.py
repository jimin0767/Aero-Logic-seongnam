"""
NB10_site_optimization_v2.py
=============================
Ds_v3 + Ra 기반 거점 재선정 — 소현 작업

기존 NB10 문제:
  - urgency (2변수) 기반 핫스팟 정의
  - 로봇 접근성 미반영
  - 거점 후보가 H3 셀 전체 (실제 설치 불가 위치 포함)

개선:
  - Ds_v3 (5변수 수요지수) 기반 핫스팟 재정의
  - Ra (로봇 접근성) 를 6번째 제약 레이어로 추가
  - composite_score_v2 = 기존 5레이어 × Ra 추가 반영

산출물:
  processed/final_hubs_v2.csv        — 새 수요지수 기반 거점
  processed/final_hubs_v2.gpkg       — GeoPackage (geopandas 있으면)
  processed/hub_coverage_summary.csv — 구별 커버리지 요약
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

BASE = Path(r"C:\Users\pasoh\OneDrive\문서\GitHub\Aero-Logic-seongnam")
OUT  = BASE / "processed"

print("=" * 60)
print("NB10 v2 — Ds_v3 + Ra 기반 거점 재선정")
print("=" * 60)

# ── 파라미터 ─────────────────────────────────────────────────────────────────
SERVICE_RADIUS_M  = 1000    # 서비스 반경 (m) — H3 res.9 기준 현실적 드론 범위
MAX_HUBS          = 10      # 최대 거점 수
TARGET_COVERAGE   = 0.90    # 목표 커버리지
DEMAND_THRESHOLD  = 0.70    # 핫스팟 기준 Ds_v3 상위 30%
RA_WEIGHT         = 0.15    # Ra를 composite에 반영하는 가중치
MAX_SAME_DONG     = 1       # 동일 행정동 최대 선정 횟수 (중복 방지)

print(f"\n[파라미터]")
print(f"  서비스 반경: {SERVICE_RADIUS_M}m")
print(f"  최대 거점 수: {MAX_HUBS}")
print(f"  목표 커버리지: {TARGET_COVERAGE*100}%")
print(f"  핫스팟 기준: Ds_v3 상위 {(1-DEMAND_THRESHOLD)*100:.0f}%")
print(f"  Ra 반영 가중치: {RA_WEIGHT}")

# ── 데이터 로드 ───────────────────────────────────────────────────────────────
print("\n[STEP 1] 데이터 로드...")

# constraint_layers_v3_ra.csv (Ds_v3 + Ra 포함)
v3_ra_path = OUT / "constraint_layers_v3_ra.csv"
v3_path    = OUT / "constraint_layers_v3.csv"

if v3_ra_path.exists():
    gdf = pd.read_csv(v3_ra_path)
    print(f"  ✅ constraint_layers_v3_ra.csv 로드 ({len(gdf)}행)")
    HAS_RA = "Ra" in gdf.columns and gdf["Ra"].sum() > 0
else:
    gdf = pd.read_csv(v3_path)
    gdf["Ra"] = 0.5  # fallback
    HAS_RA = False
    print(f"  ⚠ v3_ra 없음, v3 사용 + Ra=0.5 기본값")

print(f"  컬럼: {gdf.columns.tolist()}")
print(f"  Ra 사용: {HAS_RA}")

# Ds_v3 없으면 Ds_v2 사용
if "Ds_v3" not in gdf.columns and "Ds_v2" in gdf.columns:
    gdf["Ds_v3"] = gdf["Ds_v2"]
    print("  Ds_v3 없음 → Ds_v2 사용")
elif "Ds_v3" not in gdf.columns:
    gdf["Ds_v3"] = gdf["urgency"]
    print("  Ds_v3/v2 없음 → urgency 사용")

# ── STEP 2: composite_score_v2 계산 ──────────────────────────────────────────
print("\n[STEP 2] composite_score_v2 = 기존5레이어 × Ra 반영...")

score_cols = ["score_airspace", "score_obstacle", "score_noise", "score_terrain", "score_weather"]
score_cols = [c for c in score_cols if c in gdf.columns]

gdf["composite_5layer"] = gdf[score_cols].prod(axis=1)

if HAS_RA:
    # Ra를 가중 평균으로 추가 (기존 composite 85% + Ra 15%)
    gdf["composite_score_v2"] = (
        (1 - RA_WEIGHT) * gdf["composite_5layer"]
      + RA_WEIGHT        * gdf["Ra"]
    )
    print(f"  composite_score_v2 = {1-RA_WEIGHT:.0%}×5layer + {RA_WEIGHT:.0%}×Ra")
else:
    gdf["composite_score_v2"] = gdf["composite_5layer"]
    print("  composite_score_v2 = 5레이어 그대로 (Ra 없음)")

print(f"  기존 composite 평균: {gdf['composite_5layer'].mean():.4f}")
print(f"  신규 composite_v2 평균: {gdf['composite_score_v2'].mean():.4f}")

# ── STEP 3: 핫스팟 & 후보지 정의 ─────────────────────────────────────────────
print("\n[STEP 3] 핫스팟 & 거점 후보지 정의...")

# 운영 가능 셀 (composite_v2 > 0)
feasible = gdf[gdf["composite_score_v2"] > 0].copy()
print(f"  운영 가능 셀: {len(feasible):,} / {len(gdf):,}")

# 핫스팟 = Ds_v3 상위 (1-DEMAND_THRESHOLD) 분위수 이상
ds_threshold = gdf["Ds_v3"].quantile(DEMAND_THRESHOLD)
hotspots = gdf[
    (gdf["Ds_v3"] >= ds_threshold) &
    (gdf["composite_score_v2"] > 0)
].copy()
print(f"  핫스팟 (Ds_v3 ≥ {ds_threshold:.4f}): {len(hotspots):,}셀")

# 기존 urgency 기반 핫스팟과 비교
if "urgency" in gdf.columns:
    old_threshold = gdf["urgency"].quantile(DEMAND_THRESHOLD)
    old_hotspots = gdf[
        (gdf["urgency"] >= old_threshold) &
        (gdf["composite_5layer"] > 0)
    ]
    print(f"  [비교] 기존 urgency 핫스팟: {len(old_hotspots):,}셀")
    overlap = len(set(hotspots["h3_index"]) & set(old_hotspots["h3_index"]))
    print(f"  핫스팟 겹침: {overlap}셀 ({overlap/max(len(hotspots),1)*100:.1f}%)")

# ── STEP 4: 거리 계산 함수 ───────────────────────────────────────────────────

def haversine_km(lat1, lon1, lat2, lon2):
    """위경도 → 거리(km)"""
    R = 6371.0
    r = np.pi / 180
    f1, f2 = lat1 * r, lat2 * r
    df = (lat2 - lat1) * r
    dl = (lon2 - lon1) * r
    a = np.sin(df/2)**2 + np.cos(f1)*np.cos(f2)*np.sin(dl/2)**2
    return 2 * R * np.arcsin(np.sqrt(a))

SERVICE_KM = SERVICE_RADIUS_M / 1000.0

# ── STEP 5: 그리디 셋 커버 알고리즘 ─────────────────────────────────────────
print(f"\n[STEP 4] 그리디 셋 커버 (반경 {SERVICE_RADIUS_M}m, 최대 {MAX_HUBS}개)...")

# 핫스팟 좌표 배열
hs_lat = hotspots["lat"].values
hs_lon = hotspots["lon"].values
hs_idx = hotspots.index.values

# 후보지 = 운영 가능 셀 전체
cand_lat = feasible["lat"].values
cand_lon = feasible["lon"].values
cand_idx = feasible.index.values

# 핫스팟별 가중치 = Ds_v3 (수요가 높은 셀 커버가 더 중요)
hs_weight = hotspots["Ds_v3"].values

# 커버 매트릭스 사전 계산 (candidate → set of covered hotspot positions)
print(f"  후보지 {len(cand_idx):,}개 × 핫스팟 {len(hs_idx):,}개 커버 계산 중...")

# 배치 계산으로 메모리 효율화
BATCH = 100
coverage_map = {}  # cand_row_idx → set of hs positions covered

for bi in range(0, len(cand_idx), BATCH):
    batch_cands = list(range(bi, min(bi+BATCH, len(cand_idx))))
    for ci in batch_cands:
        dists = haversine_km(cand_lat[ci], cand_lon[ci], hs_lat, hs_lon)
        covered_pos = set(np.where(dists <= SERVICE_KM)[0])
        if covered_pos:
            coverage_map[ci] = covered_pos

print(f"  커버 가능 후보지: {len(coverage_map):,}개")

# 그리디 실행
uncovered   = set(range(len(hs_idx)))  # 아직 커버 안 된 핫스팟 위치 인덱스
selected    = []                        # 선택된 후보지 row index
dong_count  = {}                        # 동별 선정 횟수 (중복 방지)

for step in range(MAX_HUBS):
    if not uncovered:
        print(f"  ✅ {step}단계에서 전체 커버 완료!")
        break

    # 가장 많은 미커버 핫스팟(가중합)을 커버하는 후보지 선택
    best_ci, best_gain, best_new = -1, -1.0, set()

    for ci, cov_set in coverage_map.items():
        new_cov = cov_set & uncovered
        if not new_cov:
            continue
        # 동일 동 중복 방지 (이미 MAX_SAME_DONG개 선정된 동 제외)
        row_idx_ci = cand_idx[ci]
        dong_nm_ci = gdf.loc[row_idx_ci, "ADM_NM"]
        if dong_count.get(dong_nm_ci, 0) >= MAX_SAME_DONG:
            continue
        gain = sum(hs_weight[pos] for pos in new_cov)
        if gain > best_gain:
            best_gain = gain
            best_ci   = ci
            best_new  = new_cov

    if best_ci == -1:
        print(f"  더 이상 커버 가능한 후보지 없음 ({step+1}개 선택)")
        break

    # 선택
    row_idx = cand_idx[best_ci]
    hub_info = gdf.loc[row_idx].copy()
    uncovered -= best_new
    dong_count[hub_info["ADM_NM"]] = dong_count.get(hub_info["ADM_NM"], 0) + 1

    coverage_pct = 1 - len(uncovered) / len(hs_idx)
    selected.append({
        "step"          : step + 1,
        "row_idx"       : row_idx,
        "h3_index"      : hub_info["h3_index"],
        "lat"           : hub_info["lat"],
        "lon"           : hub_info["lon"],
        "ADM_NM"        : hub_info["ADM_NM"],
        "GU_NM"         : hub_info["GU_NM"],
        "Ds_v3"         : round(hub_info["Ds_v3"], 4),
        "Ra"            : round(hub_info.get("Ra", 0), 4),
        "composite_v2"  : round(hub_info["composite_score_v2"], 4),
        "new_covered"   : len(best_new),
        "total_covered" : len(hs_idx) - len(uncovered),
        "coverage_pct"  : round(coverage_pct, 4),
        "gain_weight"   : round(best_gain, 4),
    })

    print(f"  [{step+1}] {hub_info['ADM_NM']} ({hub_info['GU_NM']}) "
          f"→ 신규커버 {len(best_new)} | 누적 {coverage_pct:.1%}")

    if coverage_pct >= TARGET_COVERAGE:
        print(f"  ✅ 목표 커버리지 {TARGET_COVERAGE*100}% 달성!")
        break

hubs_df = pd.DataFrame(selected)
print(f"\n  최종 선정: {len(hubs_df)}개 거점")
print(f"  최종 커버리지: {hubs_df['coverage_pct'].iloc[-1]*100:.1f}%")

# ── STEP 6: 기존 결과와 비교 ─────────────────────────────────────────────────
print("\n[STEP 5] 기존 final_hubs.csv와 비교...")

old_hubs_path = OUT / "final_hubs.csv"
if old_hubs_path.exists():
    old = pd.read_csv(old_hubs_path)
    print(f"  기존 거점 ({len(old)}개):")
    if "name" in old.columns:
        for _, r in old.iterrows():
            print(f"    {r.get('name','?')} — coverage {r.get('coverage_pct',0)*100:.1f}%")
    print(f"\n  신규 거점 ({len(hubs_df)}개):")
    for _, r in hubs_df.iterrows():
        print(f"    [{r['step']}] {r['ADM_NM']} ({r['GU_NM']}) "
              f"— Ds_v3={r['Ds_v3']:.3f} Ra={r['Ra']:.3f} "
              f"coverage={r['coverage_pct']*100:.1f}%")

# ── STEP 7: 저장 ─────────────────────────────────────────────────────────────
print("\n[STEP 6] 저장...")

hubs_df.to_csv(OUT / "final_hubs_v2.csv", index=False, encoding="utf-8-sig")
print(f"  ✅ final_hubs_v2.csv")

# 구별 커버리지 요약
if "GU_NM" in hotspots.columns:
    covered_hs_pos = set(range(len(hs_idx))) - uncovered
    covered_hs = hotspots.iloc[list(covered_hs_pos)]
    gu_total  = hotspots.groupby("GU_NM").size().reset_index(name="total")
    gu_covered = covered_hs.groupby("GU_NM").size().reset_index(name="covered") if len(covered_hs) > 0 else pd.DataFrame(columns=["GU_NM","covered"])
    gu_stats  = gu_total.merge(gu_covered, on="GU_NM", how="left").fillna(0)
    gu_stats["coverage_pct"] = (gu_stats["covered"] / gu_stats["total"] * 100).round(1)
    print("\n  [구별 커버리지]")
    print(gu_stats.to_string(index=False))
    gu_stats.to_csv(OUT / "hub_coverage_summary.csv", index=False, encoding="utf-8-sig")
    print(f"  ✅ hub_coverage_summary.csv")

# geopandas 있으면 gpkg도 저장
try:
    import geopandas as gpd
    from shapely.geometry import Point
    geometry = [Point(r.lon, r.lat) for _, r in hubs_df.iterrows()]
    hubs_gdf = gpd.GeoDataFrame(hubs_df, geometry=geometry, crs="EPSG:4326")
    hubs_gdf.to_file(OUT / "final_hubs_v2.gpkg", driver="GPKG")
    print(f"  ✅ final_hubs_v2.gpkg")
except ImportError:
    print("  ⚠ geopandas 없음 — CSV만 저장됨")

# ── STEP 8: 커버리지 곡선 시각화 ─────────────────────────────────────────────
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    plt.rcParams["axes.unicode_minus"] = False
    for fname in ["Malgun Gothic", "NanumGothic"]:
        try:
            fm.findfont(fname, fallback_to_default=False)
            plt.rcParams["font.family"] = fname
            break
        except Exception:
            pass

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("NB10 v2 — Ds_v3 + Ra 기반 거점 선정 결과", fontsize=13)

    # 커버리지 곡선
    ax = axes[0]
    ax.bar(hubs_df["step"], hubs_df["coverage_pct"]*100,
           color="#42A5F5", edgecolor="white", alpha=0.85)
    ax.axhline(TARGET_COVERAGE*100, color="red", ls="--",
               label=f"목표 {TARGET_COVERAGE*100}%")
    ax.set_xlabel("선택 거점 수")
    ax.set_ylabel("누적 커버리지 (%)")
    ax.set_title("Greedy Set Cover: 거점 수 vs 커버리지")
    ax.set_ylim(0, 105)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    # Ds_v3 vs Ra 산점도 (선정 거점 강조)
    ax2 = axes[1]
    ax2.scatter(gdf["Ds_v3"], gdf.get("Ra", pd.Series(0.5, index=gdf.index)),
                c=gdf["composite_score_v2"], cmap="YlOrRd",
                alpha=0.4, s=10, label="전체 셀")
    ax2.scatter(hubs_df["Ds_v3"], hubs_df["Ra"],
                c="blue", s=120, marker="*", zorder=5, label="선정 거점")
    ax2.set_xlabel("Ds_v3 (수요지수)")
    ax2.set_ylabel("Ra (로봇 접근성)")
    ax2.set_title("수요 vs 로봇 접근성 (선정 거점 표시)")
    ax2.legend()
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUT / "hub_selection_v2.png", dpi=150, bbox_inches="tight")
    print(f"\n  ✅ hub_selection_v2.png 저장")
except Exception as e:
    print(f"  ⚠ 차트 저장 실패: {e}")

print(f"\n✅ NB10 v2 완료!")
print(f"   선정 거점: {len(hubs_df)}개 | 최종 커버리지: {hubs_df['coverage_pct'].iloc[-1]*100:.1f}%")
print(f"   기존 urgency → Ds_v3 + Ra 반영으로 수요지수 정교화")
print(f"\n   [선정 거점 요약]")
print(hubs_df[["step","ADM_NM","GU_NM","Ds_v3","Ra","coverage_pct"]].to_string(index=False))
