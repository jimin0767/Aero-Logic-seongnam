"""
NB12_eta_simulation.py  —  ETA 시뮬레이션 (이착륙 + 신호대기 포함)
====================================================================
기존 NB12 문제: 드론에 2분만 추가, 오토바이 정체 미반영

개선:
  드론  : T_flight + T_takeoff + T_landing + T_hub_handoff
  오토바이: T_road   + T_signal  + T_congestion

산출물 : processed/eta_simulation.csv
         processed/mode_comparison_v2.csv
"""

import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.use("Agg")          # 화면 없이 파일 저장
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# ── 경로 설정 ────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent
OUT  = BASE / "processed"

# ── 한글 폰트 ─────────────────────────────────────────────────────────────────
plt.rcParams["axes.unicode_minus"] = False
for fname in ["Malgun Gothic", "NanumGothic", "AppleGothic"]:
    try:
        fm.findfont(fname, fallback_to_default=False)
        plt.rcParams["font.family"] = fname
        break
    except Exception:
        pass

print("=" * 60)
print("NB12 ETA 시뮬레이션 — 현실적 배송시간 비교")
print("=" * 60)

# ══════════════════════════════════════════════════════════════════════════════
#  ETA 파라미터 정의
# ══════════════════════════════════════════════════════════════════════════════

# ── 드론 파라미터 ─────────────────────────────────────────────────────────────
DRONE = {
    "name"           : "드론",
    "speed_kmh"      : 60,       # 순항 속도
    "takeoff_min"    : 1.0,      # 이륙 준비·상승 시간 (분)
    "landing_min"    : 1.0,      # 착륙·수령 시간 (분)
    "hub_handoff_min": 1.5,      # 허브 하역·포장·출발 준비 (분)
    "wind_penalty_min": 0.5,     # 맞바람 등 기상 지연 평균 (분)
}
DRONE["fixed_overhead_min"] = (
    DRONE["takeoff_min"]
  + DRONE["landing_min"]
  + DRONE["hub_handoff_min"]
  + DRONE["wind_penalty_min"]
)

# ── 로봇 파라미터 (도심 단거리, 드론 착륙 후 연계) ────────────────────────────
ROBOT = {
    "name"              : "로봇 (라스트마일)",
    "speed_kmh"         : 6,        # 보행속도 수준
    "crosswalk_wait_min": 1.0,      # 횡단보도 대기 평균 (회당)
    "elevator_wait_min" : 0.5,      # 엘리베이터 대기 (아파트 등)
    "avg_crosswalks"    : 2,        # 평균 횡단보도 통과 횟수
    "handoff_min"       : 1.0,      # 드론→로봇 연계 하역 시간
}
ROBOT["fixed_overhead_min"] = (
    ROBOT["crosswalk_wait_min"] * ROBOT["avg_crosswalks"]
  + ROBOT["elevator_wait_min"]
  + ROBOT["handoff_min"]
)

# ── 오토바이 파라미터 ─────────────────────────────────────────────────────────
MOTO = {
    "name"            : "오토바이",
    "speed_kmh"       : 25,      # 도심 평균 (신호·정체 포함 실효속도)
    "signal_per_km"   : 2.5,     # km당 평균 신호 횟수
    "avg_signal_wait_min": 0.8,  # 신호 1회 평균 대기 (분)
    "congestion_peak_factor": 1.3,  # 피크타임 정체 배율
    "parking_walk_min": 1.5,     # 주차 후 도보 배달 (분)
}

print("\n[드론 고정 오버헤드]")
print(f"  이륙: {DRONE['takeoff_min']}분")
print(f"  착륙: {DRONE['landing_min']}분")
print(f"  허브 하역: {DRONE['hub_handoff_min']}분")
print(f"  기상지연: {DRONE['wind_penalty_min']}분")
print(f"  → 합계: {DRONE['fixed_overhead_min']}분")

print("\n[로봇 고정 오버헤드]")
print(f"  드론→로봇 연계: {ROBOT['handoff_min']}분")
print(f"  횡단보도 ({ROBOT['avg_crosswalks']}회): {ROBOT['crosswalk_wait_min'] * ROBOT['avg_crosswalks']}분")
print(f"  엘리베이터: {ROBOT['elevator_wait_min']}분")
print(f"  → 합계: {ROBOT['fixed_overhead_min']}분")

# ══════════════════════════════════════════════════════════════════════════════
#  거리별 ETA 계산 함수
# ══════════════════════════════════════════════════════════════════════════════

def eta_drone(dist_km: float) -> float:
    """드론 순수 비행 + 고정 오버헤드"""
    t_flight = dist_km / DRONE["speed_kmh"] * 60
    return t_flight + DRONE["fixed_overhead_min"]


