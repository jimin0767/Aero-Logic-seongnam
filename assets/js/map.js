function scoreToColor(v) {
  if (v <= 0) return '#e94560';
  if (v < 0.2) return '#ff5722';
  if (v < 0.4) return '#ff9800';
  if (v < 0.6) return '#ffeb3b';
  if (v < 0.75) return '#8bc34a';
  if (v < 0.9) return '#4caf50';
  return '#00c853';
}

function recalcScore(cell, active) {
  let v = 1.0;
  let n = 0;
  if (active.sa) { v *= cell.sa; n++; }
  if (active.so) { v *= cell.so; n++; }
  if (active.sn) { v *= cell.sn; n++; }
  if (active.st) { v *= cell.st; n++; }
  if (active.sw) { v *= cell.sw; n++; }
  return n === 0 ? 0 : v;
}

function getPriorityScore(cell, suitability) {
  return suitability * demandValueForCell(cell);
}

function getActiveLayers() {
  const a = {};
  document.querySelectorAll('.layer-toggle input').forEach(inp => {
    a[inp.dataset.layer] = inp.checked;
  });
  return a;
}

function getActivePoiLayers() {
  const active = {};
  document.querySelectorAll('.poi-toggle input').forEach(inp => {
    active[inp.dataset.poi] = inp.checked;
  });
  return active;
}

function haversineM(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const r = Math.PI / 180;
  const f1 = lat1 * r;
  const f2 = lat2 * r;
  const df = (lat2 - lat1) * r;
  const dl = (lon2 - lon1) * r;
  const a = Math.sin(df / 2) ** 2 + Math.cos(f1) * Math.cos(f2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

let hubCandidates = [];
let hubCoverage = [];
let currentTargetCells = new Map();

const POI_WEIGHTS = {
  commercial: 1.0,
  medical: 0.95,
  subway: 0.85,
  school: 0.75,
  park: 0.55,
};

function findNearestGridIndex(lat, lon) {
  let bestIndex = -1;
  let bestDistance = Infinity;
  GRID.forEach((cell, i) => {
    const distance = haversineM(lat, lon, cell.lat, cell.lon);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = i;
    }
  });
  return bestIndex;
}

function addPoiTarget(targets, ci, category, poi) {
  const existing = targets.get(ci);
  const weight = POI_WEIGHTS[category] || 0.5;
  if (existing) {
    existing.poiWeight += weight;
    existing.poiCount += 1;
    existing.poiCategories.add(category);
    if (poi.name) existing.poiNames.add(poi.name);
  } else {
    targets.set(ci, {
      poiWeight: weight,
      poiCount: 1,
      poiCategories: new Set([category]),
      poiNames: new Set(poi.name ? [poi.name] : []),
    });
  }
}

function buildTargetCells(scores, activePoi = {}) {
  const targets = new Map();
  let totalDemand = 0;

  scores.forEach((suitability, i) => {
    if (suitability <= 0) return;

    const demand = demandValueForCell(GRID[i]);
    if (demand >= DEMAND_THR) {
      targets.set(i, {
        poiWeight: 0,
        poiCount: 0,
        poiCategories: new Set(),
        poiNames: new Set(),
      });
      totalDemand += demand;
    }
  });

  Object.entries(activePoi).forEach(([category, isActive]) => {
    if (!isActive) return;

    (poiSource[category] || []).forEach(poi => {
      const ci = findNearestGridIndex(poi.lat, poi.lon);
      if (ci >= 0 && scores[ci] > 0) addPoiTarget(targets, ci, category, poi);
    });
  });

  return { targets, totalDemand };
}

function getTargetWeight(ci, scores) {
  const target = currentTargetCells.get(ci);
  const demand = demandValueForCell(GRID[ci]);
  const poiWeight = target ? target.poiWeight : 0;
  return scores[ci] * (demand + poiWeight);
}

function selectHubs(scores, activePoi = {}, maxHubs = 10, coverageTarget = 0.9) {
  const feasible = new Set();

  scores.forEach((suitability, i) => {
    if (suitability > 0) feasible.add(i);
  });

  const targetResult = buildTargetCells(scores, activePoi);
  currentTargetCells = targetResult.targets;
  const hotspots = new Set(currentTargetCells.keys());
  const totalDemand = targetResult.totalDemand;

  hubCandidates = [...feasible].map(ci => {
    const cell = GRID[ci];
    return {
      cellIndex: ci,
      lat: cell.lat,
      lon: cell.lon,
      name: `${cell.dong} 후보지`,
      facility: 'H3 후보 셀',
      capacity: Math.max(2, Math.round(2 + demandValueForCell(cell) * 8)),
    };
  });
  hubCoverage = hubCandidates.map(candidate =>
    [...hotspots].filter(ci => haversineM(candidate.lat, candidate.lon, GRID[ci].lat, GRID[ci].lon) <= 500)
  );

  if (hotspots.size === 0) {
    return { hubs: [], feasible, hotspots, uncovered: new Set(), totalDemand };
  }

  const uncovered = new Set(hotspots);
  const selected = [];

  for (let k = 0; k < maxHubs && uncovered.size > 0; k++) {
    let bestFac = -1;
    let bestScore = -Infinity;

    for (let f = 0; f < hubCandidates.length; f++) {
      if (selected.includes(f)) continue;

      const coveredNew = hubCoverage[f].filter(ci => uncovered.has(ci));
      if (coveredNew.length === 0) continue;

      const demandWeightedCoverage = coveredNew.reduce((sum, ci) => sum + getTargetWeight(ci, scores), 0);

      if (demandWeightedCoverage > bestScore) {
        bestScore = demandWeightedCoverage;
        bestFac = f;
      }
    }

    if (bestFac < 0) break;
    selected.push(bestFac);
    hubCoverage[bestFac].forEach(ci => uncovered.delete(ci));

    const coveredCount = hotspots.size - uncovered.size;
    if (coveredCount / hotspots.size >= coverageTarget) break;
  }

  return { hubs: selected, feasible, hotspots, uncovered, totalDemand };
}

const map = L.map('map', { preferCanvas: true }).setView([37.39, 127.11], 12.5);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  maxZoom: 19,
  subdomains: 'abcd',
}).addTo(map);
L.control.attribution({ prefix: false }).addAttribution('&copy; <a href="https://carto.com/">CARTO</a>').addTo(map);

