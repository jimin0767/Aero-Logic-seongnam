"""
NB16_welfare_facilities.py
===========================
경로당 + 다목적복지회관 + 여가의료주거시설 → 로봇 우선 배송 구역 도출

활용 전략:
  경로당 (817개)        : 고령자 밀집 → 로봇 배송 수요 최우선 구역
  다목적복지회관 (20개) : 드론/로봇 거점 및 배송 허브 후보
  여가의료주거시설 (9개) : 대형 노인복지관 → 고수요 배송 거점

분석 내용:
  1. 동명 기반 H3 셀 매핑
  2. 경로당 밀도 → welfare_density 지수 생성
  3. "로봇 우선 배송 구역" 플래그 추가 (score_welfare)
  4. Tableau TB06_welfare.csv, vertiport 업데이트

산출물:
  processed/welfare_facilities.csv
  processed/welfare_dong_density.csv
  processed/tableau/TB06_welfare.csv
  assets/js/welfare.js
"""

import pandas as pd
import numpy as np
import json, re
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

BASE = Path(r"C:\Users\pasoh\OneDrive\문서\GitHub\Aero-Logic-seongnam")
OUT  = BASE / "processed"
DATA = Path(r"D:\성남시")
TB   = OUT / "tableau"
TB.mkdir(exist_ok=True)

print("=" * 60)
print("NB16 — 노인복지시설 로봇 우선 배송 구역 분석")
print("=" * 60)

# ── 기존 그리드 로드 ─────────────────────────────────────────
grid = pd.read_csv(OUT / "constraint_layers_v4.csv", encoding="utf-8-sig")
if (OUT / "delivery_zones.csv").exists():
    zone_df = pd.read_csv(OUT / "delivery_zones.csv", encoding="utf-8-sig",
                           usecols=["h3_index", "zone"])
    grid = grid.merge(zone_df, on="h3_index", how="left")
    grid["zone"] = grid["zone"].fillna("일반")
print(f"그리드: {len(grid)}셀")

# ── 1. 경로당 로드 ─────────────────────────────────────────
print("\n[1] 경로당 (817개)...")
senior_df = pd.read_excel(DATA / "경로당 [노인복지과]_.xlsx")
senior_df["시설유형"] = "경로당"
senior_df["주소"]     = senior_df["도로명주소(변경)"]
senior_df["이름"]     = senior_df["경로당명"]
senior_df["동명"]     = senior_df["동명"].str.strip()
senior_df["회원수"]   = pd.to_numeric(senior_df["회원수(계)"], errors="coerce").fillna(0)
print(f"  {len(senior_df)}개소, 총 회원수: {senior_df['회원수'].sum():.0f}명")

# ── 2. 다목적복지회관 ──────────────────────────────────────
print("\n[2] 다목적복지회관 (20개)...")
welfare_df = pd.read_excel(DATA / "다목적복지회관 [노인복지과]_.xlsx")
welfare_df["시설유형"] = "다목적복지회관"
welfare_df["주소"]     = welfare_df["소재지"]
welfare_df["이름"]     = welfare_df["기관명"]
welfare_df["동명"]     = welfare_df["기관명"].str.extract(r'^(\S+동)')[0]
welfare_df["회원수"]   = 0
print(f"  {len(welfare_df)}개소")

# ── 3. 여가의료주거시설 ──────────────────────────────────────
print("\n[3] 여가의료주거시설 (9개)...")
medical_df = pd.read_excel(DATA / "여가의료주거시설 [노인복지과]_.xlsx")
medical_df["시설유형"] = "노인복지관"
medical_df["주소"]     = medical_df["주소"]
medical_df["이름"]     = medical_df["기관명"]
medical_df["동명"]     = medical_df["주소"].str.extract(r'(수정구|중원구|분당구)')[0]
medical_df["회원수"]   = pd.to_numeric(medical_df["시설현원"], errors="coerce").fillna(0)
print(f"  {len(medical_df)}개소, 총 이용자: {medical_df['회원수'].sum():.0f}명")

# ── 전체 병합 ─────────────────────────────────────────────
cols = ["시설유형", "이름", "주소", "동명", "회원수"]
all_df = pd.concat([
    senior_df[cols],
    welfare_df[cols],
    medical_df[cols],
], ignore_index=True)
print(f"\n전체 복지시설: {len(all_df)}개소")

# ── 동명 → 구 추출 ─────────────────────────────────────────
def extract_gu_dong(text):
    if pd.isna(text):
        return None, None
    text = str(text)
    gu   = re.search(r'(수정구|중원구|분당구)', text)
    dong = re.search(r'(\S+동)', text)
    return (gu.group(1) if gu else None), (dong.group(1) if dong else None)

# 경로당은 동명 컬럼 직접 활용
def get_gu_from_grid(dong_name):
    """그리드에서 동 이름으로 구 찾기"""
    match = grid[grid["ADM_NM"].str.contains(str(dong_name)[:4], na=False)]
    if len(match) > 0:
        return match["GU_NM"].iloc[0]
    return None

all_df["GU_NM"] = all_df["동명"].apply(
    lambda d: extract_gu_dong(d)[0] or get_gu_from_grid(d)
)
all_df["ADM_NM"] = all_df["동명"].apply(
    lambda d: extract_gu_dong(d)[1] or (str(d).strip() if pd.notna(d) else None)
)

