"""
NB07_corporate_demand_index.py
==============================
기업/가맹점 데이터 → 배송 수요 지수 산출 — 소현 작업

[데이터]
  기업: D:/성남시/기업-*/기업/3. 법인 기업(cnt)/*.csv
        → induty_pri_nm, induty_med_nm, admi_nm, 기업 수
  가맹점: D:/성남시/카드-*/카드/3. 가맹점 정보(대민)(mer_s)/*.csv
          → card_tpbuz_nm_1/2, admi_cty_no, mer_cnt

[산출 지수]
  Ec: 기업 밀도 지수 (배달 수요 창출 기업 밀도)
      = 물류/유통 기업수×2.0 + 음식업×1.5 + 소매×1.0 + 사무용품×0.8 (동별 합계, Min-Max)
  Od_v2: 배달 주문 대리변수 정밀화
      = 배달/음식/편의점 업종 가맹점 수 비율 (동별, Min-Max)

[산출물]
  processed/corporate_density_ec.csv  — 동별 기업 밀도 지수
  processed/merchant_od_v2.csv        — 동별 배달 가맹점 비율 (Od_v2)
"""

import pandas as pd
import numpy as np
import glob
from pathlib import Path

BASE     = Path(r"C:\Users\pasoh\OneDrive\문서\GitHub\Aero-Logic-seongnam")
DATA_DIR = Path(r"D:\성남시")
OUT      = BASE / "processed"

print("=" * 60)
print("NB07 기업/가맹점 데이터 → Ec, Od_v2 지수 산출")
print("=" * 60)

# ══════════════════════════════════════════════════════════════════════════════
#  PART A: 기업 밀도 지수 (Ec)
# ══════════════════════════════════════════════════════════════════════════════
print("\n[PART A] 기업 밀도 지수(Ec) 산출...")

# 배달 수요 관련 업종 가중치 정의
# induty_pri_nm 기준 (대분류)
CORP_WEIGHTS = {
    "운수 및 창고업": 3.0,           # 물류창고 → 거점 후보 최고
    "도매 및 소매업": 2.0,           # 도매 물류 수요
    "숙박 및 음식점업": 1.5,         # 음식 배달 수요
    "제조업": 1.2,                   # 공장/사무용품 배달
    "전문, 과학 및 기술 서비스업": 1.0,  # 오피스 밀집 → 점심 배달
    "금융 및 보험업": 0.8,
    "정보통신업": 1.0,               # IT 기업 밀집 (분당 판교)
}

corp_files = sorted(glob.glob(str(DATA_DIR / "기업-*" / "기업" / "3. 법인 기업(cnt)" / "*.csv")))
print(f"  법인기업 파일: {len(corp_files)}개")

# 최근 12개월 파일 사용
corp_files_recent = corp_files[-12:]
dfs = []
for f in corp_files_recent:
    try:
        df = pd.read_csv(f, encoding="utf-8-sig")
        dfs.append(df)
    except Exception as e:
        print(f"  ⚠ {f}: {e}")

corp = pd.concat(dfs, ignore_index=True)
print(f"  로드 완료: {len(corp):,}행")
print(f"  컬럼: {corp.columns.tolist()}")
print(f"  대분류 업종: {corp['induty_pri_nm'].str.strip().unique()[:10]}")

# 동명 정제
corp["admi_nm"] = corp["admi_nm"].str.strip()

# 기업 수 집계: oc_comp_cn (기타법인) + co_ctx_comp_cn (협동조합 등) 합산
# vpap=유가증권, kosdaq=코스닥, oc=기타법인, co_ctx=협동조합
corp["total_corp"] = (
    corp["vpap_comp_cn"].fillna(0)
    + corp["kosdaq_comp_cn"].fillna(0)
    + corp["konex_comp_cn"].fillna(0)
    + corp["oc_comp_cn"].fillna(0)
    + corp["co_ctx_comp_cn"].fillna(0)
)

# 가중 기업 수 계산
corp["induty_pri_nm_clean"] = corp["induty_pri_nm"].str.strip()
corp["weight"] = corp["induty_pri_nm_clean"].map(CORP_WEIGHTS).fillna(0.5)
corp["weighted_corp"] = corp["total_corp"] * corp["weight"]

# 동별 집계 (12개월 평균)
ec_by_dong = (
    corp.groupby("admi_nm")
    .agg(
        avg_total_corp   = ("total_corp",    "mean"),
        avg_weighted_corp= ("weighted_corp", "mean"),
        top_industry     = ("induty_pri_nm_clean",
                            lambda x: x.value_counts().index[0] if len(x) > 0 else ""),
    )
    .reset_index()
)
ec_by_dong.rename(columns={"admi_nm": "ADM_NM"}, inplace=True)

