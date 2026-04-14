"""
성남시 드론·로봇 배송 거점 최적화 — Tableau Cloud 퍼블리시 스크립트
=================================================================
1) CSV/GeoJSON → Hyper 추출 파일 생성
2) Hyper 파일 → Tableau Cloud 에 데이터소스로 게시
3) 필요 시 프로젝트 자동 생성

사용법:
  python publish_to_tableau.py --pat-name "MY_TOKEN" --pat-secret "xxxxxxxx"

PAT(개인용 액세스 토큰) 발급:
  Tableau Cloud → 내 계정 설정 → 개인용 액세스 토큰 → 토큰 만들기
"""
import argparse, os, sys, json
import pandas as pd
from pathlib import Path

# ── Windows SSL fix: use native cert store ────────────────────
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

# ── Tableau libraries ─────────────────────────────────────────
from tableauhyperapi import (
    HyperProcess, Telemetry, Connection, CreateMode,
    TableDefinition, TableName, SqlType, Inserter, NOT_NULLABLE, NULLABLE,
)
import tableauserverclient as TSC

# ── Paths ─────────────────────────────────────────────────────
BASE = Path(__file__).parent
DATA_DIR = BASE / "tableau_data"
HYPER_DIR = BASE / "hyper_extracts"
HYPER_DIR.mkdir(exist_ok=True)

SERVER_URL = "https://prod-kr-a.online.tableau.com"
SITE_NAME = "jimin076721-be93e49158"
PROJECT_NAME = "성남시_드론배송_거점최적화"


# ═══════════════════════════════════════════════════════════════
# STEP 1 — CSV / GeoJSON → Hyper
# ═══════════════════════════════════════════════════════════════

def csv_to_hyper(csv_path: Path, hyper_path: Path, table_name: str):
    """범용 CSV → Hyper 변환."""
    df = pd.read_csv(csv_path)
    df = df.fillna("")  # NULL → 빈 문자열 (Hyper 호환)

    # 컬럼 타입 매핑
    col_defs = []
    for col in df.columns:
        dtype = df[col].dtype
        if pd.api.types.is_integer_dtype(dtype):
            col_defs.append(TableDefinition.Column(col, SqlType.big_int(), NULLABLE))
        elif pd.api.types.is_float_dtype(dtype):
            col_defs.append(TableDefinition.Column(col, SqlType.double(), NULLABLE))
        else:
            col_defs.append(TableDefinition.Column(col, SqlType.text(), NULLABLE))

    table_def = TableDefinition(TableName("Extract", table_name), col_defs)

    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        with Connection(hyper.endpoint, str(hyper_path), CreateMode.CREATE_AND_REPLACE) as conn:
            conn.catalog.create_schema_if_not_exists("Extract")
            conn.catalog.create_table(table_def)

            with Inserter(conn, table_def) as inserter:
                for _, row in df.iterrows():
                    values = []
                    for col_def, val in zip(col_defs, row):
                        if pd.isna(val) or val == "":
                            values.append(None)
                        elif col_def.type == SqlType.big_int():
                            values.append(int(val) if val != "" else None)
                        elif col_def.type == SqlType.double():
                            values.append(float(val) if val != "" else None)
                        else:
                            values.append(str(val))
                    inserter.add_row(values)
                inserter.execute()

    print(f"  [OK] {csv_path.name} -> {hyper_path.name} ({len(df)} rows)")


