"""
NB10_site_optimization_v3.py
==============================
7레이어 composite_v3 기반 거점 재선정 (공사장 + 보호구역 추가)

v2 대비 변경:
  - 입력: constraint_layers_v4.csv (composite_v3 = 7레이어)
  - score_construction, score_protected 제약 추가 반영
  - Zoning 결과(delivery_zones.csv)와 교차 검증
  - v2 vs v3 커버리지 비교 리포트 출력

산출물:
  processed/final_hubs_v3.csv
  processed/hub_coverage_v3.csv
  processed/hub_comparison_v2_v3.csv  ← v2/v3 비교
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

BASE = Path(r"C:\Users\pasoh\OneDrive\문서\GitHub\Aero-Logic-seongnam")
OUT  = BASE / "processed"

print("=" * 60)
print("NB10 v3 — 7레이어 composite_v3 기반 거점 재선정")
print("=" * 60)

# ── 파라미터 (v2와 동일) ──────────────────────────────────────
SERVICE_RADIUS_M = 1000
MAX_HUBS         = 10
DEMAND_THRESHOLD = 0.70    # 핫스팟 = Ds_v3 상위 30%
RA_WEIGHT        = 0.15
MAX_SAME_DONG    = 1

# ── 데이터 로드 ───────────────────────────────────────────────
print("\n[STEP 1] 데이터 로드...")

df = pd.read_csv(OUT / "constraint_layers_v4.csv", encoding="utf-8-sig")
print(f"  constraint_layers_v4: {len(df)}행, {len(df.columns)}컬럼")

# composite_v3 없으면 재계산
if "composite_v3" not in df.columns:
    score_cols = [c for c in ["score_airspace","score_obstacle","score_noise",
                               "score_terrain","score_weather",
                               "score_construction","score_protected"]
                  if c in df.columns]
    df["composite_6layer"] = df[score_cols].prod(axis=1)
    df["composite_v3"] = (1 - RA_WEIGHT) * df["composite_6layer"] + RA_WEIGHT * df["Ra"]

# v2 결과 로드 (비교용)
v2_df = None
if (OUT / "final_hubs_v2.csv").exists():
    v2_df = pd.read_csv(OUT / "final_hubs_v2.csv")

# Zoning 로드 (교차 검증용)
zone_df = None
if (OUT / "delivery_zones.csv").exists():
    zone_df = pd.read_csv(OUT / "delivery_zones.csv", encoding="utf-8-sig",
                           usecols=["h3_index","zone"])
    df = df.merge(zone_df, on="h3_index", how="left")
    df["zone"] = df["zone"].fillna("일반")

print(f"  Ds_v3 range: {df['Ds_v3'].min():.3f} ~ {df['Ds_v3'].max():.3f}")
print(f"  composite_v3 range: {df['composite_v3'].min():.3f} ~ {df['composite_v3'].max():.3f}")

# ── 핫스팟 정의 ───────────────────────────────────────────────
print("\n[STEP 2] 핫스팟 정의...")
ds_threshold = df["Ds_v3"].quantile(DEMAND_THRESHOLD)
hotspots = df[df["Ds_v3"] >= ds_threshold].copy()
print(f"  Ds_v3 임계값(상위 30%): {ds_threshold:.4f}")
print(f"  핫스팟 셀 수: {len(hotspots)}")

# ── 후보지 필터링 ─────────────────────────────────────────────
print("\n[STEP 3] 후보지 필터링...")

# v3 기준: composite_v3 > 0 (공사장/보호구역 포함)
candidates = df[df["composite_v3"] > 0].copy()
# 보호구역 내 거점 제외 (score_protected < 0.50: 드론 이착륙 위험)
if "score_protected" in candidates.columns:
    before = len(candidates)
    candidates = candidates[candidates["score_protected"] >= 0.50]
    print(f"  보호구역 제외: {before - len(candidates)}개 셀 제거")
# 공사장 활발한 지역 제외 (score_construction < 0.40)
if "score_construction" in candidates.columns:
    before = len(candidates)
    candidates = candidates[candidates["score_construction"] >= 0.40]
    print(f"  공사장 밀집 제외: {before - len(candidates)}개 셀 제거")

candidates = candidates.sort_values("composite_v3", ascending=False)
print(f"  최종 후보지: {len(candidates)}개 셀")

# Zoning별 후보 분포
if "zone" in candidates.columns:
    print(f"\n  [Zoning별 후보 분포]")
    print(candidates["zone"].value_counts().to_string())

# ── 거리 계산 함수 ────────────────────────────────────────────
def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi  = np.radians(lat2 - lat1)
    dlam  = np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlam/2)**2
    return 2 * R * np.arcsin(np.sqrt(a))

# ── Greedy Set Cover ─────────────────────────────────────────
print("\n[STEP 4] Greedy Set Cover 최적화...")

lat_arr = df["lat"].values
lon_arr = df["lon"].values
ds_arr  = df["Ds_v3"].values

selected_hubs = []
covered_mask  = np.zeros(len(df), dtype=bool)
dong_counts   = {}

for step in range(MAX_HUBS):
    best_hub = None
    best_new  = 0
    best_score = -1

    for _, cand in candidates.iterrows():
        dong = cand["ADM_NM"]
        if dong_counts.get(dong, 0) >= MAX_SAME_DONG:
            continue

        dists = haversine_m(lat_arr, lon_arr, cand["lat"], cand["lon"])
        within = dists <= SERVICE_RADIUS_M
        new_hotspots = (~covered_mask) & within & (ds_arr >= ds_threshold)
        new_count = new_hotspots.sum()
        new_demand = ds_arr[new_hotspots].sum()

        # 점수 = 신규 커버 수요 × composite_v3 (드론 운영 가능성) × Ds_v3
        score = new_demand * cand["composite_v3"] * cand["Ds_v3"]

        if score > best_score:
            best_hub   = cand
            best_new   = new_count
            best_score = score
            best_within = within

    if best_hub is None or best_new == 0:
        print(f"  [STEP {step+1}] 더 커버할 핫스팟 없음 — 조기 종료")
        break

    covered_mask |= (best_within & (ds_arr >= ds_threshold))
    dong_counts[best_hub["ADM_NM"]] = dong_counts.get(best_hub["ADM_NM"], 0) + 1

    total_hotspots = (ds_arr >= ds_threshold).sum()
    cov_pct = covered_mask.sum() / total_hotspots

    zone_info = best_hub.get("zone", "N/A") if "zone" in best_hub else "N/A"
    print(f"  [{step+1:2d}] {best_hub['ADM_NM']:<10s} "
          f"Ds3={best_hub['Ds_v3']:.3f} Ra={best_hub['Ra']:.3f} "
          f"cv3={best_hub['composite_v3']:.3f} zone={zone_info} "
          f"+{best_new}셀 → {cov_pct*100:.1f}%")

    selected_hubs.append({
        "step"        : step + 1,
        "h3_index"    : best_hub["h3_index"],
        "lat"         : best_hub["lat"],
        "lon"         : best_hub["lon"],
        "ADM_NM"      : best_hub["ADM_NM"],
        "GU_NM"       : best_hub["GU_NM"],
        "Ds_v3"       : round(best_hub["Ds_v3"], 4),
        "Ra"          : round(best_hub["Ra"], 4),
        "composite_v3": round(best_hub["composite_v3"], 4),
        "score_construction": round(best_hub.get("score_construction", 1.0), 3),
        "score_protected"   : round(best_hub.get("score_protected", 1.0), 3),
        "zone"        : zone_info,
        "new_covered" : int(best_new),
        "coverage_pct": round(cov_pct, 4),
    })

# ── 결과 ────────────────────────────────────────────────────
hubs_v3 = pd.DataFrame(selected_hubs)
final_cov = covered_mask.sum() / (ds_arr >= ds_threshold).sum() * 100

print(f"\n{'='*50}")
print(f"[NB10 v3 결과]")
print(f"  선정 거점 수: {len(hubs_v3)}개")
print(f"  최종 커버리지: {final_cov:.1f}%")

# ── v2 vs v3 비교 ────────────────────────────────────────────
if v2_df is not None:
    print(f"\n[v2 vs v3 비교]")
    v2_cov = v2_df["coverage_pct"].max() * 100
    print(f"  v2 커버리지: {v2_cov:.1f}%  →  v3 커버리지: {final_cov:.1f}%  "
          f"({'↑' if final_cov >= v2_cov else '↓'}{abs(final_cov - v2_cov):.1f}%p)")

    # 거점 변화 확인
    v2_dongs = set(v2_df["ADM_NM"].tolist())
    v3_dongs = set(hubs_v3["ADM_NM"].tolist())
    new_dongs  = v3_dongs - v2_dongs
    kept_dongs = v2_dongs & v3_dongs
    drop_dongs = v2_dongs - v3_dongs

    print(f"  유지 거점: {kept_dongs}")
    print(f"  신규 거점: {new_dongs}")
    print(f"  제외 거점: {drop_dongs}")

    # 비교 CSV
    compare_data = []
    for v in ["v2", "v3"]:
        vdf = v2_df if v == "v2" else hubs_v3
        for _, row in vdf.iterrows():
            compare_data.append({
                "version": v,
                "rank"   : row["step"],
                "dong"   : row["ADM_NM"],
                "gu"     : row["GU_NM"],
                "ds3"    : row["Ds_v3"],
                "ra"     : row["Ra"],
                "composite": row.get("composite_v3", row.get("composite_v2", 0)),
                "coverage_pct": row["coverage_pct"] * 100,
            })
    pd.DataFrame(compare_data).to_csv(
        OUT / "hub_comparison_v2_v3.csv", index=False, encoding="utf-8-sig"
    )
    print(f"  ✅ hub_comparison_v2_v3.csv 저장")

# ── 구별 커버리지 요약 ────────────────────────────────────────
print(f"\n[구별 분포]")
print(hubs_v3.groupby("GU_NM")[["ADM_NM","Ds_v3","Ra","composite_v3"]].agg(
    {"ADM_NM": "count", "Ds_v3": "mean", "Ra": "mean", "composite_v3": "mean"}
).rename(columns={"ADM_NM": "거점수"}).round(3).to_string())

# ── 저장 ─────────────────────────────────────────────────────
hubs_v3.to_csv(OUT / "final_hubs_v3.csv", index=False, encoding="utf-8-sig")
print(f"\n✅ final_hubs_v3.csv 저장")

# ── 시각화 ───────────────────────────────────────────────────
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["axes.unicode_minus"] = False
    try:
        plt.rcParams["font.family"] = "Malgun Gothic"
    except:
        pass

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(f"NB10 v3 — 7레이어 기반 최적 거점 (커버리지 {final_cov:.1f}%)", fontsize=13)

    # 왼쪽: 커버리지 누적 곡선
    ax = axes[0]
    steps = hubs_v3["step"].tolist()
    covs  = [r * 100 for r in hubs_v3["coverage_pct"].tolist()]
    ax.plot(steps, covs, "o-", color="#42A5F5", lw=2, ms=8, label="v3 (7레이어)")
    if v2_df is not None:
        v2_covs = [r * 100 for r in v2_df["coverage_pct"].tolist()]
        ax.plot(v2_df["step"].tolist(), v2_covs, "s--",
                color="#ef5350", lw=1.5, ms=6, alpha=0.7, label="v2 (5레이어)")
    ax.axhline(50, color="gray", ls=":", lw=1, label="목표 50%")
    ax.set_xlabel("거점 선정 순서")
    ax.set_ylabel("핫스팟 커버리지 (%)")
    ax.set_title("커버리지 누적 곡선")
    ax.legend()
    ax.grid(alpha=0.3)
    ax.set_ylim(0, 100)

    # 오른쪽: 거점 지도
    ax2 = axes[1]
    bg = df[df["composite_v3"] > 0]
    sc = ax2.scatter(bg["lon"], bg["lat"], c=bg["Ds_v3"],
                     cmap="YlOrRd", s=2, alpha=0.3, vmin=0, vmax=0.5)
    plt.colorbar(sc, ax=ax2, shrink=0.8, label="Ds_v3")
    ax2.scatter(hubs_v3["lon"], hubs_v3["lat"],
                c="#1565C0", s=180, zorder=5, marker="*", label="v3 거점")
    if v2_df is not None:
        ax2.scatter(v2_df["lon"], v2_df["lat"],
                    c="#ef5350", s=80, zorder=4, marker="^",
                    alpha=0.6, label="v2 거점")
    for _, row in hubs_v3.iterrows():
        ax2.annotate(row["ADM_NM"][:4],
                     (row["lon"], row["lat"]), fontsize=6.5,
                     xytext=(3, 3), textcoords="offset points")
    ax2.set_xlabel("경도")
    ax2.set_ylabel("위도")
    ax2.set_title("거점 위치 (v3 ★ vs v2 ▲)")
    ax2.legend(markerscale=1.5, fontsize=8)
    ax2.grid(alpha=0.2)

    plt.tight_layout()
    plt.savefig(OUT / "hub_selection_v3.png", dpi=150, bbox_inches="tight")
    print("✅ hub_selection_v3.png 저장")
except Exception as e:
    print(f"⚠ 차트 오류: {e}")

print(f"\n✅ NB10 v3 완료! 커버리지: {final_cov:.1f}%")