# ── 동별 경로당 밀도 계산 ────────────────────────────────────
print("\n[동별 경로당 밀도 계산]")
dong_density = all_df.groupby("ADM_NM").agg(
    시설수    = ("시설유형", "count"),
    경로당수  = ("시설유형", lambda x: (x == "경로당").sum()),
    복지관수  = ("시설유형", lambda x: (x != "경로당").sum()),
    총회원수  = ("회원수", "sum"),
).reset_index()

# 셀수와 병합해서 밀도 계산
cell_count = grid.groupby("ADM_NM").size().reset_index(name="cell_count")
dong_density = dong_density.merge(cell_count, on="ADM_NM", how="left")
dong_density["facility_per_cell"] = dong_density["시설수"] / dong_density["cell_count"].clip(lower=1)

# 정규화 (0~1)
max_density = dong_density["facility_per_cell"].max()
dong_density["welfare_density"] = dong_density["facility_per_cell"] / max_density if max_density > 0 else 0

print(f"  동별 집계: {len(dong_density)}개 행정동")
print(f"  경로당 최다 동: {dong_density.nlargest(3, '경로당수')[['ADM_NM','경로당수']].to_string(index=False)}")
print(f"  복지 밀도 최고: {dong_density.nlargest(3, 'welfare_density')[['ADM_NM','welfare_density']].round(3).to_string(index=False)}")

# ── 그리드에 score_welfare 추가 ────────────────────────────
print("\n[그리드 score_welfare 추가]")
grid = grid.merge(dong_density[["ADM_NM", "welfare_density", "경로당수", "총회원수"]],
                  on="ADM_NM", how="left")
grid["welfare_density"] = grid["welfare_density"].fillna(0)
grid["경로당수"]         = grid["경로당수"].fillna(0)
grid["총회원수"]         = grid["총회원수"].fillna(0)

# 로봇 우선 배송 구역: 경로당 밀도 높고 Ra 좋은 셀
grid["robot_priority"] = (
    (grid["welfare_density"] > 0.3) &
    (grid["Ra"] > 0.4)
).astype(int)

n_priority = grid["robot_priority"].sum()
print(f"  로봇 우선 배송 구역: {n_priority}개 셀")
print(f"  구별 분포:")
if "GU_NM" in grid.columns:
    print(grid[grid["robot_priority"]==1].groupby("GU_NM")["robot_priority"].sum().to_string())

# ── 저장 ────────────────────────────────────────────────────
# 1. 전체 시설 목록
all_df.to_csv(OUT / "welfare_facilities.csv", index=False, encoding="utf-8-sig")
print(f"\n✅ welfare_facilities.csv ({len(all_df)}행)")

# 2. 동별 밀도
dong_density.to_csv(OUT / "welfare_dong_density.csv", index=False, encoding="utf-8-sig")
print(f"✅ welfare_dong_density.csv ({len(dong_density)}행)")

# 3. 그리드 업데이트 (welfare 컬럼 추가)
grid_update = grid[["h3_index","welfare_density","경로당수","총회원수","robot_priority"]]
# constraint_layers_v4에 병합
v4 = pd.read_csv(OUT / "constraint_layers_v4.csv", encoding="utf-8-sig")
for col in ["welfare_density","경로당수","총회원수","robot_priority"]:
    if col in v4.columns:
        v4 = v4.drop(columns=[col])
v4 = v4.merge(grid_update, on="h3_index", how="left")
for col in ["welfare_density","경로당수","총회원수","robot_priority"]:
    v4[col] = v4[col].fillna(0)
v4.to_csv(OUT / "constraint_layers_v4.csv", index=False, encoding="utf-8-sig")
print(f"✅ constraint_layers_v4.csv 업데이트 (+welfare 컬럼)")

# 4. Tableau TB06
tb06 = dong_density.copy()
tb06.to_csv(TB / "TB06_welfare.csv", index=False, encoding="utf-8-sig")
print(f"✅ TB06_welfare.csv")

# 5. welfare.js
# 경로당만 위치 정보 추출 (도로명 주소 기반)
facilities_js = []
TYPE_ICONS = {
    "경로당"       : "#FF7043",
    "다목적복지회관": "#26A69A",
    "노인복지관"   : "#AB47BC",
}
for _, row in all_df.iterrows():
    facilities_js.append({
        "name"  : str(row["이름"]),
        "type"  : str(row["시설유형"]),
        "dong"  : str(row["ADM_NM"]) if pd.notna(row["ADM_NM"]) else "",
        "gu"    : str(row["GU_NM"])   if pd.notna(row["GU_NM"])  else "",
        "members": int(row["회원수"]),
        "color" : TYPE_ICONS.get(str(row["시설유형"]), "#9E9E9E"),
    })

welfare_js = (
    f"// Auto-generated by NB16_welfare_facilities.py\n"
    f"// 노인복지시설: 경로당 {(all_df['시설유형']=='경로당').sum()}개 "
    f"| 복지관 {(all_df['시설유형']!='경로당').sum()}개\n"
    f"const WELFARE_FACILITIES = {json.dumps(facilities_js, ensure_ascii=False, indent=2)};\n\n"
    f"// 동별 복지 밀도 (로봇 우선 배송 구역)\n"
    f"const WELFARE_DENSITY = {json.dumps(dong_density.fillna(0).to_dict('records'), ensure_ascii=False, indent=2)};\n"
)
(BASE / "assets" / "js" / "welfare.js").write_text(welfare_js, encoding="utf-8")
print(f"✅ welfare.js ({len(facilities_js)}개 시설)")

print(f"\n{'='*50}")
print(f"✅ NB16 완료!")
print(f"   경로당 817개 → 로봇 우선 배송 구역 {n_priority}셀 식별")
print(f"   다음: NB_EXPORT 재실행 필요")