const POI_CONFIG = {
  park: { color: '#ce93d8', radius: 5, fillOpacity: 0.80, label: '공원' },
  commercial: { color: '#9c27b0', radius: 6, fillOpacity: 0.85, label: '상권' },
  medical: { color: '#e040fb', radius: 5, fillOpacity: 0.85, label: '의료' },
  subway: { color: '#7c4dff', radius: 6, fillOpacity: 0.90, label: '지하철' },
  school: { color: '#b39ddb', radius: 5, fillOpacity: 0.80, label: '학교' },
};

const poiSource = typeof POI === 'undefined' ? {} : POI;
const poiGroups = {};
Object.entries(POI_CONFIG).forEach(([cat, cfg]) => {
  const group = L.layerGroup();
  (poiSource[cat] || []).forEach(p => {
    const nameLabel = p.name ? `<b>${p.name}</b><br>` : '';
    L.circleMarker([p.lat, p.lon], {
      radius: cfg.radius,
      fillColor: cfg.color,
      color: cfg.color,
      weight: 1.5,
      fillOpacity: cfg.fillOpacity,
      opacity: 0.9,
    }).bindPopup(
      `<div style="font-family:'Noto Sans KR';font-size:12px;">${nameLabel}${cfg.label}</div>`,
      { maxWidth: 180 }
    ).addTo(group);
  });
  poiGroups[cat] = group;
});