# Min-Max 정규화
for col in ["avg_total_corp", "avg_weighted_corp"]:
    mn, mx = ec_by_dong[col].min(), ec_by_dong[col].max()
    ec_by_dong[f"{col}_norm"] = (ec_by_dong[col] - mn) / (mx - mn) if mx > mn else 0.0

# Ec 최종 지수 (가중 기업 수 기반)
ec_by_dong["Ec"] = ec_by_dong["avg_weighted_corp_norm"]

print(f"\n  동별 기업밀도 집계: {len(ec_by_dong)}개 동")
print("\n  [상위 10 동 — 기업 밀도]")
top10 = ec_by_dong.nlargest(10, "Ec")[["ADM_NM", "avg_total_corp", "avg_weighted_corp", "Ec", "top_industry"]]
print(top10.round(4).to_string(index=False))

ec_by_dong.to_csv(OUT / "corporate_density_ec.csv", index=False, encoding="utf-8-sig")
print(f"\n  ✅ corporate_density_ec.csv 저장 ({len(ec_by_dong)}행)")

# ══════════════════════════════════════════════════════════════════════════════
#  PART B: 배달 가맹점 기반 Od_v2 정밀화
# ══════════════════════════════════════════════════════════════════════════════
print("\n[PART B] 배달 가맹점 기반 Od_v2 산출...")

# 배달 관련 업종 코드 정의 (card_tpbuz_nm_1 / card_tpbuz_nm_2)
DELIVERY_CATEGORIES_L1 = {"음식", "소매/유통"}
DELIVERY_CATEGORIES_L2 = {
    "배달음식", "치킨", "피자/햄버거", "중식", "한식", "일식",
    "편의점", "슈퍼마켓", "대형마트", "제과/빵집", "음료/아이스크림"
}

mer_files = sorted(glob.glob(str(DATA_DIR / "카드-*" / "카드" / "3. 가맹점 정보(대민)(mer_s)" / "*.csv")))
print(f"  가맹점 파일: {len(mer_files)}개")

# 최근 12개월
mer_files_recent = mer_files[-12:]
dfs_mer = []
for f in mer_files_recent:
    try:
        df = pd.read_csv(f, encoding="cp949", sep="|")
        dfs_mer.append(df)
    except Exception as e:
        print(f"  ⚠ {f}: {e}")

mer = pd.concat(dfs_mer, ignore_index=True)
print(f"  로드 완료: {len(mer):,}행")
print(f"\n  card_tpbuz_nm_1 업종 분포:")
print(mer["card_tpbuz_nm_1"].value_counts().to_string())
print(f"\n  card_tpbuz_nm_2 상위 20:")
print(mer["card_tpbuz_nm_2"].value_counts().head(20).to_string())

# 배달 관련 가맹점 필터
is_delivery = (
    mer["card_tpbuz_nm_1"].isin(DELIVERY_CATEGORIES_L1) |
    mer["card_tpbuz_nm_2"].isin(DELIVERY_CATEGORIES_L2)
)
mer_delivery = mer[is_delivery].copy()
print(f"\n  전체 가맹점: {len(mer):,} → 배달 관련: {len(mer_delivery):,} ({len(mer_delivery)/len(mer):.1%})")

# 행정동 코드 기반 집계
# admi_cty_no = 법정동코드 (8자리)
# crosswalk으로 동명 매핑
crosswalk = pd.read_csv(OUT / "admin_code_crosswalk.csv")
print(f"\n  crosswalk 컬럼: {crosswalk.columns.tolist()}")
print(crosswalk.head(3).to_string())

# 동별 가맹점 집계
mer_agg = mer.groupby("admi_cty_no").agg(
    total_mer_cnt    = ("mer_cnt", "sum"),
).reset_index()

mer_del_agg = mer_delivery.groupby("admi_cty_no").agg(
    delivery_mer_cnt = ("mer_cnt", "sum"),
).reset_index()

mer_combined = mer_agg.merge(mer_del_agg, on="admi_cty_no", how="left")
mer_combined["delivery_mer_cnt"] = mer_combined["delivery_mer_cnt"].fillna(0)
mer_combined["delivery_ratio"] = (
    mer_combined["delivery_mer_cnt"] / mer_combined["total_mer_cnt"].replace(0, 1)
)

# crosswalk 매핑
mer_combined["admi_cty_no"] = mer_combined["admi_cty_no"].astype(str).str.zfill(8)
crosswalk_col = [c for c in crosswalk.columns if "CD" in c.upper() or "cd" in c.lower()][0]
crosswalk[crosswalk_col] = crosswalk[crosswalk_col].astype(str).str.zfill(8)
mer_combined = mer_combined.merge(
    crosswalk.rename(columns={crosswalk_col: "admi_cty_no"}),
    on="admi_cty_no", how="left"
)