def geojson_to_hyper(geojson_path: Path, hyper_path: Path, table_name: str):
    """GeoJSON → Hyper: 속성 + WKT geometry 컬럼."""
    with open(geojson_path, encoding="utf-8") as f:
        gj = json.load(f)

    features = gj.get("features", [])
    if not features:
        print(f"  [SKIP] {geojson_path.name} - no features")
        return

    # 속성 컬럼 추출
    props_keys = list(features[0]["properties"].keys())

    # DataFrame으로 변환
    rows = []
    for feat in features:
        row = {k: feat["properties"].get(k) for k in props_keys}
        # geometry → WKT (간이 변환)
        geom = feat.get("geometry", {})
        row["geometry_wkt"] = _geojson_geom_to_wkt(geom)
        rows.append(row)

    df = pd.DataFrame(rows)
    all_cols = props_keys + ["geometry_wkt"]

    col_defs = []
    for col in all_cols:
        if col in df.columns:
            dtype = df[col].dtype
            if pd.api.types.is_integer_dtype(dtype):
                col_defs.append(TableDefinition.Column(col, SqlType.big_int(), NULLABLE))
            elif pd.api.types.is_float_dtype(dtype):
                col_defs.append(TableDefinition.Column(col, SqlType.double(), NULLABLE))
            else:
                col_defs.append(TableDefinition.Column(col, SqlType.text(), NULLABLE))

    table_def = TableDefinition(TableName("Extract", table_name), col_defs)

    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        with Connection(hyper.endpoint, str(hyper_path), CreateMode.CREATE_AND_REPLACE) as conn:
            conn.catalog.create_schema_if_not_exists("Extract")
            conn.catalog.create_table(table_def)

            with Inserter(conn, table_def) as inserter:
                for _, row in df.iterrows():
                    values = []
                    for cd in col_defs:
                        val = row.get(cd.name.unescaped, None)
                        if pd.isna(val):
                            values.append(None)
                        elif cd.type == SqlType.big_int():
                            values.append(int(val))
                        elif cd.type == SqlType.double():
                            values.append(float(val))
                        else:
                            values.append(str(val))
                    inserter.add_row(values)
                inserter.execute()

    print(f"  [OK] {geojson_path.name} -> {hyper_path.name} ({len(features)} features)")


def _geojson_geom_to_wkt(geom: dict) -> str:
    """간이 GeoJSON geometry → WKT 변환."""
    gtype = geom.get("type", "")
    coords = geom.get("coordinates", [])

    if gtype == "Point":
        return f"POINT ({coords[0]} {coords[1]})"
    elif gtype == "LineString":
        pts = ", ".join(f"{c[0]} {c[1]}" for c in coords)
        return f"LINESTRING ({pts})"
    elif gtype == "Polygon":
        rings = []
        for ring in coords:
            pts = ", ".join(f"{c[0]} {c[1]}" for c in ring)
            rings.append(f"({pts})")
        return f"POLYGON ({', '.join(rings)})"
    elif gtype == "MultiPolygon":
        polys = []
        for polygon in coords:
            rings = []
            for ring in polygon:
                pts = ", ".join(f"{c[0]} {c[1]}" for c in ring)
                rings.append(f"({pts})")
            polys.append(f"({', '.join(rings)})")
        return f"MULTIPOLYGON ({', '.join(polys)})"
    return ""


def build_all_hyper():
    """모든 데이터를 Hyper 추출 파일로 변환."""
    print("\n=== STEP 1: Hyper 추출 파일 생성 ===\n")

    # CSV files
    csvs = {
        "grid_scores.csv": "grid_scores",
        "final_hubs.csv": "final_hubs",
        "dong_summary.csv": "dong_summary",
        "hourly_demand.csv": "hourly_demand",
        "mode_comparison.csv": "mode_comparison",
        "mode_radar_scores.csv": "mode_radar_scores",
        "public_facilities.csv": "public_facilities",
        "delivery_routes_summary.csv": "delivery_routes_summary",
    }
    for fname, tname in csvs.items():
        csv_path = DATA_DIR / fname
        if csv_path.exists():
            csv_to_hyper(csv_path, HYPER_DIR / f"{tname}.hyper", tname)

    # GeoJSON files
    geojsons = {
        "grid_hexagons.geojson": "grid_hexagons",
        "final_hubs.geojson": "hub_locations",
        "drone_routes.geojson": "drone_routes",
        "service_areas.geojson": "service_areas",
    }
    for fname, tname in geojsons.items():
        gj_path = DATA_DIR / fname
        if gj_path.exists():
            geojson_to_hyper(gj_path, HYPER_DIR / f"{tname}.hyper", tname)

    print(f"\n  총 {len(list(HYPER_DIR.glob('*.hyper')))}개 Hyper 파일 생성 완료")
    print(f"  경로: {HYPER_DIR}")


