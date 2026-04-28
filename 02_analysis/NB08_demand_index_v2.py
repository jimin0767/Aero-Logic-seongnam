"""
NB08_demand_index_v2.py
=======================
수요지수(Ds) 4변수 분리 버전 — 소현 작업

기존 NB08: urgency = 0.6 * delivery_demand_index + 0.4 * flow_pop_index  (2변수)

개선 버전:
  Ds = w_Hr*Hr + w_Fp*Fp + w_Cc*Cc + w_Od*Od  (4변수)

  - Hr  : 1인가구 비중 (배달 수요 핵심 타깃)
  - Fp  : 유동인구 지수 (피크타임 기준, NB05에서 재산출된 값)
  - Cc  : 카드 매출 밀도 (상업시설 밀도 대리변수)
  - Od  : 배달 앱 주문 대리변수 (배달/편의점 카드매출 비중)

산출물:
  processed/single_household_hr.csv   — 동별 Hr 지수
  processed/delivery_urgency_grid_v2.gpkg — 개선된 urgency 포함 H3 그리드
  processed/constraint_layers_v2.csv  — 개선된 Ds 반영 제약레이어 (대시보드용)
"""

import pandas as pd
import numpy as np
from pathlib import Path

try:
    import geopandas as gpd
    HAS_GEO = True
except ImportError:
    HAS_GEO = False
    print("⚠ geopandas 없음 — CSV만 저장됩니다 (gpkg 생략)")

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent
OUT  = BASE / "processed"
RAW_1IN = BASE / "경기도 성남시_1인세대_현황_20250430.csv"

print("=" * 60)
print("NB08 수요지수 v2 — 4변수 분리 산출")
print("=" * 60)

# ── 가중치 정의 (팀 회의에서 조정 가능) ───────────────────────────────────────
W_HR = 0.30   # 1인가구 비중 (배달 타깃 인구)
W_FP = 0.25   # 유동인구 지수 (피크타임)
W_CC = 0.25   # 카드 매출 밀도 (상업 활성도)
W_OD = 0.20   # 배달 주문 대리변수 (배달/편의점 매출 비중)
assert abs(W_HR + W_FP + W_CC + W_OD - 1.0) < 1e-9, "가중치 합이 1이어야 합니다"

print(f"\n[가중치] Hr={W_HR}, Fp={W_FP}, Cc={W_CC}, Od={W_OD}")

# ── STEP 1: Hr — 1인가구 비중 산출 ───────────────────────────────────────────
print("\n[STEP 1] 1인가구 비중(Hr) 산출...")

df_1in = pd.read_csv(RAW_1IN, encoding="utf-8-sig")

# 전체 가구수 = 1인세대수를 기준으로 비율 계산
# 실제 전체 세대수 데이터가 없으므로 동별 총합 기준 상대 비율로 정규화
df_hr = df_1in[["구별", "동별", "1인세대수_계"]].copy()
df_hr.columns = ["GU_NM", "ADM_NM", "single_hh_count"]
df_hr = df_hr[df_hr["ADM_NM"].notna() & (df_hr["ADM_NM"] != "")]

# 동명 표준화: 공백 제거
df_hr["ADM_NM"] = df_hr["ADM_NM"].str.strip()
df_hr["GU_NM"]  = df_hr["GU_NM"].str.strip()

# Min-Max 정규화 → Hr 지수 (0~1)
vmin, vmax = df_hr["single_hh_count"].min(), df_hr["single_hh_count"].max()
df_hr["Hr"] = (df_hr["single_hh_count"] - vmin) / (vmax - vmin)

print(f"  ✅ 동 수: {len(df_hr)}")
print(f"  상위 5개 동 (1인 가구 수 기준):")
print(df_hr.nlargest(5, "single_hh_count")[["GU_NM", "ADM_NM", "single_hh_count", "Hr"]].to_string(index=False))

df_hr.to_csv(OUT / "single_household_hr.csv", index=False, encoding="utf-8-sig")
print(f"  저장: {OUT / 'single_household_hr.csv'}")

# ── STEP 2: Fp — 유동인구 지수 로드 ──────────────────────────────────────────
print("\n[STEP 2] 유동인구 지수(Fp) 로드...")

# NB05_peak_filter.py가 먼저 실행되었으면 peak 버전 사용, 없으면 기본값
peak_path = OUT / "flow_pop_agg_peak.parquet"
base_path  = OUT / "flow_pop_agg.parquet"

try:
    import pyarrow  # noqa
    if peak_path.exists():
        flow_pop = pd.read_parquet(peak_path, engine="fastparquet")
        print(f"  ✅ 피크타임 필터 버전 로드: {peak_path.name}")
    else:
        flow_pop = pd.read_parquet(base_path, engine="fastparquet")
        print(f"  ⚠ 피크타임 버전 없음, 기본값 사용: {base_path.name}")
        print("    → NB05_peak_filter.py를 먼저 실행하면 더 정확해집니다")
    fp_col = "ADMI_CD"
except ImportError:
    print("  ⚠ pyarrow 없음 — constraint_layers.csv에서 flow_pop_index 직접 사용")
    flow_pop = None

# ── STEP 3: Cc & Od — 카드 매출 데이터 로드 ──────────────────────────────────
print("\n[STEP 3] 카드 매출(Cc, Od) 산출...")