# Min-Max 정규화 → Od_v2
mn, mx = mer_combined["delivery_mer_cnt"].min(), mer_combined["delivery_mer_cnt"].max()
mer_combined["Od_v2"] = (
    (mer_combined["delivery_mer_cnt"] - mn) / (mx - mn) if mx > mn else 0.0
)

print(f"\n  [상위 10 동 — 배달 가맹점 수]")
show_cols = [c for c in ["ADM_NM", "admi_cty_no", "total_mer_cnt", "delivery_mer_cnt", "delivery_ratio", "Od_v2"]
             if c in mer_combined.columns]
print(mer_combined.nlargest(10, "Od_v2")[show_cols].round(4).to_string(index=False))

mer_combined.to_csv(OUT / "merchant_od_v2.csv", index=False, encoding="utf-8-sig")
print(f"\n  ✅ merchant_od_v2.csv 저장 ({len(mer_combined)}행)")

# ══════════════════════════════════════════════════════════════════════════════
#  PART C: constraint_layers_v2에 Ec, Od_v2 통합
# ══════════════════════════════════════════════════════════════════════════════
print("\n[PART C] constraint_layers_v2에 Ec, Od_v2 통합...")

constraint = pd.read_csv(OUT / "constraint_layers_v2.csv")
print(f"  현재 컬럼: {constraint.columns.tolist()}")

# Ec 병합 (동명 기준)
constraint = constraint.merge(
    ec_by_dong[["ADM_NM", "Ec"]],
    on="ADM_NM", how="left"
)
constraint["Ec"] = constraint["Ec"].fillna(0)

# Od_v2 병합 (행정동 코드 기준)
od_cols = [c for c in mer_combined.columns if c in ["ADM_NM", "Od_v2", "admi_cty_no"]]
od_merge = mer_combined[od_cols].drop_duplicates()

if "admi_cty_no" in od_merge.columns:
    constraint["CSV_ADMI_CD_str"] = constraint["CSV_ADMI_CD"].astype(str).str.zfill(8)
    od_merge["admi_cty_no_str"] = od_merge["admi_cty_no"].astype(str).str.zfill(8)
    constraint = constraint.merge(
        od_merge[["admi_cty_no_str", "Od_v2"]].rename(columns={"admi_cty_no_str": "CSV_ADMI_CD_str"}),
        on="CSV_ADMI_CD_str", how="left"
    ).drop(columns=["CSV_ADMI_CD_str"])
elif "ADM_NM" in od_merge.columns:
    constraint = constraint.merge(
        od_merge[["ADM_NM", "Od_v2"]], on="ADM_NM", how="left"
    )

constraint["Od_v2"] = constraint.get("Od_v2", pd.Series(0, index=constraint.index)).fillna(0)

# 가중치 (팀 조정 가능)
W_HR = 0.25
W_FP = 0.20
W_CC = 0.20
W_EC = 0.20   # 기업 밀도 (신규)
W_OD = 0.15   # 배달 가맹점 (정밀화)

assert abs(W_HR + W_FP + W_CC + W_EC + W_OD - 1.0) < 1e-9

constraint["Ds_v3"] = (
    W_HR * constraint["Hr"]
  + W_FP * constraint["Fp"]
  + W_CC * constraint["Cc"]
  + W_EC * constraint["Ec"]
  + W_OD * constraint["Od_v2"]
)

print(f"\n  [Ds_v2 vs Ds_v3 비교]")
print(f"  Ds_v2: mean={constraint['Ds_v2'].mean():.4f}, std={constraint['Ds_v2'].std():.4f}")
print(f"  Ds_v3: mean={constraint['Ds_v3'].mean():.4f}, std={constraint['Ds_v3'].std():.4f}")
print(f"  상관계수: {constraint['Ds_v2'].corr(constraint['Ds_v3']):.4f}")

print("\n  [상위 10 동 Ds_v3]")
top = constraint.nlargest(10, "Ds_v3")[["ADM_NM", "GU_NM", "Hr", "Fp", "Cc", "Ec", "Od_v2", "Ds_v3"]].round(4)
print(top.to_string(index=False))

constraint.to_csv(OUT / "constraint_layers_v3.csv", index=False, encoding="utf-8-sig")
print(f"\n  ✅ constraint_layers_v3.csv 저장")
print(f"\n✅ 완료! Ds_v3 = {W_HR*100:.0f}%Hr + {W_FP*100:.0f}%Fp + {W_CC*100:.0f}%Cc + {W_EC*100:.0f}%Ec + {W_OD*100:.0f}%Od_v2")
