"""
NB13b_weather_simulation.py
==============================
Monte Carlo 기상 시뮬레이션 — 드론 가용률 및 Fallback 로봇 전환

회의 결의:
  - 풍속 10m/s 이상: 드론 운항 불가
  - 강수량 5mm/h 이상: 드론 운항 불가
  - 비행 불가 시 로봇 전 구간 배송으로 자동 전환 (Fallback)
  - Monte Carlo 10,000회 시뮬레이션

성남시 기상 통계 (2020-2024 기상청 관측값 기반):
  - 연간 강풍(10m/s↑) 일수: 약 65일 → P_wind_fail = 65/365
  - 연간 강우(5mm/h↑) 시간: 약 180h → P_rain_fail = 180/8760
  - 동시 발생 가정: 독립 이벤트

산출물:
  processed/weather_sim_result.csv
  processed/weather_sim_chart.png
"""

import numpy as np
import pandas as pd
from pathlib import Path
import json
import warnings
warnings.filterwarnings("ignore")

BASE = Path(r"C:\Users\pasoh\OneDrive\문서\GitHub\Aero-Logic-seongnam")
OUT  = BASE / "processed"

print("=" * 60)
print("NB13b — Monte Carlo 기상 시뮬레이션")
print("=" * 60)

# ── 기상 파라미터 (성남시 기상청 통계 기반) ───────────────────
WEATHER_PARAMS = {
    "P_wind_fail"  : 65 / 365,       # 강풍(10m/s↑) 일 확률 ≈ 17.8%
    "P_rain_fail"  : 180 / 8760,     # 강우(5mm/h↑) 시간 확률 ≈ 2.1%
    "P_vis_fail"   : 0.03,           # 시정 불량 확률 ≈ 3%
}

# 드론 비행 가능 확률 (세 조건 모두 OK여야 함)
P_drone_ok = (
    (1 - WEATHER_PARAMS["P_wind_fail"]) *
    (1 - WEATHER_PARAMS["P_rain_fail"]) *
    (1 - WEATHER_PARAMS["P_vis_fail"])
)

print(f"\n[기상 파라미터]")
print(f"  강풍 실패 확률: {WEATHER_PARAMS['P_wind_fail']*100:.1f}%")
print(f"  강우 실패 확률: {WEATHER_PARAMS['P_rain_fail']*100:.1f}%")
print(f"  시정 실패 확률: {WEATHER_PARAMS['P_vis_fail']*100:.1f}%")
print(f"  → 드론 가용률: {P_drone_ok*100:.1f}%")

# ── ETA 파라미터 ─────────────────────────────────────────────
ETA_PARAMS = {
    # 드론 모드 (가용 시)
    "drone_speed_kmh"     : 60,
    "drone_takeoff_min"   : 2.0,
    "drone_landing_min"   : 2.0,
    "drone_handoff_min"   : 1.5,

    # 로봇 라스트마일
    "robot_speed_kmh"     : 5,
    "robot_last_km"       : 0.3,

    # 오토바이 (비교 기준)
    "moto_speed_kmh"      : 25,
    "moto_signal_wait_min": 3.0,
    "moto_peak_factor"    : 1.4,

    # 배송 거리 분포 (km)
    "mean_dist_km"        : 2.5,
    "std_dist_km"         : 1.0,
}

# ── Monte Carlo 시뮬레이션 ────────────────────────────────────
N = 10_000
np.random.seed(42)

print(f"\n[Monte Carlo N={N:,}회 시뮬레이션 중...]")

