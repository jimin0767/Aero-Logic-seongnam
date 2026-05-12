# Tableau Dashboard v3 - 구축 가이드 (한국어)

## 사전 준비

1. **Tableau Desktop** 설치 (2024.x 이상 권장)
2. [Google Fonts](https://fonts.google.com/specimen/Noto+Sans+KR)에서 **Noto Sans KR** 폰트 설치
3. 먼저 `prepare_tableau_data.py`를 실행해서 `data/` 폴더 안에 5개 CSV 파일을 생성

### 한국어 Tableau UI 표기 기준

이 문서는 **한국어 Tableau Desktop UI** 기준으로 작성했습니다. 괄호 안의 영어는 Tableau 자료를 검색할 때 참고용입니다.

| English UI | 한국어 Tableau UI |
|------------|-------------------|
| Data | 데이터 |
| New Data Source | 새 데이터 원본 |
| Text file | 텍스트 파일 |
| Data pane | 데이터 패널 |
| Create Parameter | 매개 변수 만들기 |
| Create Calculated Field | 계산된 필드 만들기 |
| Columns / Rows | 열 / 행 |
| Marks card | 마크 카드 |
| Detail / Color / Size / Label / Tooltip | 세부 정보 / 색상 / 크기 / 레이블 / 도구 설명 |
| Filters | 필터 |
| Path | 경로 |
| Sheet / Dashboard | 시트 / 대시보드 |
| New Dashboard | 새 대시보드 |
| Layout pane | 레이아웃 패널 |
| Show Parameter Control | 매개 변수 컨트롤 표시 |

---

## Phase 1: 데이터 원본 연결

Tableau Desktop을 열고, 각 CSV 파일에 대해 **데이터 > 새 데이터 원본 > 텍스트 파일**을 선택합니다.

| # | 파일 | 지리적 역할 |
|---|------|-------------|
| 1 | `data/grid_master.csv` | lat = Latitude, lon = Longitude |
| 2 | `data/scenario_hubs.csv` | lat = Latitude, lon = Longitude |
| 3 | `data/scenario_routes.csv` | route_lat = Latitude, route_lon = Longitude |
| 4 | `data/scenario_lookup.csv` | 없음 |
| 5 | `data/charts_bundle.csv` | 없음 |

**중요:** 각 CSV는 **서로 별도의 데이터 원본**입니다. Join하지 마세요.

지리적 역할 설정 방법:
지리적 역할 설정 방법:
필드를 우클릭한 뒤 **지리적 역할 > 위도/경도**를 선택합니다.

---

## Phase 2: 매개 변수 만들기 (총 9개)

아무 데이터 원본에서 **데이터 패널**을 우클릭한 뒤 **매개 변수 만들기...**를 선택합니다.

매개 변수는 전역으로 작동하므로 모든 데이터 원본에서 공유됩니다.

| Parameter Name | 표시 이름 | 데이터 타입 | 허용 값 | 기본값 |
|----------------|-----------|-------------|---------|--------|
| `p_demand_b2b` | B2B | Boolean | True / False | True |
| `p_demand_b2c` | B2C | Boolean | True / False | True |
| `p_demand_cv` | CV | Boolean | True / False | True |
| `p_con_airspace` | Airspace | Boolean | True / False | True |
| `p_con_obstacle` | Obstacle | Boolean | True / False | True |
| `p_con_noise` | Noise | Boolean | True / False | True |
| `p_con_robot` | Robot | Boolean | True / False | True |
| `p_con_weather` | Weather | Boolean | True / False | True |
| `p_airspace_mode` | Airspace Mode | String | List: `approval`, `strict` | `approval` |

---

## Phase 3: 계산된 필드 만들기

### 3A: `grid_master` 데이터 원본에서 만들 계산 필드

**데이터 패널**을 우클릭한 뒤 **계산된 필드 만들기**를 선택하고 아래 필드를 만듭니다.

#### `[Demand Score]`
```tableau
IIF(
  INT([p_demand_b2b]) + INT([p_demand_b2c]) + INT([p_demand_cv]) = 0,
  1.0,
  (IIF([p_demand_b2b], [demand_b2b], 0)
  + IIF([p_demand_b2c], [demand_b2c], 0)
  + IIF([p_demand_cv], [demand_cv], 0))
  / (INT([p_demand_b2b]) + INT([p_demand_b2c]) + INT([p_demand_cv]))
)
```

#### `[Constraint Score]`
```tableau
(IIF([p_con_airspace], [score_airspace], 1.0)
+ IIF([p_con_obstacle], [score_obstacle], 1.0)
+ IIF([p_con_noise], [score_noise], 1.0)
+ IIF([p_con_robot], [score_robot], 1.0)
+ IIF([p_con_weather], [score_weather], 1.0)) / 5
```

#### `[Final Score]`
```tableau
[Demand Score] * [Constraint Score]
```

#### `[Is Strict Excluded]`
```tableau
[hard_exclusion] AND [p_con_airspace] AND [p_airspace_mode] = "strict"
```

### 3B: `scenario_hubs` 데이터 원본에서 만들 계산 필드

#### `[Current Scenario ID]`
```tableau
"S" + RIGHT("000" + STR(
  (IIF(NOT [p_con_weather], 1, 0)
  + IIF(NOT [p_con_robot], 2, 0)
  + IIF(NOT [p_con_noise], 4, 0)
  + IIF(NOT [p_con_obstacle], 8, 0)
  + IIF(NOT [p_con_airspace], 16, 0))
  * 2
  + IIF([p_airspace_mode] = "strict", 1, 0)
  + 1
), 3)
```

#### `[Is Active Scenario]`
```tableau
[scenario_id] = [Current Scenario ID]
```

### 3C: `scenario_routes` 데이터 원본에서 만들 계산 필드

아래 두 계산 필드를 **3B와 동일한 수식**으로 만듭니다.

#### `[Current Scenario ID]`
3B의 `[Current Scenario ID]`와 같은 수식입니다.

#### `[Is Active Scenario]`
3B의 `[Is Active Scenario]`와 같은 수식입니다.

---

## Phase 4: 시트 만들기

### Sheet 1: "Map - H3 Grid" (`grid_master` 데이터 원본)

1. `lon`을 **열**로, `lat`을 **행**으로 드래그합니다. 둘 다 AVG, 연속형으로 둡니다.
2. `h3_index`를 **마크 카드 > 세부 정보**로 드래그합니다.
3. **마크 유형**을 **원(Circle)**으로 변경합니다.
4. `[Final Score]`를 **마크 카드 > 색상**으로 드래그합니다.
5. 색상을 편집합니다. Custom Diverging palette:
   - 3 stops: Red `#D32F2F` at 0.0, Yellow `#FDD835` at 0.5, Green `#4CAF50` at 1.0
   - Range: Fixed, Start: 0, End: 1
6. **마크 카드 > 크기**를 작고 고정된 값으로 설정합니다. 크기를 클릭한 뒤 슬라이더를 왼쪽으로 조정합니다.
7. **마크 카드 > 도구 설명**에 `ADM_NM`, `GU_NM`, `demand_b2b`, `demand_b2c`, `demand_cv`, `[Demand Score]`, `[Constraint Score]`, `[Final Score]`, `delivery_zone`을 추가합니다.
8. **도구 설명**을 아래처럼 편집합니다.

```html
<b><ADM_NM> (<GU_NM>)</b>
B2B: <demand_b2b>  B2C: <demand_b2c>
CV: <demand_cv>
Demand: <ATTR(Demand Score)>
Constraint: <ATTR(Constraint Score)>
Final: <b><ATTR(Final Score)></b>
Zone: <delivery_zone>
```

9. **맵 > 배경 맵 > 어둡게(Dark)**를 선택합니다.
10. **맵 > 맵 레이어 > 워시아웃(Washout): 80%**로 설정합니다.

### Sheet 2: "Map - Hubs" (`scenario_hubs` 데이터 원본)

1. `lon`을 **열**로, `lat`을 **행**으로 드래그합니다. 둘 다 AVG, 연속형으로 둡니다.
2. `lot_id`를 **마크 카드 > 세부 정보**로 드래그합니다.
3. **마크 유형**을 **원(Circle)**으로 설정합니다.
4. `delivery_zone`을 **마크 카드 > 색상**으로 드래그합니다.
   - 색상 배정: Blue `#2196F3`, Purple `#9C27B0`, Grey `#78909C`
5. `rank`를 **마크 카드 > 레이블**로 드래그합니다.
6. **마크 카드 > 크기**를 크게 고정합니다.
7. `[Is Active Scenario]`를 **필터**로 드래그하고 True만 선택합니다.
8. **마크 카드 > 도구 설명**에 `lot_name`, `gu`, `dong`, `cover_n`, `cover_ds`, `delivery_zone`을 추가합니다.
9. **맵 > 배경 맵 > 어둡게(Dark)**, **워시아웃(Washout): 80%**를 적용합니다.

### Sheet 3: "Map - Routes" (`scenario_routes` 데이터 원본)

1. `route_lon`을 **열**로, `route_lat`을 **행**으로 드래그합니다. 둘 다 AVG, 연속형으로 둡니다.
2. `route_id`를 **마크 카드 > 세부 정보**로 드래그합니다.
3. **마크 유형**을 **라인(Line)**으로 설정합니다.
4. `path_order`를 **마크 카드 > 경로**로 드래그합니다. 차원으로 사용합니다.
5. `approval`을 **마크 카드 > 색상**으로 드래그합니다.
   - True: Orange `#FFB74D`, False: Green `#53D769`
6. `[Is Active Scenario]`를 **필터**로 드래그하고 True만 선택합니다.
7. 투명도(opacity)를 약 55%로 설정합니다.
8. **맵 > 배경 맵 > 어둡게(Dark)**, **워시아웃(Washout): 80%**를 적용합니다.

### Sheet 4: "Hub Roster" (`scenario_hubs` 데이터 원본)

1. `lot_name`을 **행**으로, `cover_ds`의 SUM을 **열**로 드래그합니다.
2. `lot_name`을 `rank` 오름차순으로 정렬합니다.
3. `delivery_zone`을 **마크 카드 > 색상**으로 드래그합니다. Sheet 2와 같은 색상 배정을 사용합니다.
4. `rank`, `dong`, `cover_n`을 **마크 카드 > 레이블**로 드래그합니다.
5. `[Is Active Scenario]`를 **필터**로 드래그하고 True만 선택합니다.

### Sheets 5-11: KPI 카드 (총 7개 시트)

각 KPI마다 **마크 유형**을 **텍스트(Text)**로 설정하고, 큰 숫자 하나만 표시하는 시트를 만듭니다.

| Sheet | 데이터 원본 | 측정값 | 필터 |
|-------|-------------|--------|------|
| KPI: Hubs | scenario_hubs | `COUNTD([lot_id])` | [Is Active Scenario]=True |
| KPI: Routes | scenario_routes | `COUNTD([route_id])` | [Is Active Scenario]=True |
| KPI: Time Saving | scenario_routes | `MEDIAN([time_saving])` | [Is Active Scenario]=True, path_order=1 |
| KPI: CO2 | scenario_routes | `SUM([co2_saving])/1000000` | [Is Active Scenario]=True, path_order=1 |
| KPI: Weather | grid_master | `AVG([score_weather])*100` | 없음 |
| KPI: Drone Faster | scenario_routes | 아래 계산 필드 사용 | [Is Active Scenario]=True, path_order=1 |
| KPI: ESG | charts_bundle | `AVG([value1])` | chart_id = "esg" |

**KPI: Drone Faster 계산 필드** (`scenario_routes`에서 생성):

```tableau
SUM(IIF([time_saving] > 0, 1, 0)) / COUNTD([route_id]) * 100
```

**Route KPI 주의사항:** 각 route가 2행으로 구성되어 있으므로 `path_order = 1` 필터를 적용해야 중복 집계를 피할 수 있습니다.

KPI 서식:
- Text size: 22-28pt, Bold, Color: `#4FC3F7`
- 단위는 별도 subtitle text object로 추가
- headers, axes, gridlines 모두 제거

### Sheets 12-19: 차트 (총 8개, 모두 `charts_bundle` 사용)

각 차트는 먼저 `chart_id` 필터를 해당 값으로 설정합니다.

| # | 시트 이름 | chart_id | 차트 유형 | 행/열 | 색상 |
|---|------------|----------|-----------|--------------|-------|
| 12 | Dong Top 15 | dong_top15 | 가로 막대 | 행: `label` (`rank` 기준 정렬), 열: `value1` | `GU_NM` 또는 fixed `#4FC3F7` |
| 13 | Hourly Pattern | hourly | 세로 막대 | 열: `label`, 행: `value1` | `category` (period) |
| 14 | Mode Compare | mode_compare | 그룹 막대 | 열: `label`, 행: `value1` + `value2` | 측정값 이름(Measure Names) |
| 15 | ESG Index | esg | 가로 막대 | 행: `label` (`rank` 기준 정렬), 열: `value1` | Fixed `#53D769` |
| 16 | Drone Zone % | dong_zone_pct | 가로 막대 | 행: `label` (`rank` 기준 정렬), 열: `value1` | Fixed `#53D769` |
| 17 | B2B Top 15 | b2b | 가로 막대 | 행: `label` (`rank` 기준 정렬), 열: `value1` | `GU_NM` 또는 fixed `#FF6B35` |
| 18 | B2C Top 15 | b2c | 가로 막대 | 행: `label` (`rank` 기준 정렬), 열: `value1` | `GU_NM` 또는 fixed `#A855F7` |
| 19 | Robot Top 15 | robot | 가로 막대 | 행: `label` (`rank` 기준 정렬), 열: `value1` | `GU_NM` 또는 fixed `#42A5F5` |

**Mode Compare 별도 설정:**

1. `value1`을 **열**로 드래그합니다. 이름은 "Drone"으로 바꿉니다.
2. `value2`를 **열**로 드래그합니다. 이름은 "Motorcycle"로 바꿉니다.
3. 두 pill을 선택한 뒤 우클릭하고 **이중 축(Dual Axis) > 축 동기화(Synchronize Axis)**를 적용합니다.
4. 또는 **측정값 이름/측정값(Measure Names/Measure Values)**을 사용하고 value1, value2만 필터링합니다.

---

## Phase 5: Dashboard 1 - "Map & Controls" 조립 (1600 x 900)

1. **새 대시보드(New Dashboard)**를 만들고 **크기(Size)**를 **고정(Fixed)** 1600 x 900으로 설정합니다.
2. **Layout:**

```text
+-------------------------------------------------------------------+
| Text: "Seongnam Drone/Robot Hub Analysis" (hero banner)   [60px]  |
+-------------------------------------------------------------------+
| KPI1 | KPI2 | KPI3 | KPI4 | KPI5 | KPI6 | KPI7         [80px]   |
+----------+--------------------------------------------------------+
| Sidebar  | Map - H3 Grid (tiled, fills remaining space)           |
| (300px)  |                                                        |
|          |                                                        |
+----------+--------------------------------------------------------+
```

3. **Sidebar 구성** (세로 layout container, 너비 300px):
   - Text object: "Demand Layers"
   - 매개 변수 표시: `p_demand_b2b`, `p_demand_b2c`, `p_demand_cv`
   - Text object: "Constraint Layers"
   - 매개 변수 표시: `p_con_airspace`, `p_con_obstacle`, `p_con_noise`, `p_con_robot`, `p_con_weather`
   - 매개 변수 표시: `p_airspace_mode`
   - Text object: "Final Score = Demand x Constraint"
   - Hub Roster sheet (Sheet 4)

4. **Map overlay** (고급 사용자용, 선택 사항):
   - "Map - Hubs"를 H3 grid map 위에 floating으로 배치합니다.
   - "Map - Routes"를 H3 grid map 위에 floating으로 배치합니다.
   - 두 floating sheet의 배경을 투명하게 설정합니다.
   - H3 grid map과 위치와 크기를 정확히 맞춥니다.
   - 대안: overlay를 생략하고 Hub Roster + KPI만 사용해도 됩니다.

5. **매개 변수 컨트롤 표시:** 각 parameter를 우클릭하고 **매개 변수 컨트롤 표시(Show Parameter Control)**를 선택합니다.

---

## Phase 6: Dashboard 2 - "Charts" 조립 (1600 x 1200)

1. **새 대시보드(New Dashboard)**를 만들고 **크기(Size)**를 **고정(Fixed)** 1600 x 1200으로 설정합니다.
2. **Layout** (3행 x 3열):

```text
+---------------------+---------------------+---------------------+
| Dong Top 15         | Hourly Pattern      | Mode Compare        |
| (Sheet 12)          | (Sheet 13)          | (Sheet 14)          |
+---------------------+---------------------+---------------------+
| ESG Index           | Drone Zone %        | B2B Top 15          |
| (Sheet 15)          | (Sheet 16)          | (Sheet 17)          |
+---------------------+---------------------+---------------------+
| B2C Top 15          | Robot Top 15        | (empty or text)     |
| (Sheet 18)          | (Sheet 19)          |                     |
+---------------------+---------------------+---------------------+
```

---

## Phase 7: 다크 테마 적용

### Dashboard Background
- **대시보드 > 서식 > 음영**: `#0F0F1A`

### 각 Sheet Container
- Container 선택 > **레이아웃 패널 > 배경**: `#16213E`
- **테두리**: `#0F3460` 1px

### Sheet Formatting (모든 시트에 적용)

1. **서식 > 음영 > 워크시트**: `#16213E`, **패널**: `#1A1A2E`
2. **서식 > 글꼴 > 모두**: `Noto Sans KR`, Color: `#E0E0E0`
3. **서식 > 라인 > 격자선**: `#1A3A5C`
4. **서식 > 테두리 > 행/열 구분선**: None 또는 `#1A3A5C`

### KPI Cards
- Value font: 26pt Bold, Color: `#4FC3F7`
- Label font: 11pt, Color: `#AABBCC`

### Map Settings
- **배경 맵**: 어둡게(Dark)
- **맵 레이어 > 워시아웃(Washout)**: 80%

---

## Phase 8: 검증

### Data Check
- [ ] H3 grid가 지도에 약 1,947개 circle로 표시됩니다.
- [ ] 모든 circle이 red-yellow-green gradient로 색칠됩니다.
- [ ] 기본 시나리오(S001)가 6개 hubs와 353개 routes를 표시합니다.

### Toggle Tests

1. **Demand toggles:**
   - [ ] demand toggle 3개를 모두 OFF로 바꾸면 모든 cell이 더 초록색에 가까워집니다. demand=1.0이고 constraint만 반영됩니다.
   - [ ] B2B만 ON으로 두면 B2B score가 낮은 cell이 빨간색으로 바뀝니다.

2. **Constraint toggles:**
   - [ ] constraint toggle 5개를 모두 OFF로 바꾸면 cell 색상이 demand score만 기준으로 표시됩니다.
   - [ ] airspace만 ON으로 두면 많은 cell이 빨간색으로 바뀝니다.

3. **Airspace mode:**
   - [ ] "strict"로 전환하면 hard_exclusion cell이 회색 또는 낮은 점수로 표시됩니다.

### Scenario Tests
- [ ] All ON + approval = S001 (6 hubs, 353 routes)
- [ ] All ON + strict = S002
- [ ] All OFF + approval = S063
- [ ] Weather OFF only + approval = S003

### Visual Match
- [ ] 지도 색상이 HTML dashboard와 대략 일치합니다.
- [ ] hub marker가 delivery_zone에 따라 blue/purple/grey로 표시됩니다.
- [ ] KPI 숫자가 HTML dashboard 기본값과 일치합니다.

---

## Scenario ID Reference

아래 bit-pattern 수식이 parameter 상태를 scenario ID로 매핑합니다.

```text
S + zero_pad_3(
  (NOT weather)*1 + (NOT robot)*2 + (NOT noise)*4 + (NOT obstacle)*8 + (NOT airspace)*16
  ) * 2
  + (strict ? 1 : 0)
  + 1
)
```

예시:

| Parameters | Scenario |
|------------|----------|
| All ON, approval | S001 |
| All ON, strict | S002 |
| Weather OFF, rest ON, approval | S003 |
| Robot OFF, rest ON, approval | S005 |
| All OFF, approval | S063 |
| All OFF, strict | S064 |

---

## File Summary

| File | Rows | Size | Used By |
|------|------|------|---------|
| grid_master.csv | 1,947 | 490 KB | Map, KPI: Weather |
| scenario_hubs.csv | 384 | 65 KB | Hub markers, Hub roster, KPI: Hubs |
| scenario_routes.csv | 37,436 | 3,045 KB | Route lines, KPI: Routes/Time/CO2/Drone% |
| scenario_lookup.csv | 64 | 3 KB | Reference only |
| charts_bundle.csv | 162 | 8 KB | All 8 chart sheets, KPI: ESG |
