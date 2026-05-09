# dashboard.html Tableau 구현 가이드

이 폴더의 CSV들은 `03_visualization/dashboard.html`을 Tableau Desktop/Cloud에서 재구현하기 위한 전용 데이터 묶음입니다.

## 1. 연결할 데이터

우선 Tableau에서 `processed/tableau/dashboard` 폴더의 CSV를 각각 Text File로 연결하세요.

핵심 데이터는 다음 순서로 쓰면 됩니다.

| 우선순위 | CSV | 용도 |
|---:|---|---|
| 1 | `T01_grid_cells.csv` | H3 셀 지도, KPI, 동별 집계의 중심 데이터 |
| 2 | `T02_dong_summary.csv` | 동별 Top 15, 적합 셀 비율 |
| 3 | `T06_hubs.csv` | 기본 선정 거점 4개 |
| 4 | `T07_vertiports_dashboard.csv` | HTML에 실제 표시되는 버티포트 후보 570개 |
| 5 | `T07_vertiport_candidates_full.csv` | 원본 전체 버티포트 후보 분석용 |
| 6 | `T13_layer_scenario_summary.csv` / `T14_layer_scenario_hubs.csv` | HTML의 레이어/수요 조합별 거점 재선정 결과 |
| 7 | `T03_hourly_demand.csv`, `T04_mode_comparison_long.csv`, `T05_mode_radar_long.csv`, `T08_demand_indices_long.csv`, `T09_esg_scenarios.csv`, `T10_weather.csv`, `T11_welfare_by_dong.csv` | 하단 차트 |

지도는 간단히 구현하려면 `T01_grid_cells.csv`의 `lat`, `lon`을 쓰세요. 진짜 H3 육각형 폴리곤이 필요하면 기존 `03_visualization/tableau_data/grid_hexagons.geojson`을 Spatial File로 추가하고 `h3_index`로 연결하세요.

## 2. 관계 설정

추천 관계는 다음과 같습니다.

| 기준 데이터 | 연결 데이터 | 키 |
|---|---|---|
| `T01_grid_cells` | `T02_dong_summary` | `dong`, `gu` |
| `T01_grid_cells` | `T08_demand_indices_wide` | `dong`, `gu` |
| `T13_layer_scenario_summary` | `T14_layer_scenario_hubs` | `scenario_key` |
| `T15_layer_scenario_cell_scores` | `T01_grid_cells` | `h3_index` |

대시보드가 복잡해지면 모든 파일을 한 데이터 모델에 억지로 묶지 말고, 시트별 데이터소스로 분리하는 편이 안정적입니다.

## 3. 파라미터

HTML의 체크박스를 Tableau Boolean 파라미터로 만듭니다.

| 파라미터 | 기본값 |
|---|---|
| `p_airspace` | True |
| `p_obstacle` | True |
| `p_noise` | True |
| `p_robot` | True |
| `p_weather` | True |
| `p_b2b` | False |
| `p_b2c` | False |
| `p_ddi` | False |

## 4. 계산 필드

### 선택 레이어 점수

```tableau
IF NOT [p_airspace]
AND NOT [p_obstacle]
AND NOT [p_noise]
AND NOT [p_robot]
AND NOT [p_weather]
THEN 0
ELSE
    (IF [p_airspace] THEN [score_airspace] ELSE 1 END)
  * (IF [p_obstacle] THEN [score_obstacle] ELSE 1 END)
  * (IF [p_noise] THEN [score_noise] ELSE 1 END)
  * (IF [p_robot] THEN [score_robot_access_ra] ELSE 1 END)
  * (IF [p_weather] THEN [score_weather] ELSE 1 END)
END
```

### 적합 셀 여부

```tableau
[선택 레이어 점수] > 0
```

### 적합 셀 수

```tableau
COUNTD(IF [적합 셀 여부] THEN [h3_index] END)
```

### 적합 셀 비율

```tableau
COUNTD(IF [적합 셀 여부] THEN [h3_index] END) / COUNTD([h3_index])
```

### 평균 종합 적합도

```tableau
AVG([선택 레이어 점수])
```

### 수요 점수