results = []
for i in range(N):
    # 배송 거리 샘플링
    dist = max(0.5, np.random.normal(ETA_PARAMS["mean_dist_km"],
                                      ETA_PARAMS["std_dist_km"]))
    # 피크타임 여부 (30% 확률)
    is_peak = np.random.random() < 0.30

    # 드론 가용 여부
    drone_available = np.random.random() < P_drone_ok

    if drone_available:
        # 드론 + 로봇 모드
        fly_time = dist / ETA_PARAMS["drone_speed_kmh"] * 60
        robot_time = ETA_PARAMS["robot_last_km"] / ETA_PARAMS["robot_speed_kmh"] * 60
        overhead = (ETA_PARAMS["drone_takeoff_min"] +
                    ETA_PARAMS["drone_landing_min"] +
                    ETA_PARAMS["drone_handoff_min"])
        total_min = fly_time + overhead + robot_time
        mode = "드론+로봇"
        # 탄소 (전기 드론 + 전기 로봇)
        carbon_kg = dist * 0.021 + ETA_PARAMS["robot_last_km"] * 0.008
    else:
        # Fallback: 로봇 전 구간
        robot_full_time = dist / ETA_PARAMS["robot_speed_kmh"] * 60
        total_min = robot_full_time
        mode = "로봇(Fallback)"
        carbon_kg = dist * 0.008

    # 오토바이 ETA (비교)
    peak_f = ETA_PARAMS["moto_peak_factor"] if is_peak else 1.0
    moto_time = (dist / ETA_PARAMS["moto_speed_kmh"] * 60 * peak_f
                 + ETA_PARAMS["moto_signal_wait_min"])
    moto_carbon = dist * 0.145

    results.append({
        "sim_id"         : i,
        "dist_km"        : round(dist, 2),
        "is_peak"        : is_peak,
        "drone_available": drone_available,
        "mode"           : mode,
        "eta_min"        : round(total_min, 1),
        "moto_eta_min"   : round(moto_time, 1),
        "eta_saving_min" : round(moto_time - total_min, 1),
        "carbon_kg"      : round(carbon_kg, 4),
        "moto_carbon_kg" : round(moto_carbon, 4),
        "carbon_saving_kg": round(moto_carbon - carbon_kg, 4),
    })

sim_df = pd.DataFrame(results)

# ── 결과 집계 ────────────────────────────────────────────────
print("\n[시뮬레이션 결과 요약]")
drone_ratio = sim_df["drone_available"].mean()
fallback_ratio = 1 - drone_ratio

print(f"  드론+로봇 배송:    {drone_ratio*100:.1f}% ({int(drone_ratio*N):,}건)")
print(f"  로봇 Fallback:    {fallback_ratio*100:.1f}% ({int(fallback_ratio*N):,}건)")

overall_eta   = sim_df["eta_min"].mean()
overall_moto  = sim_df["moto_eta_min"].mean()
avg_saving_t  = sim_df["eta_saving_min"].mean()
avg_carbon    = sim_df["carbon_kg"].mean()
avg_moto_c    = sim_df["moto_carbon_kg"].mean()
avg_carbon_s  = sim_df["carbon_saving_kg"].mean()

t_efficiency = avg_saving_t / overall_moto * 100
e_reduction  = avg_carbon_s / avg_moto_c * 100

print(f"\n  평균 ETA (드론+로봇): {overall_eta:.1f}분")
print(f"  평균 ETA (오토바이):  {overall_moto:.1f}분")
print(f"  평균 시간 단축:       {avg_saving_t:.1f}분 ({t_efficiency:.1f}%)")
print(f"\n  평균 탄소 (드론+로봇): {avg_carbon:.4f} kgCO2/배송")
print(f"  평균 탄소 (오토바이):  {avg_moto_c:.4f} kgCO2/배송")
print(f"  평균 탄소 절감:        {avg_carbon_s:.4f} kgCO2 ({e_reduction:.1f}%)")

# 연간 추정 (하루 1,000건 가정)
DAILY_DELIVERIES = 1000
annual_carbon_save = avg_carbon_s * DAILY_DELIVERIES * 365 / 1000  # 톤CO2/년
print(f"\n  [연간 추정 — 하루 {DAILY_DELIVERIES:,}건]")
print(f"  탄소 절감: {annual_carbon_save:.1f} 톤CO2/년")
print(f"  ≈ 소나무 {int(annual_carbon_save * 1000 / 6.6):,}그루 효과")

# ── 요약 저장 ────────────────────────────────────────────────
summary = {
    "N_simulations"         : N,
    "P_drone_available"     : round(P_drone_ok, 4),
    "drone_usage_pct"       : round(drone_ratio * 100, 1),
    "fallback_robot_pct"    : round(fallback_ratio * 100, 1),
    "avg_eta_drone_robot"   : round(overall_eta, 1),
    "avg_eta_motorcycle"    : round(overall_moto, 1),
    "avg_time_saving_min"   : round(avg_saving_t, 1),
    "T_efficiency_pct"      : round(t_efficiency, 1),
    "avg_carbon_drone_robot": round(avg_carbon, 4),
    "avg_carbon_motorcycle" : round(avg_moto_c, 4),
    "avg_carbon_saving_kg"  : round(avg_carbon_s, 4),
    "E_reduction_pct"       : round(e_reduction, 1),
    "annual_carbon_ton_1000d": round(annual_carbon_save, 1),
}

