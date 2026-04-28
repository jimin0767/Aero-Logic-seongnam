"""
NB05_peak_filter.py  —  피크타임 유동인구 재집계
==================================================
피크타임: 11~14시(점심), 17~21시(저녁)
산출물  : processed/flow_pop_agg_peak.parquet
          processed/flow_pop_hourly_peak.parquet
"""

import pandas as pd
import numpy as np
from pathlib import Path

BASE = Path(__file__).parent.parent
OUT  = BASE / "processed"

PEAK_HOURS = list(range(11, 15)) + list(range(17, 22))
print(f"피크타임 정의: {PEAK_HOURS}")

try:
    import pyarrow  # noqa

    # ── 기존 시간대별 데이터 로드 ──────────────────────────────────────────
    hourly = pd.read_parquet(OUT / "flow_pop_hourly.parquet", engine="fastparquet")
    print(f"로드: {len(hourly)}행 | 컬럼: {hourly.columns.tolist()}")
    print(f"TIME_CD 범위: {sorted(hourly['TIME_CD'].unique())}")

    # ── 피크 필터 ─────────────────────────────────────────────────────────
    hourly_peak = hourly[hourly["TIME_CD"].isin(PEAK_HOURS)].copy()
    print(f"전체 {len(hourly)}행 → 피크 {len(hourly_peak)}행 ({len(hourly_peak)/len(hourly):.1%})")

    # ── 동별 집계 ─────────────────────────────────────────────────────────
    agg_dict = {"avg_total_pop": ["mean", "max"]}
    if "avg_young_pop" in hourly_peak.columns:
        agg_dict["avg_young_pop"] = "mean"

    grouped = hourly_peak.groupby("ADMI_CD").agg(agg_dict)
    grouped.columns = ["avg_peak_total", "peak_hour_pop"] + (
        ["avg_peak_young"] if "avg_young_pop" in hourly_peak.columns else []
    )
    grouped = grouped.reset_index()

    # dong_nm 추가
    try:
        old = pd.read_parquet(OUT / "flow_pop_agg.parquet", engine="fastparquet")
        if "dong_nm" in old.columns:
            grouped = grouped.merge(old[["ADMI_CD","dong_nm"]], on="ADMI_CD", how="left")
    except Exception:
        pass

    # ── Min-Max 정규화 ────────────────────────────────────────────────────
    for col in ["avg_peak_total", "avg_peak_young"]:
        if col in grouped.columns:
            mn, mx = grouped[col].min(), grouped[col].max()
            grouped[f"{col}_norm"] = (grouped[col] - mn) / (mx - mn) if mx > mn else 0.0

    t_norm = "avg_peak_total_norm"
    y_norm = "avg_peak_young_norm" if "avg_peak_young_norm" in grouped.columns else t_norm
    grouped["flow_pop_index"] = 0.5 * grouped[t_norm] + 0.5 * grouped[y_norm]

    # ── 기존 vs 피크 비교 ─────────────────────────────────────────────────
    try:
        old = pd.read_parquet(OUT / "flow_pop_agg.parquet", engine="fastparquet")
        cmp = grouped.merge(old[["ADMI_CD","flow_pop_index"]].rename(
            columns={"flow_pop_index":"fp_전체"}), on="ADMI_CD", how="left")
        cmp["fp_피크"] = cmp["flow_pop_index"]
        top = cmp.nlargest(10, "fp_피크")
        show_cols = (["dong_nm"] if "dong_nm" in cmp.columns else []) + ["fp_전체","fp_피크"]
        print("\n[상위 10 동 비교]")
        print(top[show_cols].round(4).to_string(index=False))
        print(f"\n전체 vs 피크 상관계수: {cmp['fp_전체'].corr(cmp['fp_피크']):.4f}")
    except Exception as e:
        print(f"비교 생략: {e}")

    # ── 저장 ──────────────────────────────────────────────────────────────
    grouped.to_parquet(OUT / "flow_pop_agg_peak.parquet", index=False, engine="fastparquet")
    hourly_peak.to_parquet(OUT / "flow_pop_hourly_peak.parquet", index=False, engine="fastparquet")
    print(f"\n✅ flow_pop_agg_peak.parquet ({len(grouped)}행)")
    print(f"✅ flow_pop_hourly_peak.parquet ({len(hourly_peak)}행)")

except ImportError:
    print("\n⚠ pyarrow 없음. 아래 코드를 NB05 Cell 7 직전에 삽입하세요:\n")
    print("PEAK_HOURS = list(range(11,15)) + list(range(17,22))")
    print("recent = recent[recent['TIME_CD'].isin(PEAK_HOURS)]")
    print("# 이후 기존 집계 코드 그대로 실행")
except FileNotFoundError as e:
    print(f"\n⚠ 파일 없음: {e}")
    print("NB05를 먼저 실행해서 flow_pop_hourly.parquet를 생성하세요.")
