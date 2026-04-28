"""
NB06b_infrastructure_constraints.py
=====================================
공사장 + 보호구역 → 제약 레이어 추가 (score_construction, score_protected)

입력:
  D:\성남시\민간건축 공사장 현황 [건축과]_.xlsx
  D:\성남시\어린이.노인.장애인보호구역 지정 및 교통안전시설 현황 [교통기획과]_.xlsx
  processed/constraint_layers_v3_ra.csv

출력:
  processed/constraint_layers_v4.csv  ← score_construction + score_protected 추가

공사장 로직:
  - 공사장 주소 → 지오코딩 → H3 셀 매핑
  - 공사장 반경 200m 내 셀: score_construction = 0.5 (드론 이착륙 위험)
  - 지상층수 10층 이상: = 0.3 (고층 공사 분진/크레인)

보호구역 로직:
  - 보호구역명에서 구/동 추출 → H3 셀 매핑
  - 시설구분별 가중치:
    초등학교: 0.5 (소음 민감, 드론 비행 위험)
    노인:     0.6 (로봇 충돌 위험)
    장애인:   0.7 (안전 최우선)
"""

import pandas as pd
import numpy as np
import re
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

BASE = Path(r"C:\Users\pasoh\OneDrive\문서\GitHub\Aero-Logic-seongnam")
OUT  = BASE / "processed"
DATA = Path(r"D:\성남시")

print("=" * 60)
print("NB06b — 인프라 제약 레이어 (공사장 + 보호구역)")
print("=" * 60)

# ── 기존 constraint_layers 로드 ──────────────────────────────
df = pd.read_csv(OUT / "constraint_layers_v3_ra.csv", encoding="utf-8-sig")
print(f"기존 레이어: {len(df)}행")
df["score_construction"] = 1.0   # 기본: 문제없음
df["score_protected"]    = 1.0

# ── 공사장 데이터 로드 ────────────────────────────────────────
print("\n[1] 공사장 데이터 처리...")
const_df = pd.read_excel(
    DATA / "민간건축 공사장 현황 [건축과]_.xlsx",
    sheet_name=0
)
print(f"  공사장: {len(const_df)}개소")
print(f"  컬럼: {const_df.columns.tolist()[:8]}")

# 주소에서 구/동 추출
def extract_dong(addr):
    """'분당구 삼평동 654' → ('분당구', '삼평동')"""
    if pd.isna(addr):
        return None, None
    addr = str(addr)
    gu_match  = re.search(r'(수정구|중원구|분당구)', addr)
    dong_match = re.search(r'(\S+동)', addr)
    gu   = gu_match.group(1)  if gu_match  else None
    dong = dong_match.group(1) if dong_match else None
    return gu, dong

const_df[["GU_NM","ADM_NM"]] = const_df["대지위치"].apply(
    lambda x: pd.Series(extract_dong(x))
)
const_df["floors"] = pd.to_numeric(const_df["지상층수"], errors="coerce").fillna(0)

# 층수별 제약 점수
def const_score(floors):
    if floors >= 10:
        return 0.30   # 고층 공사: 크레인·분진
    elif floors >= 5:
        return 0.50   # 중층
    else:
        return 0.70   # 저층

const_df["penalty"] = const_df["floors"].apply(const_score)

print(f"\n  [공사장 구/동 분포]")
print(const_df.groupby("GU_NM")["ADM_NM"].count().to_string())

# ── H3 셀에 공사장 패널티 적용 ────────────────────────────────
# 동 이름 기반 매핑 (geocoding 대신 행정동 단위 적용)
for _, row in const_df.iterrows():
    if row["ADM_NM"] is None:
        continue
    mask = df["ADM_NM"].str.contains(str(row["ADM_NM"])[:3], na=False)
    if mask.any():
        # 해당 동 내 셀 중 기존보다 낮은 값이면 업데이트 (가장 심각한 공사장 기준)
        df.loc[mask, "score_construction"] = df.loc[mask, "score_construction"].clip(
            upper=float(row["penalty"])
        )

