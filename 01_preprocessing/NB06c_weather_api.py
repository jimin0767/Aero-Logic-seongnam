"""
NB06c_weather_api.py
======================
기상청 API 연동 — 드론 Go/No-Go 실시간 판단

API 엔드포인트:
  [A] 지상관측 단시간: kma_sfctm2.php  (WS 풍속, RN 강수, VIS 시정)
  [B] 지상관측 기간:   kma_sfctm3.php  (과거 데이터 수집)
  [C] 초단기실황:      getUltraSrtNcst  (NX=62,NY=123 성남 분당구)

드론 Go/No-Go 기준:
  풍속(WSD) >= 10 m/s  → NO-GO
  강수량(RN1) >= 5 mm/h → NO-GO
  강수형태(PTY) != 0   → NO-GO (비/눈/진눈깨비)

성남시 관측소: 수원(119) 또는 광주(212) — 성남 직접 관측소 없음
초단기실황 격자: 분당구 NX=62, NY=123

산출물:
  processed/weather_current.json    — 현재 Go/No-Go 상태
  processed/weather_history.csv     — 과거 관측 (Monte Carlo 파라미터 검증용)
"""

import requests
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

BASE = Path(r"C:\Users\pasoh\OneDrive\문서\GitHub\Aero-Logic-seongnam")
OUT  = BASE / "processed"

# ══════════════════════════════════════════════
AUTH_KEY = "8FPiv31cRI6T4r99XOSOCA"
# ══════════════════════════════════════════════

# 드론 Go/No-Go 임계값
THRESHOLD = {
    "wind_ms"    : 10.0,   # 풍속 (m/s)
    "rain_mmh"   : 5.0,    # 강수량 (mm/h)
    "pty_nogo"   : [1, 2, 3, 4, 5, 6, 7],  # 강수형태 (0=없음만 OK)
}

print("=" * 60)
print("NB06c — 기상청 API 드론 Go/No-Go 판단")
print("=" * 60)

# ── [C] 초단기실황 (성남 분당구 NX=62, NY=123) ───────────────
print("\n[C] 초단기실황 조회...")

now = datetime.now()
# 초단기실황은 정시 기준 (분을 0으로)
base_date = now.strftime("%Y%m%d")
# 가장 최근 정시 (초단기실황은 매시 30분 이후부터 조회 가능)
base_hour = now.hour if now.minute >= 30 else now.hour - 1
if base_hour < 0:
    base_hour = 23
    base_date = (now - timedelta(days=1)).strftime("%Y%m%d")
base_time = f"{base_hour:02d}00"

url_c = (
    f"https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/"
    f"getUltraSrtNcst?pageNo=1&numOfRows=1000&dataType=JSON"
    f"&base_date={base_date}&base_time={base_time}"
    f"&nx=62&ny=123&authKey={AUTH_KEY}"
)

