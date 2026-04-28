"""
NB14_esg_efficiency_index.py
==============================
탄소 배출 절감량($E_{reduction}$) 및 시간 단축 효율($T_{efficiency}$) 공식화

회의 결의:
  - 기존 오토바이 배송 대비 드론+로봇 배송의 ESG 가치 정량화
  - 온실가스 종합정보센터 배출계수 활용

배출계수 출처:
  - 오토바이(휘발유): 0.1445 kgCO2/km (국토연구원 2023)
  - 전기 드론: 0.0210 kgCO2/km (kWh당 0.4781 kgCO2, 한국 전력 믹스 2023)
  - 전기 로봇: 0.0079 kgCO2/km (드론 대비 저전력)

공식:
  E_motorcycle   = d × 0.1445
  E_drone_robot  = d_fly × 0.0210 + d_last × 0.0079
  E_reduction    = E_motorcycle - E_drone_robot
  E_reduction%   = E_reduction / E_motorcycle × 100

  T_efficiency   = (t_moto - t_drone_robot) / t_moto × 100 (%)

산출물:
  processed/esg_index.csv
  processed/esg_chart.png
  assets/js/esg.js
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json
import warnings
warnings.filterwarnings("ignore")

BASE = Path(r"C:\Users\pasoh\OneDrive\문서\GitHub\Aero-Logic-seongnam")
OUT  = BASE / "processed"

print("=" * 60)
print("NB14 — ESG 효율성 지수 (탄소절감 + 시간효율)")
print("=" * 60)

# ── 배출계수 상수 ────────────────────────────────────────────
EMISSION = {
    "motorcycle"   : 0.1445,   # kgCO2/km (휘발유 오토바이)
    "drone"        : 0.0210,   # kgCO2/km (전기 드론, 한국 전력 믹스)
    "robot"        : 0.0079,   # kgCO2/km (전기 배송 로봇)
    "ev_car"       : 0.0321,   # kgCO2/km (전기차 참고용)
}

# ── 배송 시나리오 설정 ────────────────────────────────────────
# 성남시 평균 배송 거리 분포 (행정동별 분석 기반)
SCENARIOS = [
    {"name": "단거리 (1km)", "d_fly": 0.7,  "d_last": 0.3,
     "t_moto_min": 8.0,  "t_drone_min": 6.5},
    {"name": "중거리 (2.5km)", "d_fly": 2.2, "d_last": 0.3,
     "t_moto_min": 15.0, "t_drone_min": 9.0},
    {"name": "장거리 (4km)", "d_fly": 3.7,  "d_last": 0.3,
     "t_moto_min": 22.0, "t_drone_min": 12.5},
    {"name": "산간 (3km)", "d_fly": 3.0,   "d_last": 0.0,
     "t_moto_min": 35.0, "t_drone_min": 11.0},  # 오토바이 경로 우회
    {"name": "피크타임 (2.5km)", "d_fly": 2.2, "d_last": 0.3,
     "t_moto_min": 21.0, "t_drone_min": 9.0},   # 오토바이 혼잡
]

print("\n[시나리오별 ESG 지수 계산]")
esg_results = []

for sc in SCENARIOS:
    d_fly  = sc["d_fly"]
    d_last = sc["d_last"]
    d_total = d_fly + d_last

    # 탄소 계산
    e_moto        = d_total * EMISSION["motorcycle"]
    e_drone_robot = d_fly * EMISSION["drone"] + d_last * EMISSION["robot"]
    e_reduction   = e_moto - e_drone_robot
    e_reduction_pct = e_reduction / e_moto * 100

    # 시간 계산
    t_moto  = sc["t_moto_min"]
    t_drone = sc["t_drone_min"]
    t_saving = t_moto - t_drone
    t_efficiency = t_saving / t_moto * 100

    result = {
        "시나리오"          : sc["name"],
        "총_거리_km"        : d_total,
        "드론_비행_km"      : d_fly,
        "로봇_라스트마일_km": d_last,
        "E_moto_kg"         : round(e_moto, 4),
        "E_drone_robot_kg"  : round(e_drone_robot, 4),
        "E_reduction_kg"    : round(e_reduction, 4),
        "E_reduction_pct"   : round(e_reduction_pct, 1),
        "T_moto_min"        : t_moto,
        "T_drone_robot_min" : t_drone,
        "T_saving_min"      : round(t_saving, 1),
        "T_efficiency_pct"  : round(t_efficiency, 1),
    }
    esg_results.append(result)

    print(f"\n  [{sc['name']}]")
    print(f"    탄소 절감: {e_reduction:.4f} kgCO2 ({e_reduction_pct:.1f}%)")
    print(f"    시간 단축: {t_saving:.1f}분 ({t_efficiency:.1f}%)")

esg_df = pd.DataFrame(esg_results)

# ── 가중 평균 ESG 지수 ────────────────────────────────────────
# 배송 비중 가중치 (성남시 배송 패턴 추정)
WEIGHTS = [0.25, 0.40, 0.15, 0.10, 0.10]  # 단거리/중거리/장거리/산간/피크

E_red_weighted = np.average(esg_df["E_reduction_pct"], weights=WEIGHTS)
T_eff_weighted = np.average(esg_df["T_efficiency_pct"], weights=WEIGHTS)

print(f"\n{'='*50}")
print(f"[가중 평균 ESG 지수]")
print(f"  $E_{{reduction}}$ = {E_red_weighted:.1f}% (탄소 절감률)")
print(f"  $T_{{efficiency}}$ = {T_eff_weighted:.1f}% (시간 단축률)")

# ── 연간 규모 추정 ────────────────────────────────────────────
ANNUAL_DELIVERIES = [100_000, 365_000, 1_000_000]
avg_e_saving = np.average(esg_df["E_reduction_kg"], weights=WEIGHTS)
avg_t_saving = np.average(esg_df["T_saving_min"], weights=WEIGHTS)

print(f"\n[연간 규모 추정]")
print(f"  건당 평균 탄소 절감: {avg_e_saving:.4f} kgCO2")
print(f"  건당 평균 시간 단축: {avg_t_saving:.1f}분")
print(f"\n  {'연간 배송량':>15s} | {'탄소절감(톤CO2)':>15s} | {'소나무 효과(그루)':>18s}")
print(f"  {'-'*55}")
for ann in ANNUAL_DELIVERIES:
    ton = avg_e_saving * ann / 1000
    trees = int(ton * 1000 / 6.6)
    print(f"  {ann:>15,}건 | {ton:>15.1f}톤     | {trees:>18,}그루")

# ── 기상 시뮬레이션 결과 결합 ─────────────────────────────────
weather_json_path = OUT / "weather_sim_summary.json"
if weather_json_path.exists():
    weather_summary = json.loads(weather_json_path.read_text(encoding="utf-8"))
    P_drone = weather_summary["P_drone_available"]
    print(f"\n[기상 가용률 반영]")
    print(f"  드론 가용 확률: {P_drone*100:.1f}%")
    print(f"  실효 E_reduction: {E_red_weighted * P_drone:.1f}% (기상 불가 시 로봇 Fallback)")
    effective_e = E_red_weighted * P_drone + \
        (1 - P_drone) * np.average(
            esg_df["E_reduction_pct"].apply(
                lambda x: x * 0.3 if x > 0 else 0  # 로봇 Fallback: 30% 수준
            ), weights=WEIGHTS
        )
    print(f"  Fallback 포함 실효 절감률: {effective_e:.1f}%")

# ── 구역별 ESG 기대값 (Zoning 결합) ─────────────────────────
zones_path = OUT / "delivery_zones.csv"
if zones_path.exists():
    zones_df = pd.read_csv(zones_path)
    zone_esg = zones_df.groupby("zone").agg(
        cell_count=("h3_index", "count"),
        avg_ds3=("Ds_v3", "mean"),
        avg_ra=("Ra", "mean"),
    ).round(3)
    e_red_map = {
        "드론전용" : round(E_red_weighted * 0.90, 1),
        "로봇전용" : round(E_red_weighted * 0.45, 1),
        "Hybrid"   : round(E_red_weighted * 0.85, 1),
        "일반"     : round(E_red_weighted * 0.70, 1),
    }
    zone_esg["E_red_pct"] = zone_esg.index.map(e_red_map).fillna(0)
    print(f"\n[구역별 ESG 기대 절감률]")
    print(zone_esg[["cell_count","E_red_pct"]].to_string())

# ── 저장 ─────────────────────────────────────────────────────
esg_df.to_csv(OUT / "esg_index.csv", index=False, encoding="utf-8-sig")
print(f"\n✅ esg_index.csv 저장")

# ── esg.js 생성 ───────────────────────────────────────────────
esg_summary_for_js = {
    "E_reduction_pct"    : round(E_red_weighted, 1),
    "T_efficiency_pct"   : round(T_eff_weighted, 1),
    "avg_carbon_save_kg" : round(avg_e_saving, 4),
    "avg_time_save_min"  : round(avg_t_saving, 1),
    "annual_carbon_1M_ton": round(avg_e_saving * 1_000_000 / 1000, 1),
    "scenarios"          : esg_results,
    "emission_factors"   : EMISSION,
    "formula"            : {
        "E_reduction" : "E_moto - (d_fly×0.021 + d_last×0.008)",
        "T_efficiency": "(t_moto - t_drone_robot) / t_moto × 100",
    }
}

if weather_json_path.exists():
    esg_summary_for_js["weather"] = {
        "P_drone_available": round(P_drone * 100, 1),
        "fallback_pct"     : round((1 - P_drone) * 100, 1),
    }

esg_js = f"""// Auto-generated by NB14_esg_efficiency_index.py
// ESG 탄소절감 + 시간효율 지수
// 출처: 온실가스 종합정보센터 배출계수 (2023), 기상청 관측자료
const ESG = {json.dumps(esg_summary_for_js, ensure_ascii=False, indent=2)};
"""
(BASE / "assets" / "js" / "esg.js").write_text(esg_js, encoding="utf-8")
print("✅ esg.js 저장")

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
    fig.suptitle("NB14 — ESG 효율성 지수: 탄소절감 & 시간단축", fontsize=13)

    sc_names = [s["시나리오"] for s in esg_results]
    e_vals   = [s["E_reduction_pct"] for s in esg_results]
    t_vals   = [s["T_efficiency_pct"] for s in esg_results]

    # 탄소 절감률
    ax = axes[0]
    bars = ax.barh(sc_names, e_vals, color="#FFA726", alpha=0.85, edgecolor="white")
    ax.axvline(E_red_weighted, color="red", ls="--", lw=1.5,
               label=f"가중 평균 {E_red_weighted:.1f}%")
    for bar, val in zip(bars, e_vals):
        ax.text(val + 0.3, bar.get_y() + bar.get_height()/2,
                f"{val:.1f}%", va="center", fontsize=9)
    ax.set_xlabel("탄소 배출 절감률 (%)")
    ax.set_title(f"$E_{{reduction}}$ = {E_red_weighted:.1f}% (가중 평균)")
    ax.legend()
    ax.grid(axis="x", alpha=0.3)

    # 시간 단축률
    ax2 = axes[1]
    bars2 = ax2.barh(sc_names, t_vals, color="#42A5F5", alpha=0.85, edgecolor="white")
    ax2.axvline(T_eff_weighted, color="red", ls="--", lw=1.5,
                label=f"가중 평균 {T_eff_weighted:.1f}%")
    for bar, val in zip(bars2, t_vals):
        ax2.text(val + 0.3, bar.get_y() + bar.get_height()/2,
                 f"{val:.1f}%", va="center", fontsize=9)
    ax2.set_xlabel("배송 시간 단축률 (%)")
    ax2.set_title(f"$T_{{efficiency}}$ = {T_eff_weighted:.1f}% (가중 평균)")
    ax2.legend()
    ax2.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUT / "esg_chart.png", dpi=150, bbox_inches="tight")
    print("✅ esg_chart.png 저장")
except Exception as e:
    print(f"⚠ 차트 오류: {e}")

print(f"\n✅ NB14 완료!")
print(f"   E_reduction = {E_red_weighted:.1f}%  |  T_efficiency = {T_eff_weighted:.1f}%")