n_affected = (df["score_construction"] < 1.0).sum()
print(f"\n  → 공사장 제약 영향 셀: {n_affected}개")

# ── 보호구역 데이터 로드 ──────────────────────────────────────
print("\n[2] 보호구역 데이터 처리...")
prot_df = pd.read_excel(
    DATA / "어린이.노인.장애인보호구역 지정 및 교통안전시설 현황 [교통기획과]_.xlsx",
    sheet_name=0
)
print(f"  보호구역: {len(prot_df)}구간")
print(f"  시설구분: {prot_df['시설구분'].value_counts().to_dict()}")

# 시설구분별 점수
PROT_SCORE = {
    "초등학교"  : 0.50,
    "중학교"    : 0.60,
    "유치원"    : 0.45,
    "어린이집"  : 0.45,
    "노인"      : 0.55,
    "장애인"    : 0.55,
    "실버"      : 0.55,
}
def get_prot_score(stype):
    for key, val in PROT_SCORE.items():
        if key in str(stype):
            return val
    return 0.70

prot_df["penalty"] = prot_df["시설구분"].apply(get_prot_score)
prot_df["GU_NM"]   = prot_df["시군구명"]

# 시설명에서 동 이름 추출 (예: "단대초등학교" → 단대동 유추는 어렵, 구 단위로 적용)
# → 구 단위로 최소 패널티 적용, 시설 주변만 영향
for _, row in prot_df.drop_duplicates("시설명").iterrows():
    gu   = row.get("GU_NM", "")
    mask = df["GU_NM"] == gu
    if mask.any():
        cur_min = df.loc[mask, "score_protected"].min()
        new_val = float(row["penalty"])
        if new_val < cur_min:
            # 구 내 H3 셀의 score_protected를 낮춤 (패널티 누적)
            df.loc[mask, "score_protected"] = df.loc[mask, "score_protected"].clip(
                upper=new_val + 0.15   # 구 전체보다는 느슨하게
            )

n_prot = (df["score_protected"] < 1.0).sum()
print(f"\n  → 보호구역 제약 영향 셀: {n_prot}개")

# ── composite_score 재계산 (6개 레이어) ─────────────────────
print("\n[3] composite_score v4 재계산 (6개 레이어)...")

score_cols = [
    "score_airspace", "score_obstacle", "score_noise",
    "score_terrain", "score_weather",
    "score_construction", "score_protected"
]
score_cols = [c for c in score_cols if c in df.columns]
print(f"  적용 레이어: {score_cols}")

df["composite_6layer"] = df[score_cols].prod(axis=1)
RA_WEIGHT = 0.15
df["composite_v3"] = (1 - RA_WEIGHT) * df["composite_6layer"] + RA_WEIGHT * df["Ra"]

# 기존 v2와 비교
old_comp_col = "composite_v2" if "composite_v2" in df.columns else "composite_5layer" if "composite_5layer" in df.columns else None
if old_comp_col:
    print(f"  {old_comp_col} 평균: {df[old_comp_col].mean():.4f}")
else:
    print(f"  (기존 composite 컬럼 없음 — v4 신규 생성)")
print(f"  composite_v3 평균: {df['composite_v3'].mean():.4f}")

# ── 저장 ─────────────────────────────────────────────────────
df.to_csv(OUT / "constraint_layers_v4.csv", index=False, encoding="utf-8-sig")
print(f"\n✅ constraint_layers_v4.csv 저장 ({len(df)}행, {len(df.columns)}컬럼)")

# 제약 요약
print(f"\n[신규 레이어 요약]")
print(f"  score_construction: min={df['score_construction'].min():.2f}, "
      f"mean={df['score_construction'].mean():.3f}")
print(f"  score_protected:    min={df['score_protected'].min():.2f}, "
      f"mean={df['score_protected'].mean():.3f}")

print(f"\n✅ NB06b 완료! → constraint_layers_v4.csv")
print(f"   다음: NB10 v3에서 composite_v3 기반 거점 재선정 가능")
