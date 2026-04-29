# 성남시 드론·로봇 융합 배송 거점 최적화 프로젝트

> **팀명:** Aero-Logic  
> **대회:** 2026 성남시 공공데이터 활용·시각화 경진대회  
> **목적:** 성남시 내 최적 드론·로봇 배송 거점(Hub) 위치 선정 및 시각화

---

## 프로젝트 개요

성남시의 공공데이터(행정경계, 건물, 지형, 인구 유동, 카드 매출 등)와 민간데이터를 결합하여, **드론·로봇 배송에 최적화된 거점 위치**를 과학적으로 선정하고 시각화한 프로젝트입니다.

- **공간 단위:** H3 헥사곤 그리드 (해상도 9) → 성남시 전역 1,947개 셀
- **행정 단위:** 3개 구, 50개 동
- **후보 거점:** 공공시설 172개소 (공영주차장, 도서관 등)
- **최종 선정:** 4개 거점 (그리디 최적화 알고리즘)
- **서비스 반경:** 반경 500m

---

## 디렉토리 구조

```
Aero-Logic-seongnam/
├── 00_info/            # 공모 공고문, 제출 서식, 제안서
├── 01_preprocessing/   # 데이터 전처리 Jupyter 노트북 (6개)
├── 02_analysis/        # 분석 Jupyter 노트북 (6개)
├── 03_visualization/   # 인터랙티브 대시보드 및 Tableau 연동
├── processed/          # 전처리 완료 중간 데이터 (~58 MB)
└── EDA&Analysis.zip    # 초기 탐색적 분석 아카이브
```

---

## 데이터 파이프라인

### 1단계 — 전처리 (`01_preprocessing/`)

| 노트북 | 내용 | 출력 |
|--------|------|------|
| NB01 | 행정경계 클리핑 | `seongnam_boundary.gpkg` |
| NB02 | 건물 풋프린트 + 높이 추출 (Vworld API) | `seongnam_buildings.gpkg` (54 MB) |
| NB03 | DEM 지형 데이터 + 경사도 분석 | 경사도 레이어 |
| NB04 | 카드 매출 집계 (배달의민족 2023) | `card_sales_agg.parquet` |
| NB05 | 모바일 유동 인구 집계 | `flow_population_agg.parquet` |
| NB06 | 공공시설 지오코딩 (172개소) | `public_facilities.gpkg` |

### 2단계 — 분석 (`02_analysis/`)

| 노트북 | 내용 | 출력 |
|--------|------|------|
| NB08 | 배송 수요 긴급도 지수 산출 | `delivery_urgency_grid.gpkg` |
| NB09 | 5개 제약 레이어 복합 점수화 | `constraint_layers.gpkg` |
| NB10 | 그리디 Set-Cover 최적화 → **거점 4개 선정** | `final_hubs.gpkg` |
| NB11 | 배송 경로 분석 (20개 경로) | `drone_routes.geojson` |
| NB12 | 오토바이 vs 드론/로봇 비교 (9개 지표) | `mode_comparison.csv` |
| NB_EXPORT | Tableau용 데이터 패키징 | `tableau_data/` (12개 파일) |

#### 복합 점수 모델

```
composite_score = score_airspace × score_obstacle × score_noise × score_terrain × score_weather
```

| 레이어 | 설명 |
|--------|------|
| `score_airspace` | 공역 규제 (KSA 고시) 준수 여부 |
| `score_obstacle` | 건물 밀도 및 고층 장애물 |
| `score_noise` | 주거지 근접 소음 영향 |
| `score_terrain` | 지형 경사도 |
| `score_weather` | 기상 (풍향·풍속) 패턴 |

### 3단계 — 시각화 (`03_visualization/`)

| 결과물 | 설명 |
|--------|------|
| `dashboard.html` | 서버 불필요한 단독 실행형 인터랙티브 지도 대시보드 |
| `seongnam_drone_hub_v2.twbx` | Tableau 워크북 (5개 시트, 1개 대시보드) |
| Tableau Cloud | 12개 데이터소스 게시 완료 |

---

## 핵심 기술 스택

- **분석:** Python 3, Pandas, GeoPandas, H3, Shapely
- **시각화 (웹):** Leaflet.js, Plotly.js (인터랙티브 HTML)
- **BI:** Tableau Cloud (Hyper API, Tableau Server Client)
- **데이터 형식:** GeoPackage (.gpkg), Parquet, GeoJSON, CSV
- **버전 관리:** Git (브랜치: master, feature/nynji, hyeonseo, sohyun)

---

## 현재 진행 상태

### 완료된 항목 ✅

- [x] 데이터 전처리 파이프라인 (NB01~NB06) 전체 실행 완료
- [x] 5개 제약 레이어 복합 점수 계산 완료
- [x] 그리디 최적화로 **최종 거점 4개** 선정 완료
- [x] 배송 경로 분석 (20개 경로 생성) 완료
- [x] 인터랙티브 HTML 대시보드 (`dashboard.html`) 구현 완료
  - 제약 레이어 토글 (5개)
  - POI 오버레이 (공원·상업·의료·지하철·학교)
  - 실시간 그리디 재계산
  - KPI 카드 (셀 수, 커버리지 %, 복합 점수 평균)
  - 4개 차트 (동별 순위, 시간대별 수요, 레이더, 가능 비율)
- [x] Tableau Hyper 추출 파일 12개 생성 및 Cloud 게시 완료
- [x] TWBX 워크북 자동 생성 스크립트 완료

### 진행 중 / 잔여 항목 ⚠️

- [ ] 공모전 제출 서식 작성 (`[붙임2]`, `[붙임3]` 미작성)
- [ ] Tableau 웹 UI에서 대시보드 수동 조립 (가이드 제공됨: `TABLEAU_대시보드_가이드.md`)
- [ ] 제안서 최종 검토 및 보완 (`제안서.docx`)
- [ ] 발표 자료 제작 (`[붙임3] 발표자료 양식.pptx` 사용)

---

## 팀 구성 및 협업

| 브랜치 | 담당 |
|--------|------|
| `master` | 메인 통합 |
| `feature/nynji` | 현재 HEAD |
| `hyeonseo` | 원격 브랜치 |
| `sohyun` | 원격 브랜치 |

- **Tableau Cloud 계정:** `jimin076721-be93e49158`
- **Tableau 프로젝트명:** `성남시_드론배송_거점최적화`

---

## 주요 분석 결과 요약

| 항목 | 수치 |
|------|------|
| 분석 대상 셀 수 | 1,947개 H3 셀 |
| 후보 거점 수 | 172개 공공시설 |
| **최종 선정 거점 수** | **4개** |
| 서비스 반경 | 500m |
| 생성된 배송 경로 | 20개 |
| 분석 행정동 수 | 50개 동 |
| Tableau 데이터소스 | 12개 |

---

## 실행 방법

### 인터랙티브 대시보드 열기

```bash
# 별도 서버 불필요 — 브라우저에서 직접 열기
open 03_visualization/dashboard.html
```

### Tableau Cloud 게시

```bash
cd 03_visualization
python publish_to_tableau.py --pat-name <토큰명> --pat-secret <토큰값>
```

### 전체 파이프라인 재실행

```bash
# 01_preprocessing → 02_analysis → 03_visualization 순서로 실행
jupyter nbconvert --to notebook --execute 01_preprocessing/NB01_admin_boundary_clip.ipynb
# ... (NB01~NB06, NB08~NB12, NB_EXPORT 순서대로)
python 03_visualization/build_dashboard.py
```

---

*최종 업데이트: 2026-04-29*