try:
    r = requests.get(url_c, timeout=15)
    data = r.json()

    items = data["response"]["body"]["items"]["item"]
    obs = {it["category"]: it["obsrValue"] for it in items}

    # 주요 변수 추출
    wind_speed  = float(obs.get("WSD", 0))   # 풍속 m/s
    rain_1h     = float(obs.get("RN1", 0))   # 1시간 강수량
    pty         = int(float(obs.get("PTY", 0)))  # 강수형태
    temp        = float(obs.get("T1H", 0))   # 기온
    humidity    = float(obs.get("REH", 0))   # 습도
    # 동서바람(UUU), 남북바람(VVV) → 합성 풍속
    uuu = float(obs.get("UUU", 0))
    vvv = float(obs.get("VVV", 0))
    wind_calc = round(np.sqrt(uuu**2 + vvv**2), 2)

    print(f"  관측시각: {base_date} {base_time}")
    print(f"  풍속(WSD):   {wind_speed:.1f} m/s  (기준: {THRESHOLD['wind_ms']}↑ NO-GO)")
    print(f"  합성풍속:    {wind_calc:.1f} m/s")
    print(f"  강수량(RN1): {rain_1h:.1f} mm/h  (기준: {THRESHOLD['rain_mmh']}↑ NO-GO)")
    print(f"  강수형태:    {pty} {'(비/눈)' if pty > 0 else '(없음)'}")
    print(f"  기온:        {temp:.1f}°C")
    print(f"  습도:        {humidity:.0f}%")

    # Go/No-Go 판단
    reasons = []
    if wind_speed >= THRESHOLD["wind_ms"]:
        reasons.append(f"강풍({wind_speed}m/s)")
    if rain_1h >= THRESHOLD["rain_mmh"]:
        reasons.append(f"강우({rain_1h}mm/h)")
    if pty in THRESHOLD["pty_nogo"]:
        pty_labels = {1:"비",2:"비/눈",3:"눈",4:"소나기",5:"빗방울",6:"빗방울/눈날림",7:"눈날림"}
        reasons.append(f"강수형태({pty_labels.get(pty,'기타')})")

    go_nogo = "NO-GO" if reasons else "GO"
    print(f"\n  ▶ 드론 운항 판단: [{go_nogo}]")
    if reasons:
        print(f"    사유: {', '.join(reasons)}")
        print(f"    → 로봇 Fallback 배송 전환")

    # 현재 상태 저장
    weather_now = {
        "timestamp"  : datetime.now().isoformat(),
        "base_date"  : base_date,
        "base_time"  : base_time,
        "nx"         : 62,
        "ny"         : 123,
        "location"   : "성남시 분당구",
        "wind_speed" : wind_speed,
        "wind_calc"  : wind_calc,
        "rain_1h"    : rain_1h,
        "pty"        : pty,
        "temperature": temp,
        "humidity"   : humidity,
        "go_nogo"    : go_nogo,
        "reasons"    : reasons,
        "raw_obs"    : obs,
    }

    (OUT / "weather_current.json").write_text(
        json.dumps(weather_now, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n  ✅ weather_current.json 저장")

except Exception as e:
    print(f"  ❌ 초단기실황 오류: {e}")
    weather_now = {"go_nogo": "GO", "error": str(e)}

# ── [B] 지상관측 기간 — 과거 30일 성남 근처 관측소 ────────────
print("\n[B] 지상관측 기간 조회 (수원 STN=119, 과거 30일)...")

# 과거 30일 시간별 관측
tm1 = (now - timedelta(days=30)).strftime("%Y%m%d%H%M")
tm2 = now.strftime("%Y%m%d%H%M")

url_b = (
    f"https://apihub.kma.go.kr/api/typ01/url/kma_sfctm3.php"
    f"?tm1={tm1}&tm2={tm2}&stn=119&authKey={AUTH_KEY}"
)

try:
    r = requests.get(url_b, timeout=30)
    lines = [l for l in r.text.split("\n")
             if l and not l.startswith("#") and len(l) > 20]

    if lines:
        # 파싱: TM, STN, WD, WS, GST_WD, GST_WS, ..., RN(강수), VIS(시정)
        records = []
        for line in lines[:720]:  # 최대 30일×24h
            parts = line.split()
            if len(parts) < 10:
                continue
            try:
                records.append({
                    "tm"    : parts[0],
                    "stn"   : parts[1],
                    "wd"    : float(parts[2]) if parts[2] != "-" else np.nan,
                    "ws"    : float(parts[3]) if parts[3] != "-" else np.nan,
                    "ta"    : float(parts[11]) if len(parts) > 11 and parts[11] != "-" else np.nan,
                    "rn"    : float(parts[17]) if len(parts) > 17 and parts[17] not in ["-","0.0"] else 0.0,
                })
            except:
                continue

        hist_df = pd.DataFrame(records)
        if not hist_df.empty:
            hist_df.to_csv(OUT / "weather_history.csv", index=False, encoding="utf-8-sig")

            # Monte Carlo 파라미터 재계산
            n_total = len(hist_df)
            n_wind  = (hist_df["ws"] >= THRESHOLD["wind_ms"]).sum()
            n_rain  = (hist_df["rn"] >= THRESHOLD["rain_mmh"]).sum()
            p_wind  = n_wind / n_total
            p_rain  = n_rain / n_total
            p_drone = (1 - p_wind) * (1 - p_rain) * 0.97  # 시정 97%

            print(f"  관측 시간: {n_total}시간분")
            print(f"  강풍 실패 확률: {p_wind*100:.1f}% (기존 NB13b: 17.8%)")
            print(f"  강우 실패 확률: {p_rain*100:.1f}% (기존 NB13b: 2.1%)")
            print(f"  실측 기반 드론 가용률: {p_drone*100:.1f}%")

            # weather_sim_summary.json 업데이트
            ws_path = OUT / "weather_sim_summary.json"
            if ws_path.exists():
                ws = json.loads(ws_path.read_text(encoding="utf-8"))
                ws["P_drone_available_observed"] = round(p_drone, 4)
                ws["P_wind_fail_observed"]       = round(p_wind, 4)
                ws["P_rain_fail_observed"]       = round(p_rain, 4)
                ws["obs_station"]                = "수원(119)"
                ws["obs_period_days"]            = 30
                ws_path.write_text(
                    json.dumps(ws, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(f"  ✅ weather_sim_summary.json 업데이트 (실측 파라미터)")

            print(f"  ✅ weather_history.csv 저장 ({n_total}행)")
        else:
            print("  ⚠ 파싱 가능한 데이터 없음")
    else:
        print("  ⚠ 응답 데이터 없음")

except Exception as e:
    print(f"  ❌ 기간 조회 오류: {e}")

# ── esg.js / weather_current.js 업데이트 ─────────────────────
print("\n[D] 대시보드용 weather_current.js 생성...")
wc_js = f"""// Auto-generated by NB06c_weather_api.py — {datetime.now().strftime('%Y-%m-%d %H:%M')}
// 기상청 초단기실황 (NX=62, NY=123 성남 분당구)
const WEATHER_NOW = {json.dumps(weather_now, ensure_ascii=False, indent=2)};
"""
(BASE / "assets" / "js" / "weather_current.js").write_text(wc_js, encoding="utf-8")
print(f"  ✅ weather_current.js 저장")

print(f"\n✅ NB06c 완료!")
print(f"   현재 드론 상태: [{weather_now.get('go_nogo', 'UNKNOWN')}]")
print(f"   weather_current.json + weather_history.csv + weather_current.js")
