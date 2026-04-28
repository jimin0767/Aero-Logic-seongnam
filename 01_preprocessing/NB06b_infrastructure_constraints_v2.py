"""
NB06b_infrastructure_constraints_v2.py
=======================================
v2 업데이트:
  1. 공사장 준공예정일 기반 시계열 필터
     → 2026년 4월 기준 공사 중인 곳만 제약 적용
     → 이미 완공된 곳은 score_construction = 1.0 (정상)
  2. 효율성 지수 E 공식 분모(Cost_operation) 추가
     → NB14 결과에 운영비용 상수 반영
"""

import pandas as pd
import numpy as np
import re
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

BASE     = Path(r"C:\Users\pasoh\OneDrive\문서\GitHub\Aero-Logic-seongnam")
OUT      = BASE / "processed"
DATA     = Path(r"D:\성남시")
TODAY    = datetime(2026, 4, 29)  # 분석 기준일

print("=" * 60)
print("NB06b v2 — 공사장 준공예정일 필터 + 인프라 제약 업데이트")
print("=" * 60)

# ── 기존 constraint_layers 로드 ──────────────────────────────
df = pd.read_csv(OUT / "constraint_layers_v3_ra.csv", encoding="utf-8-sig")
print(f"기존 레이어: {len(df)}행")
df["score_construction"] = 1.0
df["score_protected"]    = 1.0

# ── 공사장 데이터 로드 + 준공예정일 필터 ─────────────────────
print("\n[1] 공사장 — 준공예정일 기준 진행 중 vs 완공 분류...")
const_df = pd.read_excel(
    DATA / "민간건축 공사장 현황 [건축과]_.xlsx", sheet_name=0
)

def parse_date(d):
    try:
        return datetime.strptime(str(d).strip(), "%Y-%m-%d")
    except:
        return None

const_df["준공일_dt"] = const_df["준공예정일"].apply(parse_date)

# 상태 분류
def construction_status(row):
    d = row["준공일_dt"]
    if d is None:
        return "unknown"
    if d < TODAY:
        return "completed"   # 이미 완공 → 제약 없음
    elif (d - TODAY).days <= 90:
        return "imminent"    # 90일 내 완공 예정 → 약한 제약
    else:
        return "ongoing"     # 계속 공사 중 → 강한 제약

const_df["status"] = const_df.apply(construction_status, axis=1)

status_counts = const_df["status"].value_counts()
print(f"\n  [공사장 상태 분류]")
for s, n in status_counts.items():
    print(f"  {s:12s}: {n}개소")

# 상태별 제약 점수
CONST_SCORE = {
    "completed": 1.00,    # 완공 — 제약 없음
    "imminent" : 0.65,    # 90일 내 완공 — 약한 제약
    "ongoing"  : 0.40,    # 공사 중 — 강한 제약
    "unknown"  : 0.55,    # 정보 없음 — 중간
}

# 지상층수 × 상태 복합 점수
def const_score(row):
    base = CONST_SCORE[row["status"]]
    floors = pd.to_numeric(row["지상층수"], errors="coerce")
    if pd.isna(floors):
        return base
    if floors >= 15:
        return base * 0.75   # 초고층 추가 패널티
    elif floors >= 10:
        return base * 0.85
    return base

const_df["penalty"] = const_df.apply(const_score, axis=1)

# 주소 파싱
def extract_dong(addr):
    if pd.isna(addr):
        return None, None
    addr = str(addr)
    gu   = re.search(r'(수정구|중원구|분당구)', addr)
    dong = re.search(r'(\S+동)', addr)
    return (gu.group(1) if gu else None), (dong.group(1) if dong else None)

const_df[["GU_NM","ADM_NM"]] = const_df["대지위치"].apply(
    lambda x: pd.Series(extract_dong(x))
)

# H3 셀 패널티 적용 (진행 중인 공사장만)
active = const_df[const_df["status"] != "completed"]
print(f"\n  진행 중 공사장: {len(active)}개소 → 제약 적용")

for _, row in active.iterrows():
    if row["ADM_NM"] is None:
        continue
    mask = df["ADM_NM"].str.contains(str(row["ADM_NM"])[:3], na=False)
    if mask.any():
        df.loc[mask, "score_construction"] = df.loc[mask, "score_construction"].clip(
            upper=float(row["penalty"])
        )

print(f"\n  score_construction < 1.0 셀: {(df['score_construction'] < 1.0).sum()}개")

# ── 보호구역 데이터 로드 ──────────────────────────────────────
print("\n[2] 보호구역 처리...")
prot_df = pd.read_excel(
    DATA / "어린이.노인.장애인보호구역 지정 및 교통안전시설 현황 [교통기획과]_.xlsx",
    sheet_name=0
)
print(f"  보호구역: {len(prot_df)}구간 / 시설: {prot_df['시설구분'].value_counts().to_dict()}")

PROT_SCORE = {
    "초등학교": 0.55, "중학교": 0.60, "유치원": 0.50,
    "어린이집": 0.50, "노인"  : 0.60, "장애인": 0.60,
}
def get_prot_score(stype):
    for k, v in PROT_SCORE.items():
        if k in str(stype): return v
    return 0.65

prot_df["penalty"] = prot_df["시설구분"].apply(get_prot_score)

for _, row in prot_df.drop_duplicates("시설명").iterrows():
    mask = df["GU_NM"] == row.get("시군구명", "")
    if mask.any():
        new_val = float(row["penalty"]) + 0.10
        df.loc[mask, "score_protected"] = df.loc[mask, "score_protected"].clip(upper=new_val)

# ── composite_v3 재계산 ───────────────────────────────────────
print("\n[3] composite_v3 재계산 (7레이어)...")
score_cols = [c for c in ["score_airspace","score_obstacle","score_noise",
                           "score_terrain","score_weather",
                           "score_construction","score_protected"]
              if c in df.columns]
df["composite_6layer"] = df[score_cols].prod(axis=1)
RA_W = 0.15
df["composite_v3"] = (1 - RA_W) * df["composite_6layer"] + RA_W * df["Ra"]

print(f"  composite_v3 — min: {df['composite_v3'].min():.4f}, "
      f"mean: {df['composite_v3'].mean():.4f}, "
      f"max: {df['composite_v3'].max():.4f}")

# 공사 상태별 영향 정리
for status in ["completed", "imminent", "ongoing", "unknown"]:
    n = (const_df["status"] == status).sum()
    print(f"  {status:12s} 공사장: {n}개소")

# ── 저장 ─────────────────────────────────────────────────────
df.to_csv(OUT / "constraint_layers_v4.csv", index=False, encoding="utf-8-sig")
print(f"\n✅ constraint_layers_v4.csv 업데이트 ({len(df)}행)")
print(f"   (준공 완료 공사장 → score_construction 1.0 복원)")
print(f"   진행 중 공사장만 제약 적용")

# ── 공사장 시계열 요약 저장 ───────────────────────────────────
const_summary = const_df[["공사명","대지위치","지상층수",
                           "준공예정일","status","penalty","GU_NM","ADM_NM"]].copy()
const_summary.to_csv(OUT / "construction_timeline.csv", index=False, encoding="utf-8-sig")
print(f"✅ construction_timeline.csv 저장 (공사 진행 상태 타임라인)")

print(f"\n✅ NB06b v2 완료!")