document.querySelectorAll('.poi-toggle').forEach(label => {
  label.addEventListener('click', function(e) {
    const inp = this.querySelector('input');
    inp.checked = !inp.checked;
    this.classList.toggle('active', inp.checked);
    const cat = this.dataset.poi;
    if (inp.checked) {
      poiGroups[cat].addTo(map);
    } else {
      poiGroups[cat].remove();
    }
    updateDashboard();
    e.preventDefault();
  });
});

let hexMarkers = [];
function buildHexLayer(scores) {
  hexMarkers.forEach(m => map.removeLayer(m));
  hexMarkers = [];

  let totalSuitability = 0;
  let totalDemand = 0;
  let totalPriority = 0;

  scores.forEach((suitability, i) => {
    const cell = GRID[i];
    const demand = getDemandForCell(cell);
    const demandScore = demand?.demand || 0;
    const priority = getPriorityScore(cell, suitability);

    totalSuitability += suitability;
    totalDemand += demandScore;
    totalPriority += priority;

    const color = scoreToColor(priority);
    const m = L.circleMarker([cell.lat, cell.lon], {
      radius: demandScore >= DEMAND_THR ? 6 : 5,
      fillColor: color,
      fillOpacity: demandScore >= DEMAND_THR ? 0.78 : 0.55,
      color,
      weight: demandScore >= DEMAND_THR ? 0.9 : 0.5,
      opacity: 0.9,
    });
    m.bindPopup(
      `<div style="font-family:'Noto Sans KR',sans-serif;font-size:12px;">` +
      `<b>${cell.dong}</b> (${cell.gu})<br>` +
      `운영 적합도: <b>${suitability.toFixed(3)}</b><br>` +
      `드론 수요지수: <b>${demandScore.toFixed(3)}</b>` +
      `${demand ? ` | 수요 순위: ${demand.rank}위` : ''}<br>` +
      `종합 우선순위: <b style="color:${color}">${priority.toFixed(3)}</b><br>` +
      `공역: ${cell.sa} | 장애물: ${cell.so}<br>` +
      `소음: ${cell.sn} | 지형: ${cell.st} | 기상: ${cell.sw}` +
      `${demand ? `<br>구성: 주거 ${demand.hr} / 유동 ${demand.fp} / 소비 ${demand.cc} / 주문 ${demand.od}` : ''}` +
      `</div>`
    );
    m.addTo(map);
    hexMarkers.push(m);
  });

  document.getElementById('kpi-avg-cs').textContent = (totalPriority / scores.length).toFixed(3);
  const demandKpi = document.getElementById('kpi-avg-demand');
  if (demandKpi) demandKpi.textContent = (totalDemand / scores.length).toFixed(3);
  const suitabilityKpi = document.getElementById('kpi-avg-suitability');
  if (suitabilityKpi) suitabilityKpi.textContent = (totalSuitability / scores.length).toFixed(3);
}

let hubMarkers = [];
let servicePolys = [];
let routeLines = [];

const PALETTE = [
  '#00e5ff',
  '#ff4081',
  '#b2ff59',
  '#ffd740',
  '#ea80fc',
  '#ff6d00',
  '#40c4ff',
  '#f50057',
  '#69ff47',
  '#ffab40',
];

