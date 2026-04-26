const plotlyLayout = {
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  font: { family: 'Noto Sans KR', color: '#bbc', size: 12 },
  margin: { l: 50, r: 20, t: 10, b: 50 },
};

(() => {
  const sorted = [...DEMAND].sort((a, b) => b.demand - a.demand).slice(0, 15);
  Plotly.newPlot('chart-bar', [{
    type: 'bar',
    x: sorted.map(d => d.dong),
    y: sorted.map(d => d.demand),
    marker: {
      color: sorted.map(d => scoreToColor(d.demand)),
      line: { color: '#0f3460', width: 1 },
    },
    text: sorted.map(d => d.demand.toFixed(3)),
    textposition: 'outside',
    textfont: { size: 10, color: '#aab' },
    customdata: sorted.map(d => [d.rank, d.hr, d.fp, d.cc, d.od]),
    hovertemplate:
      '%{x}<br>수요지수: %{y:.3f}<br>순위: %{customdata[0]}위<br>' +
      '주거 %{customdata[1]:.3f} / 유동 %{customdata[2]:.3f}<br>' +
      '소비 %{customdata[3]:.3f} / 주문 %{customdata[4]:.3f}<extra></extra>',
  }], {
    ...plotlyLayout,
    xaxis: { tickangle: -35, tickfont: { size: 11 }, gridcolor: '#0f346033' },
    yaxis: { range: [0, 1], gridcolor: '#0f346044', zeroline: false },
    margin: { ...plotlyLayout.margin, b: 80 },
  }, { responsive: true, displayModeBar: false });
})();

(() => {
  const top = [...DEMAND].sort((a, b) => b.demand - a.demand).slice(0, 5);
  Plotly.newPlot('chart-radar', [
    { type: 'scatterpolar', r: top.map(d => d.hr), theta: top.map(d => d.dong),
      fill: 'toself', fillcolor: 'rgba(83,215,105,0.12)', line: { color: '#53d769', width: 2 },
      name: '주거/가구', marker: { size: 6 } },
    { type: 'scatterpolar', r: top.map(d => d.fp), theta: top.map(d => d.dong),
      fill: 'toself', fillcolor: 'rgba(79,195,247,0.12)', line: { color: '#4fc3f7', width: 2 },
      name: '유동인구', marker: { size: 6 } },
    { type: 'scatterpolar', r: top.map(d => d.cc), theta: top.map(d => d.dong),
      fill: 'toself', fillcolor: 'rgba(255,183,77,0.10)', line: { color: '#ffb74d', width: 2 },
      name: '소비', marker: { size: 6 } },
    { type: 'scatterpolar', r: top.map(d => d.od), theta: top.map(d => d.dong),
      fill: 'toself', fillcolor: 'rgba(233,69,96,0.10)', line: { color: '#e94560', width: 2 },
      name: '주문/상권', marker: { size: 6 } },
  ], {
    ...plotlyLayout,
    polar: {
      bgcolor: 'rgba(0,0,0,0)',
      radialaxis: { visible: true, range: [0, 1], gridcolor: '#0f346055', tickfont: { size: 9 } },
      angularaxis: { gridcolor: '#0f346055', tickfont: { size: 10 } },
    },
    legend: { x: 0.78, y: 1.18, font: { size: 10 } },
    margin: { l: 30, r: 30, t: 20, b: 20 },
  }, { responsive: true, displayModeBar: false });
})();

(() => {
  const labels = { 1: '0-2h', 2: '2-4h', 3: '6-8h', 4: '8-10h', 5: '10-12h',
                   6: '12-14h', 7: '14-18h', 8: '18-21h', 9: '21-23h', 10: '23-24h' };
  Plotly.newPlot('chart-hourly', [{
    type: 'scatter',
    mode: 'lines+markers',
    x: HOURLY.map(h => labels[h.hour] || `T${h.hour}`),
    y: HOURLY.map(h => h.avg_ratio),
    line: { color: '#4fc3f7', width: 3, shape: 'spline' },
    marker: { size: 8, color: '#4fc3f7', line: { color: '#fff', width: 1 } },
    fill: 'tozeroy',
    fillcolor: 'rgba(79,195,247,0.1)',
    hovertemplate: '%{x}<br>비율: %{y:.3f}<extra></extra>',
  }], {
    ...plotlyLayout,
    xaxis: { tickangle: -25, gridcolor: '#0f346033' },
    yaxis: { gridcolor: '#0f346044', zeroline: false },
  }, { responsive: true, displayModeBar: false });
})();

(() => {
  const sorted = [...DONG].filter(d => d.pct_f > 0).sort((a, b) => a.pct_f - b.pct_f);
  Plotly.newPlot('chart-feasible', [{
    type: 'bar',
    orientation: 'h',
    y: sorted.map(d => `${d.name} (${d.gu})`),
    x: sorted.map(d => d.pct_f),
    marker: {
      color: sorted.map(d => d.pct_f >= 80 ? '#53d769' : d.pct_f >= 40 ? '#ffb74d' : '#e94560'),
      line: { color: '#0f3460', width: 1 },
    },
    text: sorted.map(d => `${d.pct_f.toFixed(1)}%`),
    textposition: 'outside',
    textfont: { size: 10, color: '#aab' },
    hovertemplate: '%{y}<br>적합 비율: %{x:.1f}%<extra></extra>',
  }], {
    ...plotlyLayout,
    xaxis: { range: [0, 115], gridcolor: '#0f346044' },
    yaxis: { tickfont: { size: 10 }, automargin: true },
    margin: { l: 150, r: 40, t: 10, b: 40 },
    height: Math.max(220, sorted.length * 22),
  }, { responsive: true, displayModeBar: false });
})();

(() => {
  const tbody = document.getElementById('comp-tbody');
  MODE.forEach(r => {
    const tr = document.createElement('tr');
    const adv = r.advantage === 'O';
    tr.innerHTML = `<td>${r.indicator}</td><td>${r.motorcycle}</td><td>${r.drone}</td>
      <td><span class="tag ${adv ? 'tag-green' : 'tag-red'}">${r.advantage}</span></td>`;
    tbody.appendChild(tr);
  });
})();
