function updateDashboard() {
  const active = getActiveLayers();
  const activePoi = getActivePoiLayers();
  const scores = GRID.map(cell => recalcScore(cell, active));

  buildHexLayer(scores);

  const result = selectHubs(scores, activePoi);
  const selFacIndices = result.hubs;
  const feasible = result.feasible;
  const hotspots = result.hotspots;
  const uncovered = result.uncovered;

  buildHubLayer(selFacIndices, scores);
  renderHubList(selFacIndices, scores, hotspots);

  document.getElementById('kpi-feasible').textContent = feasible.size.toLocaleString();
  document.getElementById('kpi-num-hubs').textContent = selFacIndices.length;

  const coveredHots = hotspots.size - (uncovered ? uncovered.size : 0);
  const covPct = hotspots.size > 0 ? (coveredHots / hotspots.size * 100).toFixed(1) : '0.0';
  document.getElementById('kpi-coverage').textContent = `${covPct}%`;

  const highDemandDongCount = DEMAND.filter(row => row.demand >= DEMAND_THR).length;
  const highDemandKpi = document.getElementById('kpi-high-demand-dongs');
  if (highDemandKpi) highDemandKpi.textContent = highDemandDongCount.toLocaleString();

  const names = { sa: '공역', so: '장애물', sn: '소음', st: '지형', sw: '기상' };
  const poiNames = { park: '공원', commercial: '상권', medical: '의료', subway: '지하철', school: '학교' };
  const parts = Object.entries(active).filter(([, v]) => v).map(([k]) => names[k]);
  const poiParts = Object.entries(activePoi).filter(([, v]) => v).map(([k]) => poiNames[k]);
  const poiLabel = poiParts.length ? ` × POI(${poiParts.join(', ')})` : '';
  document.getElementById('formula-display').textContent =
    parts.length ? `${parts.join(' × ')} × 드론 수요지수${poiLabel}` : '(선택 없음 - 모든 셀 점수 0)';
}

document.querySelectorAll('.layer-toggle').forEach(label => {
  label.addEventListener('click', function(e) {
    const inp = this.querySelector('input');
    inp.checked = !inp.checked;
    this.classList.toggle('active', inp.checked);
    const spin = document.getElementById('update-spin');
    spin.classList.add('show');
    setTimeout(() => {
      updateDashboard();
      spin.classList.remove('show');
    }, 30);
    e.preventDefault();
  });
});