def eta_drone_robot(dist_drone_km: float, dist_robot_km: float = 0.3) -> float:
    """드론(장거리) + 로봇(라스트마일 0.3km 기본) 연계 배송"""
    t_drone = eta_drone(dist_drone_km)
    t_robot = dist_robot_km / ROBOT["speed_kmh"] * 60 + ROBOT["fixed_overhead_min"]
    return t_drone + t_robot  # 연계 총 시간 (병렬 X, 순차)


def eta_moto(dist_km: float, peak: bool = False) -> float:
    """오토바이: 실효속도 기반 + 신호대기 + 피크타임 정체"""
    t_road   = dist_km / MOTO["speed_kmh"] * 60
    t_signal = dist_km * MOTO["signal_per_km"] * MOTO["avg_signal_wait_min"]
    t_park   = MOTO["parking_walk_min"]
    total    = t_road + t_signal + t_park
    if peak:
        total *= MOTO["congestion_peak_factor"]
    return total


# ══════════════════════════════════════════════════════════════════════════════
#  거리 구간별 ETA 시뮬레이션
# ══════════════════════════════════════════════════════════════════════════════

dist_bands = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
records = []
for d in dist_bands:
    records.append({
        "거리(km)"      : d,
        "드론(분)"      : round(eta_drone(d), 2),
        "드론+로봇(분)" : round(eta_drone_robot(d - 0.3, 0.3) if d > 0.3 else eta_drone(d), 2),
        "오토바이(분)"  : round(eta_moto(d, peak=False), 2),
        "오토바이_피크(분)": round(eta_moto(d, peak=True), 2),
    })

df_eta = pd.DataFrame(records)
print("\n[거리별 ETA 비교 (분)]")
print(df_eta.to_string(index=False))

# 손익분기점: 드론이 오토바이보다 빨라지는 거리
# 해석: 고정 오버헤드 때문에 단거리는 오토바이가 유리할 수 있음
breakeven_distances = []
for d in np.arange(0.1, 10.0, 0.05):
    if eta_drone(d) < eta_moto(d, peak=False):
        breakeven_distances.append(d)
        break

if breakeven_distances:
    print(f"\n손익분기점: {breakeven_distances[0]:.1f}km 이상에서 드론이 오토바이보다 빠름")
else:
    print("\n분석 범위 내 손익분기점 없음")

# 피크타임 손익분기점
breakeven_peak = []
for d in np.arange(0.1, 10.0, 0.05):
    if eta_drone(d) < eta_moto(d, peak=True):
        breakeven_peak.append(d)
        break
if breakeven_peak:
    print(f"피크타임 손익분기점: {breakeven_peak[0]:.1f}km 이상")

# ══════════════════════════════════════════════════════════════════════════════
#  실제 허브 경로 데이터에 ETA 적용
# ══════════════════════════════════════════════════════════════════════════════

print("\n[실제 허브 경로 ETA 적용...]")
hub_stats_path = OUT / "hub_delivery_stats.csv"
if hub_stats_path.exists():
    hub = pd.read_csv(hub_stats_path)
    print(f"  허브 경로 데이터: {len(hub)}개 허브")
    print(f"  컬럼: {hub.columns.tolist()}")

    if "avg_distance" in hub.columns:
        hub["avg_dist_km"] = hub["avg_distance"] / 1000  # m → km
        hub["ETA_드론(분)"]        = hub["avg_dist_km"].apply(eta_drone).round(2)
        hub["ETA_드론+로봇(분)"]   = hub["avg_dist_km"].apply(
            lambda d: eta_drone_robot(max(d - 0.3, 0.1), 0.3)).round(2)
        hub["ETA_오토바이(분)"]    = hub["avg_dist_km"].apply(lambda d: eta_moto(d, False)).round(2)
        hub["ETA_오토바이_피크(분)"] = hub["avg_dist_km"].apply(lambda d: eta_moto(d, True)).round(2)
        hub["시간단축_vs_오토바이(분)"] = (hub["ETA_오토바이(분)"] - hub["ETA_드론(분)"]).round(2)

        show_cols = ["hub_name", "avg_dist_km",
                     "ETA_드론(분)", "ETA_드론+로봇(분)",
                     "ETA_오토바이(분)", "ETA_오토바이_피크(분)",
                     "시간단축_vs_오토바이(분)"]
        print(hub[show_cols].to_string(index=False))

        hub.to_csv(OUT / "hub_eta_comparison.csv", index=False, encoding="utf-8-sig")
        print(f"\n  ✅ hub_eta_comparison.csv 저장")
else:
    print(f"  ⚠ hub_delivery_stats.csv 없음 — 허브별 적용 생략")

# ══════════════════════════════════════════════════════════════════════════════
#  시각화
# ══════════════════════════════════════════════════════════════════════════════

fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle("ETA 시뮬레이션: 거리별 배송 시간 비교 (이착륙·신호대기 포함)", fontsize=13)

dist_arr = np.arange(0.3, 6.0, 0.1)
eta_d   = [eta_drone(d) for d in dist_arr]
eta_dr  = [eta_drone_robot(max(d-0.3,0.1), 0.3) for d in dist_arr]
eta_m   = [eta_moto(d, False) for d in dist_arr]
eta_mp  = [eta_moto(d, True)  for d in dist_arr]

ax = axes[0]
ax.plot(dist_arr, eta_d,  color="#1E88E5", lw=2, label="드론")
ax.plot(dist_arr, eta_dr, color="#43A047", lw=2, ls="--", label="드론+로봇(연계)")
ax.plot(dist_arr, eta_m,  color="#E53935", lw=2, label="오토바이")
ax.plot(dist_arr, eta_mp, color="#FF8F00", lw=2, ls=":", label="오토바이(피크)")
ax.set_xlabel("거리 (km)")
ax.set_ylabel("ETA (분)")
ax.set_title("거리별 ETA 곡선")
ax.legend()
ax.grid(alpha=0.3)
ax.set_ylim(0, max(eta_mp) * 1.1)

# ── 막대차트 ──────────────────────────────────────────────────────────────────
ax2 = axes[1]
x   = np.arange(len(dist_bands))
w   = 0.2
ax2.bar(x - 1.5*w, [eta_drone(d)         for d in dist_bands], w, label="드론",           color="#1E88E5", alpha=0.85)
ax2.bar(x - 0.5*w, [eta_drone_robot(max(d-0.3,0.1),0.3) for d in dist_bands], w,
        label="드론+로봇", color="#43A047", alpha=0.85)
ax2.bar(x + 0.5*w, [eta_moto(d, False)   for d in dist_bands], w, label="오토바이",       color="#E53935", alpha=0.85)
ax2.bar(x + 1.5*w, [eta_moto(d, True)    for d in dist_bands], w, label="오토바이(피크)", color="#FF8F00", alpha=0.85)
ax2.set_xticks(x)
ax2.set_xticklabels([f"{d}km" for d in dist_bands])
ax2.set_ylabel("ETA (분)")
ax2.set_title("거리 구간별 ETA 막대 비교")
ax2.legend()
ax2.grid(axis="y", alpha=0.3)

plt.tight_layout()
out_fig = OUT / "eta_simulation_chart.png"
plt.savefig(out_fig, dpi=150, bbox_inches="tight")
print(f"\n  ✅ 차트 저장: {out_fig}")

# ── 결과 CSV 저장 ──────────────────────────────────────────────────────────────
df_eta.to_csv(OUT / "eta_simulation.csv", index=False, encoding="utf-8-sig")
print(f"  ✅ eta_simulation.csv 저장")

# ── mode_comparison_v2.csv (대시보드 업데이트용) ──────────────────────────────
avg_d = 1.5  # 평균 배송 거리 (km)
mode_v2 = pd.DataFrame({
    "지표"  : ["ETA (분, 평균 1.5km)", "ETA (분, 피크 1.5km)",
               "이착륙/신호 오버헤드 (분)", "탄소 배출 (gCO₂/건)",
               "야간 운영", "경사지 대응"],
    "오토바이" : [f"{eta_moto(avg_d, False):.1f}", f"{eta_moto(avg_d, True):.1f}",
                  f"{MOTO['avg_signal_wait_min']*MOTO['signal_per_km']*avg_d + MOTO['parking_walk_min']:.1f}",
                  "186", "0.7", "0.9"],
    "드론"    : [f"{eta_drone(avg_d):.1f}", f"{eta_drone(avg_d):.1f}",
                 f"{DRONE['fixed_overhead_min']:.1f}",
                 "12", "0.95", "0.6"],
    "드론+로봇": [f"{eta_drone_robot(avg_d-0.3, 0.3):.1f}",
                  f"{eta_drone_robot(avg_d-0.3, 0.3):.1f}",
                  f"{DRONE['fixed_overhead_min']+ROBOT['fixed_overhead_min']:.1f}",
                  "12", "0.95", "0.6"],
})
mode_v2.to_csv(OUT / "mode_comparison_v2.csv", index=False, encoding="utf-8-sig")
print(f"  ✅ mode_comparison_v2.csv 저장")

print("\n✅ ETA 시뮬레이션 완료!")
print(f"   드론 고정오버헤드: {DRONE['fixed_overhead_min']}분")
print(f"   드론+로봇 오버헤드: {DRONE['fixed_overhead_min']+ROBOT['fixed_overhead_min']}분")
print(f"   오토바이 신호대기(1.5km): {MOTO['avg_signal_wait_min']*MOTO['signal_per_km']*1.5:.1f}분")