# 월별 집계 (피크/비피크)
percentiles = sim_df["eta_min"].quantile([0.1, 0.5, 0.9]).to_dict()
summary["eta_p10"] = round(percentiles[0.1], 1)
summary["eta_p50"] = round(percentiles[0.5], 1)
summary["eta_p90"] = round(percentiles[0.9], 1)

pd.DataFrame([summary]).to_csv(OUT / "weather_sim_result.csv",
                                index=False, encoding="utf-8-sig")
print(f"\n✅ weather_sim_result.csv 저장")

# ── 히스토그램 시각화 ─────────────────────────────────────────
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["axes.unicode_minus"] = False
    try:
        plt.rcParams["font.family"] = "Malgun Gothic"
    except:
        pass

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle("NB13b — Monte Carlo 기상 시뮬레이션 결과 (N=10,000)", fontsize=13)

    # ETA 분포
    ax = axes[0]
    ax.hist(sim_df[sim_df["drone_available"]]["eta_min"],
            bins=50, color="#42A5F5", alpha=0.7, label="드론+로봇")
    ax.hist(sim_df[~sim_df["drone_available"]]["eta_min"],
            bins=30, color="#66BB6A", alpha=0.7, label="로봇Fallback")
    ax.hist(sim_df["moto_eta_min"], bins=50,
            color="#ef5350", alpha=0.4, label="오토바이")
    ax.axvline(overall_eta, color="blue", ls="--", lw=1.5, label=f"드론 평균 {overall_eta:.0f}분")
    ax.axvline(overall_moto, color="red", ls="--", lw=1.5, label=f"오토바이 평균 {overall_moto:.0f}분")
    ax.set_xlabel("ETA (분)")
    ax.set_ylabel("빈도")
    ax.set_title("ETA 분포")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # 탄소 절감 분포
    ax2 = axes[1]
    ax2.hist(sim_df["carbon_saving_kg"], bins=60,
             color="#FFA726", alpha=0.85, edgecolor="white")
    ax2.axvline(avg_carbon_s, color="red", ls="--",
                label=f"평균 {avg_carbon_s:.3f}kg")
    ax2.set_xlabel("탄소 절감량 (kgCO2/배송)")
    ax2.set_ylabel("빈도")
    ax2.set_title(f"탄소 절감 분포 (평균 {e_reduction:.1f}% 감소)")
    ax2.legend()
    ax2.grid(alpha=0.3)

    # 시간 절감 분포
    ax3 = axes[2]
    colors_mode = sim_df["drone_available"].map({True: "#42A5F5", False: "#66BB6A"})
    ax3.scatter(sim_df["dist_km"], sim_df["eta_saving_min"],
                c=colors_mode, alpha=0.15, s=5)
    ax3.axhline(0, color="gray", ls="-", lw=0.8)
    ax3.axhline(avg_saving_t, color="blue", ls="--",
                lw=1.5, label=f"평균 {avg_saving_t:.1f}분 단축")
    ax3.set_xlabel("배송 거리 (km)")
    ax3.set_ylabel("시간 단축 (분)")
    ax3.set_title(f"거리별 시간 단축 효과 (평균 {t_efficiency:.1f}%)")
    ax3.legend()
    ax3.grid(alpha=0.3)

    import matplotlib.patches as mpatches
    p1 = mpatches.Patch(color="#42A5F5", label="드론+로봇")
    p2 = mpatches.Patch(color="#66BB6A", label="로봇Fallback")
    axes[2].legend(handles=[p1, p2] + axes[2].get_legend_handles_labels()[0],
                   fontsize=8)

    plt.tight_layout()
    plt.savefig(OUT / "weather_sim_chart.png", dpi=150, bbox_inches="tight")
    print("✅ weather_sim_chart.png 저장")
except Exception as e:
    print(f"⚠ 차트 오류: {e}")

print(f"\n✅ NB13b 완료!")
print(f"   드론 가용률: {P_drone_ok*100:.1f}% | 시간절감: {t_efficiency:.1f}% | 탄소절감: {e_reduction:.1f}%")

# 요약 딕셔너리 외부 접근용 저장
import json
(OUT / "weather_sim_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("✅ weather_sim_summary.json 저장")