# ═══════════════════════════════════════════════════════════════
# STEP 2 — Hyper → Tableau Cloud 게시
# ═══════════════════════════════════════════════════════════════

def publish_to_cloud(pat_name: str, pat_secret: str):
    """Hyper 파일을 Tableau Cloud에 데이터소스로 게시."""
    print(f"\n=== STEP 2: Tableau Cloud 게시 ===\n")
    print(f"  서버: {SERVER_URL}")
    print(f"  사이트: {SITE_NAME}")

    # 인증
    tableau_auth = TSC.PersonalAccessTokenAuth(
        token_name=pat_name,
        personal_access_token=pat_secret,
        site_id=SITE_NAME,
    )

    server = TSC.Server(SERVER_URL, use_server_version=True)

    # Windows Anaconda SSL 인증서 문제 해결
    import certifi
    server.add_http_options({"verify": certifi.where()})

    with server.auth.sign_in(tableau_auth):
        print(f"  [OK] 인증 성공")

        # 프로젝트 찾기 또는 생성
        project_id = _get_or_create_project(server, PROJECT_NAME)

        # Hyper 파일 게시
        hyper_files = sorted(HYPER_DIR.glob("*.hyper"))
        for hf in hyper_files:
            ds_name = hf.stem.replace("_", " ").title()
            print(f"\n  게시 중: {hf.name} -> '{ds_name}'")

            publish_mode = TSC.Server.PublishMode.Overwrite
            ds_item = TSC.DatasourceItem(project_id, name=ds_name)

            try:
                ds_item = server.datasources.publish(
                    ds_item, str(hf), publish_mode
                )
                print(f"  [OK] 게시 완료: {ds_item.name} (ID: {ds_item.id})")
            except Exception as e:
                print(f"  [ERROR] {e}")

    print(f"\n=== 게시 완료 ===")
    print(f"  Tableau Cloud에서 확인:")
    print(f"  {SERVER_URL}/#/site/{SITE_NAME}/datasources")


def _get_or_create_project(server, name):
    """프로젝트 찾기, 없으면 생성."""
    all_projects, _ = server.projects.get()
    for p in all_projects:
        if p.name == name:
            print(f"  [OK] 프로젝트 '{name}' 발견 (ID: {p.id})")
            return p.id

    # 생성
    new_project = TSC.ProjectItem(name=name, description="성남시 드론·로봇 배송 거점 최적 입지 분석")
    new_project = server.projects.create(new_project)
    print(f"  [OK] 프로젝트 '{name}' 생성 (ID: {new_project.id})")
    return new_project.id


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Tableau Cloud 데이터 게시")
    parser.add_argument("--pat-name", help="Personal Access Token 이름")
    parser.add_argument("--pat-secret", help="Personal Access Token 시크릿")
    parser.add_argument("--hyper-only", action="store_true",
                        help="Hyper 파일만 생성 (게시 안 함)")
    args = parser.parse_args()

    # Step 1: Hyper 생성
    build_all_hyper()

    # Step 2: 게시
    if args.hyper_only:
        print("\n  --hyper-only 모드: 게시 건너뜀")
    elif args.pat_name and args.pat_secret:
        publish_to_cloud(args.pat_name, args.pat_secret)
    else:
        print("\n  [INFO] PAT 미제공 — Hyper 파일만 생성됨")
        print("  게시하려면: python publish_to_tableau.py --pat-name NAME --pat-secret SECRET")
        print("\n  PAT 발급 방법:")
        print("  1. Tableau Cloud 로그인")
        print("  2. 우측 상단 프로필 아이콘 → '내 계정 설정'")
        print("  3. '개인용 액세스 토큰' 섹션")
        print("  4. 토큰 이름 입력 → '새 토큰 만들기'")
        print("  5. 토큰 이름과 시크릿 복사 (시크릿은 1회만 표시)")


if __name__ == "__main__":
    main()
