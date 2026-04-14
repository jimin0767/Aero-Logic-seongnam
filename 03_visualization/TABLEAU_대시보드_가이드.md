# Tableau Cloud 대시보드 구축 가이드

## 접속 URL
https://prod-kr-a.online.tableau.com/#/site/jimin076721-be93e49158/explore

## 프로젝트: 성남시_드론배송_거점최적화
- 12개 데이터소스 게시 완료
- 기본 통합 문서 게시 완료 (Grid Scores 연결, 지도 시트)

---

## Sheet 1: 거점 적합도 지도 (Hero Viz)

### 이미 설정됨:
- Grid Scores 데이터소스 연결
- lon → 열, h3_index + lat → 행 (1,947개 마크 지도)

### 추가 작업:
1. **composite_score → 색상 마크에 추가**
   - 데이터 패널에서 `composite_score` 을 **색상** 마크 카드에 드래그
   - 색상 편집: 빨강-노랑-초록 (역전 체크하여 높은 값=초록)

2. **ADM_NM → 세부 정보 마크에 추가** (도구 설명에 동 이름 표시)

3. **마크 유형**: 자동 → **원** 으로 변경, 크기 조절

---

## Sheet 2: 동별 종합점수 막대차트

1. 새 워크시트 만들기
2. **ADM_NM** → 행
3. **composite_score** (평균) → 열
4. **내림차순 정렬**
5. **GU_NM** → 색상 (구별 색상 구분)

---

## Sheet 3: 배송모드 비교 레이더차트

1. 새 데이터 원본 추가: **Mode Radar Scores**
2. 새 워크시트 만들기
3. **metric** → 열
4. **motorcycle, drone_robot** → 행 (이중 축)
5. 마크 유형: 다각형 또는 라인
6. 또는: 막대차트로 motorcycle vs drone_robot 비교

---

## Sheet 4: 시간대별 배송수요

1. 새 데이터 원본 추가: **Hourly Demand**
2. 새 워크시트 만들기
3. **hour** → 열 (연속형)
4. **total_del_cnt** (합계) → 행
5. 마크 유형: 영역 또는 라인
6. 12시, 18시 피크 강조

---

## Sheet 5: 허브 상세 정보

1. 새 데이터 원본 추가: **Final Hubs**
2. 새 워크시트 만들기
3. **name** → 행
4. **hub_score, coverage_count, hotspot_count** → 열 (텍스트 테이블)
5. **delivery_mode** → 색상

---

## 대시보드 조합

1. **새 대시보드** 클릭
2. 크기: 자동 또는 1920 x 1080
3. Sheet 1 (지도) → 상단 대부분 차지
4. Sheet 2-5 → 하단 또는 우측 배치
5. 제목 추가: "성남시 드론·로봇 배송 거점 최적화 의사결정 지원 시스템"

---

## 파라미터 토글 (고급)

### 5개 Boolean 파라미터 생성:
- P_Airspace (기본값: True)
- P_Obstacle (기본값: True)
- P_Noise (기본값: True)
- P_Terrain (기본값: True)
- P_Weather (기본값: True)

### 계산된 필드 생성:
```
[Dynamic Composite] = 
  (IF [P_Airspace] THEN [score_airspace] ELSE 1 END)
* (IF [P_Obstacle] THEN [score_obstacle] ELSE 1 END)
* (IF [P_Noise]    THEN [score_noise]    ELSE 1 END)
* (IF [P_Terrain]  THEN [score_terrain]  ELSE 1 END)
* (IF [P_Weather]  THEN [score_weather]  ELSE 1 END)
```

### 대시보드에 파라미터 컨트롤 표시:
- 대시보드 → 파라미터 컨트롤 표시 (5개 체크박스)
- Sheet 1의 색상을 `[Dynamic Composite]` 으로 교체
- 사용자가 체크박스 토글 시 실시간 재계산

---

## 데이터소스 목록 (게시 완료)

| 이름 | 행수 | 용도 |
|------|------|------|
| Grid Scores | 1,947 | 주 분석 데이터 (H3 그리드) |
| Grid Hexagons | 1,947 | 공간 데이터 (WKT) |
| Final Hubs | 4 | 선정 허브 |
| Hub Locations | 4 | 허브 GeoJSON |
| Dong Summary | 50 | 동별 요약 |
| Hourly Demand | 500 | 시간대별 수요 |
| Drone Routes | 20 | 경로 GeoJSON |
| Delivery Routes Summary | 20 | 경로 요약 |
| Service Areas | 4 | 서비스권역 |
| Mode Comparison | 9 | 배송모드 비교 |
| Mode Radar Scores | 6 | 레이더차트 |
| Public Facilities | 172 | 공공시설 |
