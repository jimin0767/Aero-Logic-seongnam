"""
NB07b_robot_access_index.py
============================
OpenStreetMap 보도/도로 데이터 → 로봇 접근성 지수(Ra) 산출 — 소현 작업

[개념]
  로봇(배송로봇)이 실제로 이동 가능한 구역을 H3 셀 단위로 정량화.
  법개정(지능형 로봇 개발 및 보급 촉진법)으로 횡단보도 이용 가능.

[데이터]
  OpenStreetMap (osmnx 자동 다운로드)
  - footway(인도), pedestrian(보행자도로), path(소로), crossing(횡단보도)

[산출 지수]
  Ra = 로봇 접근성 지수 (0~1)
     = 0.4 × (셀 내 인도 길이 비율)
     + 0.3 × (횡단보도 접근 가능 여부)
     + 0.3 × (보행 가능 도로 밀도)

[산출물]
  processed/robot_access_ra.csv       — 동별 Ra 지수
  processed/constraint_layers_v3_ra.csv — Ra 포함 최종 레이어
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

BASE = Path(r"C:\Users\pasoh\OneDrive\문서\GitHub\Aero-Logic-seongnam")
OUT  = BASE / "processed"

print("=" * 60)
print("NB07b 로봇 접근성 지수(Ra) 산출")
print("=" * 60)

# ── osmnx 로드 ───────────────────────────────────────────────────────────────
try:
    import osmnx as ox
    import geopandas as gpd
    from shapely.geometry import Point
    print(f"  osmnx {ox.__version__} 로드 완료")
    HAS_OSM = True
except ImportError as e:
    print(f"  ⚠ {e}")
    HAS_OSM = False

# ── H3 그리드 로드 ───────────────────────────────────────────────────────────
constraint = pd.read_csv(OUT / "constraint_layers_v3.csv")
print(f"\nH3 그리드: {len(constraint)}개 셀")

if not HAS_OSM:
    print("\n⚠ osmnx 또는 geopandas 없음 — Ra=0으로 기본값 설정")
    constraint["Ra"] = 0.0
    constraint.to_csv(OUT / "constraint_layers_v3_ra.csv", index=False, encoding="utf-8-sig")
    print("  fallback constraint_layers_v3_ra.csv 저장")
    exit()

# ══════════════════════════════════════════════════════════════════════════════
#  STEP 1: 성남시 보행 네트워크 다운로드 (OSM)
# ══════════════════════════════════════════════════════════════════════════════
print("\n[STEP 1] 성남시 보행 네트워크 다운로드 (OSM)...")
print("  (첫 실행 시 1~3분 소요, 이후 캐시 사용)")

CACHE_PATH = OUT / "seongnam_walk_network.gpkg"

if CACHE_PATH.exists():
    print(f"  캐시 존재 — 로드: {CACHE_PATH}")
    edges = gpd.read_file(CACHE_PATH, layer="edges")
    nodes = gpd.read_file(CACHE_PATH, layer="nodes")
    print(f"  edges: {len(edges):,}개, nodes: {len(nodes):,}개")
else:
    print("  OSM에서 다운로드 중...")
    ox.settings.log_console = False

    # 성남시 보행 네트워크
    G = ox.graph_from_place(
        "Seongnam-si, Gyeonggi-do, South Korea",
        network_type="walk",
        retain_all=False,
        truncate_by_edge=True,
    )
    nodes, edges = ox.graph_to_gdfs(G, nodes=True, edges=True)
    edges = edges.to_crs("EPSG:4326")
    nodes = nodes.to_crs("EPSG:4326")

    print(f"  다운로드 완료: edges={len(edges):,}, nodes={len(nodes):,}")
    print(f"  도로 유형: {edges['highway'].value_counts().head(10).to_string()}")

    # 캐시 저장
    edges.to_file(CACHE_PATH, layer="edges", driver="GPKG")
    nodes.to_file(CACHE_PATH, layer="nodes", driver="GPKG")
    print(f"  캐시 저장: {CACHE_PATH}")

# ══════════════════════════════════════════════════════════════════════════════
#  STEP 2: 보행 도로 유형 분류
# ══════════════════════════════════════════════════════════════════════════════
print("\n[STEP 2] 보행 도로 유형 분류...")

# 인도/보행자 도로 (로봇 주행 적합)
FOOTWAY_TYPES = {
    "footway"     : 1.0,   # 전용 인도 — 최적
    "pedestrian"  : 1.0,   # 보행자 전용
    "path"        : 0.7,   # 소로 — 가능하나 폭 불확실
    "cycleway"    : 0.8,   # 자전거도로 (공유 가능)
    "living_street": 0.9,  # 생활도로
    "service"     : 0.6,   # 서비스도로
    "residential" : 0.5,   # 주거지 도로 (폭 좁을 수 있음)
    "unclassified": 0.4,
}

# highway 컬럼이 리스트인 경우 첫 번째 값만 추출
def extract_highway(h):
    if isinstance(h, list):
        return h[0] if h else "unknown"
    return str(h)

edges["highway_clean"] = edges["highway"].apply(extract_highway)
edges["robot_weight"]  = edges["highway_clean"].map(FOOTWAY_TYPES).fillna(0.3)
edges["length_m"]      = edges["length"] if "length" in edges.columns else edges.geometry.length * 111000

# 횡단보도 노드 추출
crossing_mask = (
    edges["highway_clean"].isin(["crossing"]) |
    edges.get("crossing", pd.Series("", index=edges.index)).notna()
)
crossings = edges[crossing_mask].copy()
print(f"  전체 엣지: {len(edges):,}")
print(f"  보행 가능 (weight>0.3): {(edges['robot_weight']>0.3).sum():,}")
print(f"  횡단보도: {len(crossings):,}")
print(f"\n  도로유형별 분포 (상위 10):")
print(edges["highway_clean"].value_counts().head(10).to_string())

# ══════════════════════════════════════════════════════════════════════════════
#  STEP 3: H3 셀에 공간 조인 → Ra 계산
# ══════════════════════════════════════════════════════════════════════════════
print("\n[STEP 3] H3 셀 ↔ 보행 네트워크 공간 조인...")

# H3 셀 중심점 GeoDataFrame
cell_gdf = gpd.GeoDataFrame(
    constraint[["h3_index", "lat", "lon", "ADM_NM", "GU_NM"]],
    geometry=[Point(lon, lat) for lat, lon in
              zip(constraint["lat"], constraint["lon"])],
    crs="EPSG:4326"
)

# 투영 좌표계로 변환 (거리 계산용)
cell_proj     = cell_gdf.to_crs("EPSG:5186")
edges_proj    = edges.to_crs("EPSG:5186")
crossings_proj = crossings.to_crs("EPSG:5186") if len(crossings) > 0 else crossings

# H3 res.9 셀 반경 ≈ 174m → 버퍼 200m 기준으로 주변 도로 집계
BUFFER_M = 200

print(f"  버퍼 반경: {BUFFER_M}m")
print(f"  총 {len(cell_proj)}개 셀 처리 중...")

ra_records = []
for idx, cell in cell_proj.iterrows():
    buf = cell.geometry.buffer(BUFFER_M)

    # 버퍼 내 보행 엣지 필터
    edges_in = edges_proj[edges_proj.geometry.intersects(buf)]

    if len(edges_in) == 0:
        ra_records.append({
            "h3_index"          : cell["h3_index"],
            "total_walk_length" : 0,
            "robot_walk_length" : 0,
            "n_crossings"       : 0,
            "avg_robot_weight"  : 0,
            "Ra"                : 0,
        })
        continue

    total_length  = edges_in["length_m"].sum()
    robot_length  = (edges_in["length_m"] * edges_in["robot_weight"]).sum()
    avg_weight    = edges_in["robot_weight"].mean()

    # 횡단보도 수
    if len(crossings_proj) > 0:
        cross_in = crossings_proj[crossings_proj.geometry.intersects(buf)]
        n_cross  = len(cross_in)
    else:
        n_cross = 0

    # Ra 구성 요소
    # 1. 인도 길이 비율 (버퍼 내 전체 보행 길이 대비 로봇 적합 길이)
    ratio_footway = robot_length / max(total_length, 1)

    # 2. 횡단보도 접근성 (있으면 1, 없으면 0)
    has_crossing = 1.0 if n_cross > 0 else 0.0

    # 3. 보행 도로 밀도 (버퍼 면적 대비 보행 길이, 정규화는 후처리)
    walk_density = total_length  # 절대값, 이후 Min-Max

    ra_records.append({
        "h3_index"          : cell["h3_index"],
        "total_walk_length" : round(total_length, 1),
        "robot_walk_length" : round(robot_length, 1),
        "n_crossings"       : n_cross,
        "avg_robot_weight"  : round(avg_weight, 4),
        "ratio_footway"     : round(ratio_footway, 4),
        "has_crossing"      : has_crossing,
        "walk_density_raw"  : walk_density,
    })

    if idx % 200 == 0:
        print(f"    {idx}/{len(cell_proj)} 처리 중...")

ra_df = pd.DataFrame(ra_records)
print(f"\n  처리 완료: {len(ra_df)}개 셀")

# ── Min-Max 정규화 후 Ra 합산 ─────────────────────────────────────────────────
def minmax(s):
    mn, mx = s.min(), s.max()
    return (s - mn) / (mx - mn) if mx > mn else pd.Series(0.0, index=s.index)

ra_df["ratio_footway_norm"] = minmax(ra_df.get("ratio_footway", pd.Series(0, index=ra_df.index)))
ra_df["walk_density_norm"]  = minmax(ra_df.get("walk_density_raw", pd.Series(0, index=ra_df.index)))
ra_df["has_crossing"]       = ra_df.get("has_crossing", pd.Series(0.0, index=ra_df.index))

ra_df["Ra"] = (
    0.4 * ra_df["ratio_footway_norm"]
  + 0.3 * ra_df["has_crossing"]
  + 0.3 * ra_df["walk_density_norm"]
)

print(f"\n  [Ra 통계]")
print(ra_df["Ra"].describe().round(4))
print(f"\n  Ra=0 (로봇 이동 불가): {(ra_df['Ra']==0).sum()}셀")
print(f"  Ra>0.5 (우수 접근성): {(ra_df['Ra']>0.5).sum()}셀")

# ══════════════════════════════════════════════════════════════════════════════
#  STEP 4: constraint_layers_v3에 Ra 통합 → v3_ra
# ══════════════════════════════════════════════════════════════════════════════
print("\n[STEP 4] Ra 통합 및 저장...")

constraint = constraint.merge(
    ra_df[["h3_index", "Ra", "total_walk_length", "robot_walk_length",
           "n_crossings", "avg_robot_weight"]],
    on="h3_index", how="left"
)
constraint["Ra"] = constraint["Ra"].fillna(0)

# 동별 Ra 요약 저장
ra_by_dong = (
    constraint.groupby("ADM_NM")
    .agg(
        avg_Ra          = ("Ra",                "mean"),
        max_Ra          = ("Ra",                "max"),
        robot_ok_cells  = ("Ra",                lambda x: (x > 0.3).sum()),
        total_cells     = ("Ra",                "count"),
    )
    .reset_index()
)
ra_by_dong["robot_ok_ratio"] = ra_by_dong["robot_ok_cells"] / ra_by_dong["total_cells"]
ra_by_dong = ra_by_dong.sort_values("avg_Ra", ascending=False)

print("\n  [동별 로봇 접근성 상위 10]")
print(ra_by_dong.head(10)[["ADM_NM", "avg_Ra", "robot_ok_cells", "total_cells", "robot_ok_ratio"]].round(4).to_string(index=False))

ra_by_dong.to_csv(OUT / "robot_access_ra.csv", index=False, encoding="utf-8-sig")
constraint.to_csv(OUT / "constraint_layers_v3_ra.csv", index=False, encoding="utf-8-sig")

print(f"\n  ✅ robot_access_ra.csv 저장")
print(f"  ✅ constraint_layers_v3_ra.csv 저장")

# ── 시각화 ────────────────────────────────────────────────────────────────────
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    plt.rcParams["axes.unicode_minus"] = False
    for fname in ["Malgun Gothic", "NanumGothic"]:
        try:
            fm.findfont(fname, fallback_to_default=False)
            plt.rcParams["font.family"] = fname
            break
        except Exception:
            pass

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("성남시 로봇 접근성 지수(Ra) 분석", fontsize=13)

    # 동별 Ra 막대차트
    top15 = ra_by_dong.head(15)
    axes[0].barh(top15["ADM_NM"][::-1], top15["avg_Ra"][::-1], color="#43A047", alpha=0.85)
    axes[0].set_xlabel("평균 Ra 지수")
    axes[0].set_title("동별 로봇 접근성 상위 15개")
    axes[0].grid(axis="x", alpha=0.3)

    # Ra 분포 히스토그램
    axes[1].hist(constraint["Ra"], bins=30, color="#1E88E5", alpha=0.8, edgecolor="white")
    axes[1].axvline(constraint["Ra"].mean(), color="red", ls="--", label=f"평균 {constraint['Ra'].mean():.3f}")
    axes[1].set_xlabel("Ra 지수")
    axes[1].set_ylabel("H3 셀 수")
    axes[1].set_title("Ra 지수 분포")
    axes[1].legend()
    axes[1].grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUT / "robot_access_chart.png", dpi=150, bbox_inches="tight")
    print(f"  ✅ robot_access_chart.png 저장")
except Exception as e:
    print(f"  ⚠ 차트 저장 실패: {e}")

print("\n✅ 로봇 접근성 지수(Ra) 산출 완료!")
print(f"   Ra = 0.4×(인도비율) + 0.3×(횡단보도) + 0.3×(보행밀도)")
print(f"   → NB09 constraint_layer_scoring에 score_robot 레이어로 추가 가능")