function buildHubLayer(selFacIndices, scores) {
  hubMarkers.forEach(m => map.removeLayer(m));
  servicePolys.forEach(p => map.removeLayer(p));
  routeLines.forEach(l => map.removeLayer(l));
  hubMarkers = [];
  servicePolys = [];
  routeLines = [];

  selFacIndices.forEach((fi, rank) => {
    const fac = hubCandidates[fi];
    const color = PALETTE[rank % PALETTE.length];
    const icon = L.divIcon({
      className: '',
      html: `<div style="position:relative;width:44px;height:44px;">
               <div style="position:absolute;inset:0;border-radius:50%;
                 border:3px solid ${color};opacity:.45;
                 animation:hubPulse 1.8s ease-in-out infinite;"></div>
               <div style="position:absolute;inset:6px;border-radius:50%;
                 background:radial-gradient(circle,${color} 30%,${color}cc 100%);
                 border:2.5px solid #fff;display:flex;align-items:center;
                 justify-content:center;font-size:16px;color:#fff;
                 box-shadow:0 0 22px ${color},0 0 8px #fff6;">H</div>
             </div>`,
      iconSize: [44, 44],
      iconAnchor: [22, 22],
      popupAnchor: [0, -24],
    });
    const coverage = hubCoverage[fi] || [];
    const coveredTargets = coverage.filter(ci => scores[ci] > 0 && currentTargetCells.has(ci));
    const cov = coverage.filter(ci => scores[ci] > 0).length;
    const hotCov = coveredTargets.length;
    const demandSum = coveredTargets.reduce((sum, ci) => sum + getTargetWeight(ci, scores), 0);

    const marker = L.marker([fac.lat, fac.lon], { icon })
      .bindPopup(
        `<div style="font-family:'Noto Sans KR';font-size:12px;">` +
        `<b style="font-size:14px;color:${color};">#${rank + 1} ${fac.name}</b><br>` +
        `시설: ${fac.facility} | 수용: ${fac.capacity}대<br>` +
        `적합 셀 커버: <b>${cov}</b>셀 | 분석 대상 노드: <b>${hotCov}</b>개<br>` +
        `커버 우선순위 합계: <b>${demandSum.toFixed(2)}</b></div>`
      )
      .addTo(map);
    hubMarkers.push(marker);

    const circle = L.circle([fac.lat, fac.lon], {
      radius: 500,
      color,
      weight: 2.5,
      fillColor: color,
      fillOpacity: 0.10,
      dashArray: '10,5',
      opacity: 0.85,
    }).addTo(map);
    servicePolys.push(circle);

    const topCells = coverage
      .filter(ci => scores[ci] > 0 && currentTargetCells.has(ci))
      .sort((a, b) => getTargetWeight(b, scores) - getTargetWeight(a, scores))
      .slice(0, 5);
    topCells.forEach(ci => {
      const cell = GRID[ci];
      const line = L.polyline([[fac.lat, fac.lon], [cell.lat, cell.lon]], {
        color,
        weight: 2,
        opacity: 0.55,
        dashArray: '8,5',
      }).addTo(map);
      routeLines.push(line);
    });
  });
}

function renderHubList(selFacIndices, scores, hotspots) {
  const container = document.getElementById('hub-list');
  const badge = document.getElementById('hub-count-badge');
  badge.textContent = `${selFacIndices.length}개 거점`;

  if (selFacIndices.length === 0) {
    container.innerHTML = '<div style="color:#e94560;font-size:12px;padding:8px;">선택된 레이어에서 커버 가능한 고수요 거점이 없습니다.</div>';
    return;
  }

  const coveredSoFar = new Set();
  container.innerHTML = '';
  selFacIndices.forEach((fi, rank) => {
    const fac = hubCandidates[fi];
    const color = PALETTE[rank % PALETTE.length];
    const coverage = hubCoverage[fi] || [];
    const newHot = coverage.filter(ci => hotspots.has(ci) && !coveredSoFar.has(ci));
    newHot.forEach(ci => coveredSoFar.add(ci));
    const pct = hotspots.size > 0 ? (coveredSoFar.size / hotspots.size * 100) : 0;
    const demandSum = newHot.reduce((sum, ci) => sum + getTargetWeight(ci, scores), 0);

    const item = document.createElement('div');
    item.className = 'hub-item new-hub';
    item.innerHTML = `
      <span class="hub-rank">${rank + 1}</span>
      <div class="hub-name" style="color:${color};">#${rank + 1} ${fac.name}</div>
      <div class="hub-detail">${fac.facility} · 수용 ${fac.capacity}대 · 신규 대상 ${newHot.length}개</div>
      <div class="hub-detail" style="color:#7ba;">신규 우선순위 합계 ${demandSum.toFixed(2)} · 누적 커버 ${pct.toFixed(1)}%</div>
      <div class="hub-coverage-bar"><div class="hub-coverage-fill" style="width:${pct}%;"></div></div>
    `;
    container.appendChild(item);
  });
}
