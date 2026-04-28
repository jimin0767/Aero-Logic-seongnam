"""
NB15_vertiport_candidates.py
==============================
버티포트(Transfer Zone) 후보지 도출

데이터 소스: OSM (공영주차장 / 주민센터 / 마트 / 학교 운동장)
→ 성남시 열린데이터광장 공영주차장 웹에서 없음 → OSM 대체

후보지 유형별 가중치:
  공영주차장     : 1.0  (드론 이착륙 최적 — 넓고 공공 부지)
  주민센터       : 0.9  (공공 부지 + 로봇 운영 협조 용이)
  대형마트/슈퍼  : 0.8  (기존 물류 인프라 활용)
  학교 운동장    : 0.6  (방과 후/주말만 사용 가능)
  공원/광장      : 0.7  (접근성 좋고 장애물 적음)

최종 선정 기준:
  - Hybrid/드론전용 Zoning 내 위치
  - 기존 final_hubs_v3 거점 1km 반경 내
  - composite_v3 > 0.05 (드론 운항 가능)

산출물:
  processed/vertiport_candidates.csv
  assets/js/vertiport.js
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
print("NB15 — 버티포트(Transfer Zone) 후보지 도출")
print("=" * 60)

# ── 기존 데이터 로드 ─────────────────────────────────────────
grid_df  = pd.read_csv(OUT / "constraint_layers_v4.csv", encoding="utf-8-sig")
hubs_df  = pd.read_csv(OUT / "final_hubs_v3.csv", encoding="utf-8-sig")

zone_df  = None
if (OUT / "delivery_zones.csv").exists():
    zone_df = pd.read_csv(OUT / "delivery_zones.csv", encoding="utf-8-sig",
                           usecols=["h3_index", "zone"])
    grid_df = grid_df.merge(zone_df, on="h3_index", how="left")
    grid_df["zone"] = grid_df["zone"].fillna("부적합")

print(f"그리드: {len(grid_df)}행, 거점: {len(hubs_df)}개")

# ── OSM에서 시설물 추출 ───────────────────────────────────────
print("\n[1] OSM 시설물 추출...")

try:
    import osmnx as ox

    SEONGNAM_PLACE = "성남시, 경기도, 대한민국"

    # 캐시 설정
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(BASE / "cache")

    facility_types = {
        "공영주차장"  : {"amenity": ["parking"]},
        "주민센터"    : {"amenity": ["community_centre", "townhall"]},
        "대형마트"    : {"shop": ["supermarket", "mall", "department_store"]},
        "공원"        : {"leisure": ["park", "playground"]},
        "학교"        : {"amenity": ["school", "university"]},
    }

    WEIGHTS = {
        "공영주차장": 1.0,
        "주민센터"  : 0.9,
        "대형마트"  : 0.8,
        "공원"      : 0.7,
        "학교"      : 0.6,
    }

    all_facilities = []

    for ftype, tags in facility_types.items():
        try:
            gdf = ox.features_from_place(SEONGNAM_PLACE, tags=tags)
            # 중심점 계산
            gdf = gdf.copy()
            gdf["lat"] = gdf.geometry.centroid.y
            gdf["lon"] = gdf.geometry.centroid.x
            # 이름 추출
            gdf["name"] = gdf.get("name", pd.Series([""] * len(gdf)))
            # 필터: 성남시 경계 내
            gdf = gdf[(gdf["lat"] >= 37.33) & (gdf["lat"] <= 37.50) &
                      (gdf["lon"] >= 127.00) & (gdf["lon"] <= 127.20)]

            for _, row in gdf.iterrows():
                all_facilities.append({
                    "name"   : str(row.get("name", ftype)),
                    "type"   : ftype,
                    "weight" : WEIGHTS[ftype],
                    "lat"    : round(float(row["lat"]), 6),
                    "lon"    : round(float(row["lon"]), 6),
                })
            print(f"  {ftype}: {len(gdf)}개")
        except Exception as e:
            print(f"  {ftype}: 오류 — {e}")

    fac_df = pd.DataFrame(all_facilities)
    print(f"  → 전체 시설물: {len(fac_df)}개")

except ImportError:
    print("  osmnx 없음 — 주요 공공시설 수동 정의")
    # 성남시 주요 공공시설 수동 입력 (주민센터 + 공원 + 마트)
    fac_df = pd.DataFrame([
        {"name": "판교공영주차장",     "type": "공영주차장", "weight": 1.0, "lat": 37.3943, "lon": 127.1098},
        {"name": "분당구청",           "type": "주민센터",   "weight": 0.9, "lat": 37.3837, "lon": 127.1234},
        {"name": "수정구청",           "type": "주민센터",   "weight": 0.9, "lat": 37.4362, "lon": 127.1381},
        {"name": "중원구청",           "type": "주민센터",   "weight": 0.9, "lat": 37.4410, "lon": 127.1471},
        {"name": "서현역 광장",        "type": "공원",       "weight": 0.7, "lat": 37.3836, "lon": 127.1237},
        {"name": "율동공원",           "type": "공원",       "weight": 0.7, "lat": 37.3728, "lon": 127.1261},
        {"name": "탄천공원",           "type": "공원",       "weight": 0.7, "lat": 37.4011, "lon": 127.1261},
        {"name": "이마트 판교점",      "type": "대형마트",   "weight": 0.8, "lat": 37.3901, "lon": 127.0980},
        {"name": "코스트코 양재",      "type": "대형마트",   "weight": 0.8, "lat": 37.4630, "lon": 127.0340},
        {"name": "야탑역 광장",        "type": "공원",       "weight": 0.7, "lat": 37.4119, "lon": 127.1275},
        {"name": "모란역 광장",        "type": "공영주차장", "weight": 1.0, "lat": 37.4349, "lon": 127.1302},
        {"name": "수내역 광장",        "type": "공원",       "weight": 0.7, "lat": 37.3788, "lon": 127.1177},
    ])
    print(f"  수동 정의: {len(fac_df)}개")

# ── H3 셀 매핑 ─────────────────────────────────────────────
print("\n[2] H3 셀 매핑 (반경 500m 내 그리드 검색)...")

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlam/2)**2
    return 2 * R * np.arcsin(np.sqrt(a))

lat_g = grid_df["lat"].values
lon_g = grid_df["lon"].values

vertiport_candidates = []
for _, fac in fac_df.iterrows():
    dists = haversine_m(lat_g, lon_g, fac["lat"], fac["lon"])
    nearest_idx = np.argmin(dists)
    nearest_dist = dists[nearest_idx]

    if nearest_dist > 800:  # 800m 이상이면 제외
        continue

    nearest_cell = grid_df.iloc[nearest_idx]
    zone = nearest_cell.get("zone", "일반")
    cv3  = float(nearest_cell.get("composite_v3", 0))
    ds3  = float(nearest_cell.get("Ds_v3", 0))
    ra   = float(nearest_cell.get("Ra", 0))

    # 버티포트 적합성 점수
    zone_bonus = {"드론전용": 0.3, "Hybrid": 0.2, "로봇전용": 0.1, "일반": 0.0, "부적합": -0.5}
    vtp_score = (fac["weight"] * 0.4 + cv3 * 0.3 + ds3 * 0.2 +
                 zone_bonus.get(zone, 0))

    vertiport_candidates.append({
        "name"       : fac["name"],
        "type"       : fac["type"],
        "facility_weight": fac["weight"],
        "lat"        : fac["lat"],
        "lon"        : fac["lon"],
        "h3_index"   : nearest_cell["h3_index"],
        "ADM_NM"     : nearest_cell["ADM_NM"],
        "GU_NM"      : nearest_cell["GU_NM"],
        "zone"       : zone,
        "composite_v3": round(cv3, 4),
        "Ds_v3"      : round(ds3, 4),
        "Ra"         : round(ra, 4),
        "dist_to_grid_m": round(float(nearest_dist), 0),
        "vtp_score"  : round(vtp_score, 4),
    })

vtp_df = pd.DataFrame(vertiport_candidates).sort_values("vtp_score", ascending=False)
print(f"  후보지 {len(vtp_df)}개 도출")

# ── 거점(hub) 근접성 필터 ─────────────────────────────────────
print("\n[3] 기존 거점 반경 1km 내 후보 우선 선정...")
hub_lats = hubs_df["lat"].values
hub_lons = hubs_df["lon"].values

def min_dist_to_hub(lat, lon):
    dists = haversine_m(hub_lats, hub_lons, lat, lon)
    return dists.min()

vtp_df["dist_to_hub_m"] = vtp_df.apply(
    lambda r: round(min_dist_to_hub(r["lat"], r["lon"]), 0), axis=1
)
vtp_df["near_hub"] = vtp_df["dist_to_hub_m"] <= 1500

print(f"\n  [상위 버티포트 후보 (TOP 10)]")
cols_show = ["name","type","zone","vtp_score","dist_to_hub_m","ADM_NM"]
print(vtp_df[cols_show].head(10).to_string(index=False))

# ── 저장 ─────────────────────────────────────────────────────
vtp_df.to_csv(OUT / "vertiport_candidates.csv", index=False, encoding="utf-8-sig")
print(f"\n✅ vertiport_candidates.csv 저장 ({len(vtp_df)}개)")

# ── vertiport.js 생성 ────────────────────────────────────────
TYPE_COLORS = {
    "공영주차장": "#42A5F5",
    "주민센터"  : "#66BB6A",
    "대형마트"  : "#FFA726",
    "공원"      : "#AB47BC",
    "학교"      : "#EF5350",
}
vtp_records = []
for _, row in vtp_df.iterrows():
    vtp_records.append({
        "name"     : row["name"],
        "type"     : row["type"],
        "lat"      : row["lat"],
        "lon"      : row["lon"],
        "dong"     : row["ADM_NM"],
        "gu"       : row["GU_NM"],
        "zone"     : row["zone"],
        "score"    : round(row["vtp_score"], 3),
        "near_hub" : bool(row["near_hub"]),
        "color"    : TYPE_COLORS.get(row["type"], "#9E9E9E"),
    })

vtp_js = f"""// Auto-generated by NB15_vertiport_candidates.py
// 버티포트(Transfer Zone) 후보지 — OSM 기반 공공시설 분석
const VERTIPORT_COLORS = {json.dumps(TYPE_COLORS, ensure_ascii=False)};
const VERTIPORTS = {json.dumps(vtp_records, ensure_ascii=False, indent=2)};
"""
(BASE / "assets" / "js" / "vertiport.js").write_text(vtp_js, encoding="utf-8")
print("✅ vertiport.js 저장")

print(f"\n✅ NB15 완료!")
print(f"  공영주차장: {len(vtp_df[vtp_df['type']=='공영주차장'])}개")
print(f"  주민센터:   {len(vtp_df[vtp_df['type']=='주민센터'])}개")
print(f"  대형마트:   {len(vtp_df[vtp_df['type']=='대형마트'])}개")
print(f"  공원:       {len(vtp_df[vtp_df['type']=='공원'])}개")
print(f"  → 거점 1.5km 내: {vtp_df['near_hub'].sum()}개")