```tableau
IF
    (IF [p_b2b] THEN 1 ELSE 0 END)
  + (IF [p_b2c] THEN 1 ELSE 0 END)
  + (IF [p_ddi] THEN 1 ELSE 0 END) = 0
THEN 0
ELSE
(
    (IF [p_b2b] THEN ZN([b2b_index_100]) / 100 ELSE 0 END)
  + (IF [p_b2c] THEN ZN([b2c_index_100]) / 100 ELSE 0 END)
  + (IF [p_ddi] THEN ZN([delivery_demand_index]) ELSE 0 END)
)
/
(
    (IF [p_b2b] THEN 1 ELSE 0 END)
  + (IF [p_b2c] THEN 1 ELSE 0 END)
  + (IF [p_ddi] THEN 1 ELSE 0 END)
)
END
```

### 시나리오 키

`T13/T14/T15` 사전 계산 테이블을 필터링할 때 씁니다.

```tableau
"A" + (IF [p_airspace] THEN "1" ELSE "0" END)
+ "O" + (IF [p_obstacle] THEN "1" ELSE "0" END)
+ "N" + (IF [p_noise] THEN "1" ELSE "0" END)
+ "R" + (IF [p_robot] THEN "1" ELSE "0" END)
+ "W" + (IF [p_weather] THEN "1" ELSE "0" END)
+ "__B" + (IF [p_b2b] THEN "1" ELSE "0" END)
+ "C" + (IF [p_b2c] THEN "1" ELSE "0" END)
+ "D" + (IF [p_ddi] THEN "1" ELSE "0" END)
```

## 5. 시트 구성

| 시트명 | 데이터 | 배치 |
|---|---|---|
| KPI 전체 셀 | `T01_grid_cells` | `COUNTD(h3_index)` 텍스트 |
| KPI 적합 셀 | `T01_grid_cells` | 위 계산 필드 사용 |
| KPI 선정 거점 | `T13_layer_scenario_summary` | `selected_hubs`, `scenario_key` 필터 |
| KPI 커버리지 | `T13_layer_scenario_summary` | `coverage_pct`, `scenario_key` 필터 |
| H3 적합도 지도 | `T01_grid_cells` | Columns=`lon`, Rows=`lat`, Color=`선택 레이어 점수`, Detail=`h3_index` |
| 시나리오별 H3 지도 | `T15_layer_scenario_cell_scores` | `layer_key` 필터, Color=`selected_layer_score` |
| 거점 지도 | `T14_layer_scenario_hubs` | `scenario_key` 필터, Columns=`lon`, Rows=`lat`, Label=`hub_rank`, Tooltip=`hub_name` |
| 기본 거점 지도 | `T06_hubs` | 기본 발표용 4개 거점 |
| 버티포트 후보 | `T07_vertiports_dashboard` | Color=`zone`, Size=`score` |
| 전체 버티포트 후보 분석 | `T07_vertiport_candidates_full` | Color=`zone`, Size=`vertiport_score` |
| 동별 종합 적합도 Top 15 | `T02_dong_summary` | Rows=`dong`, Columns=`avg_selected_score_all_layers`, Top N=15 |
| 동별 적합 셀 비율 | `T02_dong_summary` | Rows=`dong`, Columns=`feasible_pct_all_layers` |
| 시간대별 배송 수요 | `T03_hourly_demand` | Columns=`hour_label`, Rows=`avg_hour_ratio`, Line |
| 배송 수단 비교표 | `T04_mode_comparison_long` | Rows=`indicator`, Columns=`mode`, Text=`value_display` |
| 모드 비교 점수 | `T05_mode_radar_long` | Rows=`metric`, Columns=`score`, Color=`mode` |
| ESG 효율 | `T09_esg_scenarios` | Columns=`시나리오`, Rows=`E_지수`, Reference Line=1.0 |
| 수요 지수 Top 15 | `T08_demand_indices_long` | Filter=`metric`, Rows=`dong`, Columns=`index_value` |
| 기상 GO/NOGO | `T10_weather` | Filter=`data_type`, Line/Bar |
| 복지시설 밀도 | `T11_welfare_by_dong` | Rows=`dong`, Columns=`welfare_density` |

## 6. 구현상 주의

HTML은 브라우저 JavaScript로 greedy set-cover 알고리즘을 즉시 재계산합니다. Tableau 계산 필드만으로 같은 알고리즘을 매번 실행하기는 어렵기 때문에, 이 묶음에는 `T13_layer_scenario_summary.csv`와 `T14_layer_scenario_hubs.csv`로 256개 조합을 사전 계산해 두었습니다.

발표용 최단 경로는 다음입니다.

1. 지도/차트는 `T01`부터 `T11`까지로 구현
2. 레이어 토글에 따른 점수 변화는 계산 필드로 구현
3. 거점 재선정은 `T13/T14`를 `scenario_key`로 필터링