try:
    import pyarrow  # noqa
    card = pd.read_parquet(OUT / "card_delivery_demand.parquet", engine="fastparquet")
    print(f"  카드 배달수요 컬럼: {card.columns.tolist()}")

    # Cc: 전체 배달 수요 밀도 (delivery_demand_index가 이미 있으면 활용)
    if "delivery_demand_index" in card.columns:
        cc_col = "delivery_demand_index"
    else:
        cc_col = card.select_dtypes("number").columns[0]

    # Od: delivery_demand_index를 배달 앱 주문 대리변수로 사용
    # (실제 배달앱 업종 카드매출 세분화가 있다면 여기서 필터링)
    od_col = cc_col  # 동일 컬럼 활용 (더 세분화된 데이터 확보 시 교체)
    print(f"  Cc/Od 컬럼: {cc_col}")
    card_available = True
except (ImportError, FileNotFoundError):
    print("  ⚠ 카드 데이터 로드 불가 — constraint_layers.csv 값 활용")
    card_available = False

# ── STEP 4: constraint_layers.csv 기반으로 4변수 통합 ─────────────────────────
print("\n[STEP 4] 4변수 통합 Ds 산출...")

constraint = pd.read_csv(OUT / "constraint_layers.csv")
print(f"  constraint_layers 행수: {len(constraint)}")
print(f"  컬럼: {constraint.columns.tolist()}")

# Hr 병합 (동명 기준)
constraint = constraint.merge(
    df_hr[["ADM_NM", "Hr"]],
    on="ADM_NM",
    how="left"
)
constraint["Hr"] = constraint["Hr"].fillna(0)

# Fp: 기존 flow_pop_index (또는 peak 버전)
if flow_pop is not None and fp_col in flow_pop.columns:
    fp_merge_col = "ADMI_CD" if "ADMI_CD" in flow_pop.columns else flow_pop.columns[0]
    constraint = constraint.merge(
        flow_pop[[fp_merge_col, "flow_pop_index"]].rename(
            columns={"flow_pop_index": "Fp", fp_merge_col: "CSV_ADMI_CD"}
        ),
        on="CSV_ADMI_CD",
        how="left"
    )
    constraint["Fp"] = constraint["Fp"].fillna(0)
else:
    # 기존 flow_pop_index 그대로 사용
    constraint["Fp"] = constraint["flow_pop_index"].fillna(0)
    print("  Fp: 기존 flow_pop_index 사용")

# Cc & Od: delivery_demand_index 기반
constraint["Cc"] = constraint["delivery_demand_index"].fillna(0)
constraint["Od"] = constraint["delivery_demand_index"].fillna(0)  # 더 세분화 가능

# ── STEP 5: Ds 수식 적용 ─────────────────────────────────────────────────────
print("\n[STEP 5] Ds 수식 적용...")

constraint["Ds_v2"] = (
    W_HR * constraint["Hr"]
  + W_FP * constraint["Fp"]
  + W_CC * constraint["Cc"]
  + W_OD * constraint["Od"]
)

# 기존 urgency와 비교
print("\n  [기존 urgency 통계]")
print(constraint["urgency"].describe().round(4))
print("\n  [신규 Ds_v2 통계]")
print(constraint["Ds_v2"].describe().round(4))

# 상관계수 확인
corr = constraint["urgency"].corr(constraint["Ds_v2"])
print(f"\n  기존 urgency vs Ds_v2 상관계수: {corr:.4f}")

# 상위 10 동 비교
print("\n  [상위 10 동 비교]")
top_compare = constraint.nlargest(10, "Ds_v2")[
    ["ADM_NM", "GU_NM", "Hr", "Fp", "Cc", "Od", "Ds_v2", "urgency"]
].round(4)
print(top_compare.to_string(index=False))

# ── STEP 6: 저장 ─────────────────────────────────────────────────────────────
print("\n[STEP 6] 결과 저장...")

# constraint_layers_v2.csv 저장 (대시보드용)
constraint.to_csv(OUT / "constraint_layers_v2.csv", index=False, encoding="utf-8-sig")
print(f"  ✅ {OUT / 'constraint_layers_v2.csv'}")

# H3 그리드 gpkg 업데이트
try:
    gdf = gpd.read_file(OUT / "delivery_urgency_grid.gpkg")
    gdf = gdf.merge(
        constraint[["h3_index", "Hr", "Fp", "Cc", "Od", "Ds_v2"]],
        on="h3_index",
        how="left"
    )
    gdf.to_file(OUT / "delivery_urgency_grid_v2.gpkg", driver="GPKG")
    print(f"  ✅ {OUT / 'delivery_urgency_grid_v2.gpkg'}")
except Exception as e:
    print(f"  ⚠ gpkg 업데이트 실패 (geopandas 없음): {e}")
    print("    constraint_layers_v2.csv는 정상 저장됨")

print("\n✅ 완료! Ds_v2 = {:.0f}*Hr + {:.0f}*Fp + {:.0f}*Cc + {:.0f}*Od".format(
    W_HR*100, W_FP*100, W_CC*100, W_OD*100
))
print("   NB09_constraint_layer_scoring.ipynb에서 urgency 대신 Ds_v2 사용하세요.")
