"""
NB14_esg_efficiency_index_v2.py
=================================
효율성 지수 E 완성본 (분모 Cost_operation 추가)

공식:
  E = (ΔT × ω_time + ΔC × ω_carbon) / Cost_operation

  ΔT     : 오토바이 대비 시간 단축 (분)
  ΔC     : 오토바이 대비 탄소 절감 (kgCO2)
  ω_time : 0.60 (시간 가중치)
  ω_carbon: 0.40 (탄소 가중치)

  Cost_operation (원/배송건):
    드론+로봇: 2,200원  (전기료 800 + 정비 700 + 감가 700)
    로봇 Fallback: 700원  (전기료 200 + 정비 300 + 감가 200)
    오토바이:  3,500원  (유류비 1,200 + 배달원 인건비 2,000 + 유지 300)

  단위 통일을 위해 분자 화폐화:
    ΔT_value = ΔT(분) × (15,000원/시간 ÷ 60) = ΔT × 250 원
    ΔC_value = ΔC(kg) × 30원/kg (한국 탄소크레딧 ~30,000원/tCO2)

  E = (ΔT × 250 × 0.6 + ΔC × 30 × 0.4) / Cost_op
    = 배송 1건당 창출 가치(원) / 운영비용(원)

  E > 1.0 → 비용보다 창출 가치 큼 (긍정적)
  E < 1.0 → 비용이 가치보다 큼 (개선 필요)

산출물:
  processed/esg_index_v2.csv
  processed/esg_chart_v2.png
  assets/js/esg.js  (업데이트)
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

BASE = Path(r"C:\Users\pasoh\OneDrive\문서\GitHub\Aero-Logic-seongnam")
OUT  = BASE / "processed"

print("=" * 60)
print("NB14 v2 — 효율성 지수 E 완성 (Cost_operation 분모 추가)")
print("=" * 60)

# ── 상수 정의 ─────────────────────────────────────────────────
OMEGA_TIME   = 0.60
OMEGA_CARBON = 0.40
WAGE_PER_MIN = 250       # 원/분 (시급 15,000원 기준)
CARBON_PRICE = 30        # 원/kgCO2 (탄소크레딧 30,000원/tCO2)

COST_OP = {
    "드론+로봇"      : 2200,   # 원/배송
    "로봇Fallback"   : 700,
    "오토바이"       : 3500,
}

EMISSION = {
    "motorcycle": 0.1445,
    "drone"     : 0.0210,
    "robot"     : 0.0079,
}

print(f"\n[가중치]  ω_time={OMEGA_TIME}, ω_carbon={OMEGA_CARBON}")
print(f"[비용]    드론+로봇={COST_OP['드론+로봇']:,}원/건  "
      f"오토바이={COST_OP['오토바이']:,}원/건")
print(f"[단가]    시간: {WAGE_PER_MIN}원/분  "
      f"탄소: {CARBON_PRICE}원/kgCO2")

# ── 시나리오 정의 ─────────────────────────────────────────────
SCENARIOS = [
    {"name": "단거리 (1km)",    "d_fly": 0.7, "d_last": 0.3,
     "t_moto": 8.0,  "t_drone": 6.5, "cost_mode": "드론+로봇"},
    {"name": "중거리 (2.5km)",  "d_fly": 2.2, "d_last": 0.3,
     "t_moto": 15.0, "t_drone": 9.0, "cost_mode": "드론+로봇"},
    {"name": "장거리 (4km)",    "d_fly": 3.7, "d_last": 0.3,
     "t_moto": 22.0, "t_drone": 12.5,"cost_mode": "드론+로봇"},
    {"name": "산간 (3km)",      "d_fly": 3.0, "d_last": 0.0,
     "t_moto": 35.0, "t_drone": 11.0,"cost_mode": "드론+로봇"},
    {"name": "피크타임 (2.5km)","d_fly": 2.2, "d_last": 0.3,
     "t_moto": 21.0, "t_drone": 9.0, "cost_mode": "드론+로봇"},
    {"name": "기상악화 Fallback","d_fly": 2.2, "d_last": 2.2,  # 로봇 전구간
     "t_moto": 15.0, "t_drone": 26.4,"cost_mode": "로봇Fallback"},
]

# ── E 계산 ────────────────────────────────────────────────────
print(f"\n[시나리오별 E 계산]")
print(f"{'시나리오':20s} | ΔT(분) | ΔC(kg) | ΔT가치 | ΔC가치 | Cost | E값  | 판정")
print("-" * 90)

results = []
for sc in SCENARIOS:
    d_total = sc["d_fly"] + sc["d_last"]
    t_moto  = sc["t_moto"]
    t_drone = sc["t_drone"]
    mode    = sc["cost_mode"]

    # 시간 단축
    dT = t_moto - t_drone         # 분 (음수면 로봇이 더 느림)

    # 탄소 절감
    e_moto  = d_total * EMISSION["motorcycle"]
    if mode == "로봇Fallback":
        e_new = sc["d_last"] * EMISSION["robot"]  # 로봇 전 구간
    else:
        e_new = sc["d_fly"] * EMISSION["drone"] + sc["d_last"] * EMISSION["robot"]
    dC = e_moto - e_new

    # 분자: 화폐 가치 (원)
    dT_value = dT * WAGE_PER_MIN * OMEGA_TIME
    dC_value = dC * CARBON_PRICE * OMEGA_CARBON
    numerator = dT_value + dC_value

    # 분모: 운영비용
    cost_op = COST_OP[mode]

    # E 지수
    E = numerator / cost_op

    verdict = "✅ 효율적" if E >= 1.0 else ("⚠ 비용 > 편익" if E >= 0.5 else "❌ 비효율")

    results.append({
        "시나리오"      : sc["name"],
        "배송모드"      : mode,
        "총거리_km"     : d_total,
        "ΔT_분"        : round(dT, 1),
        "ΔC_kg"        : round(dC, 4),
        "ΔT_가치_원"   : round(dT_value, 0),
        "ΔC_가치_원"   : round(dC_value, 0),
        "분자_원"       : round(numerator, 0),
        "Cost_op_원"   : cost_op,
        "E_지수"        : round(E, 3),
        "E_reduction_pct": round(dC / e_moto * 100, 1) if e_moto > 0 else 0,
        "T_efficiency_pct": round(dT / t_moto * 100, 1) if t_moto > 0 else 0,
        "판정"          : verdict,
    })

    print(f"  {sc['name']:20s} | {dT:5.1f}  | {dC:6.4f} | "
          f"{dT_value:6.0f}  | {dC_value:6.1f}  | {cost_op:4d} | "
          f"{E:4.3f} | {verdict}")

esg_df = pd.DataFrame(results)

# ── 가중 평균 E ───────────────────────────────────────────────
WEIGHTS = [0.20, 0.35, 0.15, 0.10, 0.10, 0.10]
E_weighted = np.average(esg_df["E_지수"], weights=WEIGHTS)
E_red_weighted = np.average(esg_df["E_reduction_pct"], weights=WEIGHTS[:len(esg_df)])
T_eff_weighted = np.average(esg_df["T_efficiency_pct"], weights=WEIGHTS[:len(esg_df)])

print(f"\n{'='*50}")
print(f"[가중 평균]")
print(f"  E (효율성 지수)      = {E_weighted:.3f}  {'✅ > 1.0 효율적' if E_weighted >= 1.0 else '⚠ < 1.0'}")
print(f"  E_reduction (탄소)  = {E_red_weighted:.1f}%")
print(f"  T_efficiency (시간) = {T_eff_weighted:.1f}%")

# ── 손익분기점 분석 ───────────────────────────────────────────
print(f"\n[손익분기점 분석]")
# E=1이 되는 시간 단축 최소값
for sc_name, cost_mode, d_fly, d_last in [
    ("중거리 표준", "드론+로봇", 2.2, 0.3)
]:
    e_moto = (d_fly + d_last) * EMISSION["motorcycle"]
    e_drone = d_fly * EMISSION["drone"] + d_last * EMISSION["robot"]
    dC = e_moto - e_drone
    dC_value = dC * CARBON_PRICE * OMEGA_CARBON
    cost_op = COST_OP[cost_mode]
    # E=1: dT_value + dC_value = cost_op
    # dT × WAGE × OMEGA_T = cost_op - dC_value
    dT_breakeven = (cost_op - dC_value) / (WAGE_PER_MIN * OMEGA_TIME)
    print(f"  {sc_name} ({cost_mode}): 시간 {dT_breakeven:.1f}분 단축 시 E=1.0 달성")
    print(f"  현재 단축: 6.0분 (E={results[1]['E_지수']:.3f})")

# ── 저장 ─────────────────────────────────────────────────────
esg_df.to_csv(OUT / "esg_index_v2.csv", index=False, encoding="utf-8-sig")
print(f"\n✅ esg_index_v2.csv 저장")

# ── esg.js 업데이트 ────────────────────────────────────────────
weather_summary = {}
if (OUT / "weather_sim_summary.json").exists():
    weather_summary = json.loads(
        (OUT / "weather_sim_summary.json").read_text(encoding="utf-8")
    )

esg_js_data = {
    "formula": {
        "E"          : "( ΔT×250×0.6 + ΔC×30×0.4 ) / Cost_op",
        "E_numerator": "시간절감가치(원) + 탄소절감가치(원)",
        "units"      : {"ΔT": "분", "ΔC": "kgCO2", "Cost": "원/건"},
        "omega"      : {"time": 0.6, "carbon": 0.4},
        "unit_prices": {"wage_per_min": 250, "carbon_per_kg": 30},
        "cost_op"    : COST_OP,
    },
    "E_weighted"       : round(E_weighted, 3),
    "E_reduction_pct"  : round(E_red_weighted, 1),
    "T_efficiency_pct" : round(T_eff_weighted, 1),
    "E_verdict"        : "효율적" if E_weighted >= 1.0 else "개선 필요",
    "scenarios"        : results,
    "annual"           : {
        "daily_deliveries" : 365000,
        "E_total_annual"   : round(E_weighted * COST_OP["드론+로봇"] * 365000, 0),
    },
    "weather"          : {
        "P_drone_available": weather_summary.get("P_drone_available_observed",
                             weather_summary.get("P_drone_available", 0.90)),
    }
}

(BASE / "assets" / "js" / "esg.js").write_text(
    f"// Auto-generated NB14 v2 — E = (ΔT×ω_t + ΔC×ω_c) / Cost_op\n"
    f"// E_weighted = {E_weighted:.3f} (가중평균, 1.0 이상 = 효율적)\n"
    f"const ESG = {json.dumps(esg_js_data, ensure_ascii=False, indent=2)};\n",
    encoding="utf-8"
)
print(f"✅ esg.js 업데이트")

# ── 시각화 ───────────────────────────────────────────────────
print("\n[시각화 생성...]")
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib.gridspec as gridspec

    plt.rcParams["axes.unicode_minus"] = False
    try:
        plt.rcParams["font.family"] = "Malgun Gothic"
    except:
        pass

    fig = plt.figure(figsize=(18, 12))
    gs  = gridspec.GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.35)
    fig.suptitle(
        f"NB14 v2 — 효율성 지수 $E = (\\Delta T \\cdot \\omega_t + \\Delta C \\cdot \\omega_c) / Cost_{{op}}$\n"
        f"가중 평균 $E$ = {E_weighted:.3f}  |  $E_{{reduction}}$ = {E_red_weighted:.1f}%  |  $T_{{efficiency}}$ = {T_eff_weighted:.1f}%",
        fontsize=12, y=0.98
    )

    sc_names = [r["시나리오"] for r in results]
    e_vals   = [r["E_지수"]   for r in results]
    colors_e = ["#42A5F5" if v >= 1.0 else "#FFA726" if v >= 0.5 else "#EF5350"
                for v in e_vals]

    # ── 1. E 지수 바차트 ─────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :2])
    bars = ax1.bar(sc_names, e_vals, color=colors_e, alpha=0.85, edgecolor="white", width=0.6)
    ax1.axhline(1.0, color="red", ls="--", lw=1.5, label="E=1.0 (손익분기점)")
    ax1.axhline(E_weighted, color="navy", ls=":", lw=1.5,
                label=f"가중 평균 E={E_weighted:.3f}")
    for bar, val in zip(bars, e_vals):
        ax1.text(bar.get_x() + bar.get_width()/2, val + 0.01,
                 f"{val:.3f}", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax1.set_ylabel("효율성 지수 E")
    ax1.set_title("시나리오별 효율성 지수 E\n(파랑 ≥ 1.0 효율적  |  주황 ≥ 0.5  |  빨강 < 0.5)")
    ax1.legend(fontsize=9)
    ax1.grid(axis="y", alpha=0.3)
    ax1.set_ylim(0, max(e_vals) * 1.2)
    plt.setp(ax1.get_xticklabels(), rotation=15, ha="right", fontsize=8)

    # ── 2. 분자 구성 (시간 vs 탄소) ──────────────────────────
    ax2 = fig.add_subplot(gs[0, 2])
    dt_vals = [r["ΔT_가치_원"] for r in results]
    dc_vals = [r["ΔC_가치_원"] for r in results]
    cost_v  = [r["Cost_op_원"] for r in results]
    x = np.arange(len(sc_names))
    w = 0.3
    ax2.bar(x - w/2, dt_vals, w, color="#42A5F5", alpha=0.8, label=f"ΔT 가치 (ω={OMEGA_TIME})")
    ax2.bar(x + w/2, dc_vals, w, color="#66BB6A", alpha=0.8, label=f"ΔC 가치 (ω={OMEGA_CARBON})")
    ax2.plot(x, cost_v, "r^--", ms=6, lw=1.5, label="Cost_op (원/건)")
    ax2.set_xticks(x)
    ax2.set_xticklabels([n[:4] for n in sc_names], fontsize=7)
    ax2.set_ylabel("원/배송건")
    ax2.set_title("분자 구성 vs 운영비용")
    ax2.legend(fontsize=7)
    ax2.grid(axis="y", alpha=0.3)

    # ── 3. 손익분기점 곡선 ─────────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 0])
    dT_range = np.linspace(0, 20, 100)
    # 중거리 기준 고정 탄소 절감
    dC_fixed = results[1]["ΔC_kg"]
    dC_val   = dC_fixed * CARBON_PRICE * OMEGA_CARBON
    E_curve  = (dT_range * WAGE_PER_MIN * OMEGA_TIME + dC_val) / COST_OP["드론+로봇"]
    ax3.plot(dT_range, E_curve, color="#42A5F5", lw=2.5)
    ax3.axhline(1.0, color="red", ls="--", lw=1.2, label="E=1.0")
    ax3.axvline(results[1]["ΔT_분"], color="#FFA726", ls="--", lw=1.2,
                label=f"현재 ΔT={results[1]['ΔT_분']:.0f}분")
    ax3.fill_between(dT_range, E_curve, 1.0,
                     where=(E_curve >= 1.0), alpha=0.15, color="green", label="효율 구간")
    ax3.fill_between(dT_range, E_curve, 1.0,
                     where=(E_curve < 1.0), alpha=0.10, color="red", label="비효율 구간")
    ax3.set_xlabel("ΔT 시간 단축 (분)")
    ax3.set_ylabel("효율성 지수 E")
    ax3.set_title("손익분기점 곡선\n(중거리 2.5km 기준)")
    ax3.legend(fontsize=8)
    ax3.grid(alpha=0.3)
    ax3.set_ylim(0, 3)

    # ── 4. 탄소 절감 vs 시간 단축 산점도 ─────────────────────
    ax4 = fig.add_subplot(gs[1, 1])
    ered = [r["E_reduction_pct"] for r in results]
    teff = [r["T_efficiency_pct"] for r in results]
    scatter = ax4.scatter(ered, teff, c=e_vals, cmap="RdYlGn",
                          s=150, vmin=0.5, vmax=2.0, zorder=3)
    plt.colorbar(scatter, ax=ax4, label="E 지수", shrink=0.8)
    for i, r in enumerate(results):
        ax4.annotate(r["시나리오"][:4], (ered[i], teff[i]),
                     fontsize=7, xytext=(4,4), textcoords="offset points")
    ax4.axvline(80, color="gray", ls=":", lw=0.8)
    ax4.axhline(30, color="gray", ls=":", lw=0.8)
    ax4.set_xlabel("탄소 절감률 (%)")
    ax4.set_ylabel("시간 단축률 (%)")
    ax4.set_title("탄소절감 vs 시간단축\n(색=E 지수)")
    ax4.grid(alpha=0.3)

    # ── 5. 연간 규모 추정 ─────────────────────────────────────
    ax5 = fig.add_subplot(gs[1, 2])
    daily_list   = [100_000, 365_000, 1_000_000]
    annual_value = []
    annual_cost  = []
    for daily in daily_list:
        annual = daily * 365
        avg_dT = np.average([r["ΔT_분"] for r in results], weights=WEIGHTS)
        avg_dC = np.average([r["ΔC_kg"] for r in results], weights=WEIGHTS)
        num    = (avg_dT * WAGE_PER_MIN * OMEGA_TIME +
                  avg_dC * CARBON_PRICE * OMEGA_CARBON) * annual / 1e8  # 억원
        cost   = COST_OP["드론+로봇"] * annual / 1e8
        annual_value.append(num)
        annual_cost.append(cost)

    x3 = np.arange(len(daily_list))
    labels3 = ["10만건/일", "36.5만건/일", "100만건/일"]
    ax5.bar(x3 - 0.2, annual_value, 0.35, color="#42A5F5", alpha=0.85, label="창출 가치 (억원)")
    ax5.bar(x3 + 0.2, annual_cost,  0.35, color="#EF5350", alpha=0.70, label="운영 비용 (억원)")
    ax5.set_xticks(x3)
    ax5.set_xticklabels(labels3, fontsize=8)
    ax5.set_ylabel("연간 금액 (억원)")
    ax5.set_title("연간 규모 추정\n(창출가치 vs 운영비용)")
    ax5.legend(fontsize=8)
    ax5.grid(axis="y", alpha=0.3)
    for i, (v, c) in enumerate(zip(annual_value, annual_cost)):
        ax5.text(i - 0.2, v + 0.5, f"{v:.0f}", ha="center", fontsize=7)
        ax5.text(i + 0.2, c + 0.5, f"{c:.0f}", ha="center", fontsize=7)

    plt.savefig(OUT / "esg_chart_v2.png", dpi=150, bbox_inches="tight")
    print("✅ esg_chart_v2.png 저장")

except Exception as e:
    print(f"⚠ 시각화 오류: {e}")
    import traceback
    traceback.print_exc()

print(f"\n{'='*50}")
print(f"✅ NB14 v2 완료!")
print(f"   E (가중평균) = {E_weighted:.3f}  →  {'드론+로봇 배송이 비용 대비 효율적!' if E_weighted >= 1.0 else '효율 개선 여지 있음'}")
print(f"   E_reduction = {E_red_weighted:.1f}%  |  T_efficiency = {T_eff_weighted:.1f}%")
