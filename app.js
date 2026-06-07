// app.js  —  application logic, rendering, charts

let trades = [];
const charts = {};

// ── INIT ───────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  trades = loadTrades();
  initTabs();
  setDefaultDatetime();
  seedKellyFromHistory();
  renderAll();
});

function seedKellyFromHistory() {
  if (trades.length < 10) return;
  const m = calcMetrics(trades);
  document.getElementById('kelly-winrate').value = Math.round(m.winRate * 100);
  document.getElementById('kelly-avgwin').value  = m.avgWin.toFixed(2);
  document.getElementById('kelly-avgloss').value = m.avgLoss.toFixed(2);
}

function renderAll() {
  renderDashboard();
  renderTradeLog();
  calcEdge();
  calcKelly();
  const activeTab = document.querySelector('.tab-btn.active').dataset.tab;
  if (activeTab === 'edge') renderEdgeCharts();
}

// ── TABS ───────────────────────────────────────────────────────────────────────
function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
      if (btn.dataset.tab === 'dashboard') renderDashboardCharts();
      if (btn.dataset.tab === 'edge') renderEdgeCharts();
    });
  });
}

// ── METRICS ────────────────────────────────────────────────────────────────────
function calcMetrics(ts) {
  const wins   = ts.filter(t => t.outcome === 'win');
  const losses = ts.filter(t => t.outcome === 'loss');
  const nonPush = ts.filter(t => t.outcome !== 'push');

  const totalPnl   = ts.reduce((s, t) => s + t.pnl, 0);
  const grossWin   = wins.reduce((s, t) => s + t.pnl, 0);
  const grossLoss  = Math.abs(losses.reduce((s, t) => s + t.pnl, 0));
  const winRate    = nonPush.length ? wins.length / nonPush.length : 0;
  const profitFactor = grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : 0);
  const avgWin  = wins.length   ? grossWin   / wins.length   : 0;
  const avgLoss = losses.length ? grossLoss  / losses.length : 0;

  // Max drawdown
  let peak = 0, maxDD = 0, cum = 0;
  for (const t of ts) {
    cum += t.pnl;
    if (cum > peak) peak = cum;
    maxDD = Math.max(maxDD, peak - cum);
  }

  // Streaks
  let curStreak = 0, longestWin = 0, tmpW = 0;
  if (nonPush.length) {
    const last = nonPush[nonPush.length - 1].outcome;
    let i = nonPush.length - 1;
    while (i >= 0 && nonPush[i].outcome === last) { curStreak++; i--; }
    if (last === 'loss') curStreak = -curStreak;
  }
  for (const t of nonPush) {
    if (t.outcome === 'win') { tmpW++; longestWin = Math.max(longestWin, tmpW); }
    else tmpW = 0;
  }

  const pnls = ts.map(t => t.pnl);

  return {
    total:         ts.length,
    winRate,
    totalPnl,
    avgPnl:        ts.length ? totalPnl / ts.length : 0,
    profitFactor,
    maxDrawdown:   maxDD,
    bestTrade:     pnls.length ? Math.max(...pnls) : 0,
    worstTrade:    pnls.length ? Math.min(...pnls) : 0,
    avgWin,
    avgLoss,
    curStreak,
    longestWin,
  };
}

// ── DASHBOARD ──────────────────────────────────────────────────────────────────
function renderDashboard() {
  const m = calcMetrics(trades);

  const defs = [
    { label: 'Total Trades',    val: m.total,       fmt: 'int',     cls: '' },
    { label: 'Win Rate',        val: m.winRate*100,  fmt: 'pct',     cls: m.winRate>=0.5 ? 'pos':'neg' },
    { label: 'Total P/L',       val: m.totalPnl,    fmt: 'dollar',  cls: m.totalPnl>=0 ? 'pos':'neg' },
    { label: 'Avg P/L / Trade', val: m.avgPnl,      fmt: 'dollar',  cls: m.avgPnl>=0 ? 'pos':'neg' },
    { label: 'Profit Factor',   val: m.profitFactor,fmt: 'ratio',   cls: m.profitFactor>=1 ? 'pos':'neg' },
    { label: 'Max Drawdown',    val: m.maxDrawdown, fmt: 'dollar-',  cls: 'neg' },
    { label: 'Best Trade',      val: m.bestTrade,   fmt: 'dollar',  cls: 'pos' },
    { label: 'Worst Trade',     val: m.worstTrade,  fmt: 'dollar',  cls: 'neg' },
    { label: 'Avg Winner',      val: m.avgWin,      fmt: 'dollar',  cls: 'pos' },
    { label: 'Avg Loser',       val: m.avgLoss,     fmt: 'dollar-', cls: 'neg' },
    { label: 'Current Streak',  val: m.curStreak,   fmt: 'streak',  cls: m.curStreak>0?'pos':m.curStreak<0?'neg':'' },
    { label: 'Longest Win Run', val: m.longestWin,  fmt: 'int',     cls: 'pos' },
  ];

  document.getElementById('metrics-grid').innerHTML = defs.map(d => `
    <div class="metric-card">
      <div class="metric-label">${d.label}</div>
      <div class="metric-value ${d.cls}">${fmtMetric(d.val, d.fmt)}</div>
    </div>
  `).join('');

  renderStreak(m);
  renderDashboardCharts();
}

function fmtMetric(v, fmt) {
  if (fmt === 'dollar')  return (v >= 0 ? '+' : '') + '$' + Math.abs(v).toFixed(2);
  if (fmt === 'dollar-') return '-$' + Math.abs(v).toFixed(2);
  if (fmt === 'pct')     return v.toFixed(1) + '%';
  if (fmt === 'ratio')   return isFinite(v) ? v.toFixed(2) + 'x' : '∞';
  if (fmt === 'int')     return String(v);
  if (fmt === 'streak')  return v === 0 ? '—' : (v > 0 ? `+${v}W` : `${Math.abs(v)}L`);
  return v;
}

function renderStreak(m) {
  const nonPush = trades.filter(t => t.outcome !== 'push');
  const last30  = nonPush.slice(-30);

  const cls  = m.curStreak > 0 ? 'pos' : m.curStreak < 0 ? 'neg' : '';
  const text = m.curStreak === 0 ? '—' : m.curStreak > 0 ? `${m.curStreak}W` : `${Math.abs(m.curStreak)}L`;

  document.getElementById('streak-tracker').innerHTML = `
    <div class="streak-block">
      <div class="streak-label">Current Streak</div>
      <div class="streak-value ${cls}">${text}</div>
    </div>
    <div class="streak-block">
      <div class="streak-label">Longest Win Run</div>
      <div class="streak-value pos">${m.longestWin}W</div>
    </div>
    <div style="flex:1">
      <div class="streak-label">Last ${last30.length} Resolved Trades</div>
      <div class="streak-dots">
        ${last30.map(t => `<div class="streak-dot ${t.outcome}" title="${new Date(t.datetime).toLocaleDateString()} · ${t.outcome} · $${t.pnl >= 0 ? '+' : ''}${t.pnl.toFixed(2)}"></div>`).join('')}
      </div>
    </div>
  `;
}

// ── DASHBOARD CHARTS ───────────────────────────────────────────────────────────
function renderDashboardCharts() {
  // P/L Curve
  const sorted = [...trades].sort((a, b) => new Date(a.datetime) - new Date(b.datetime));
  let cum = 0;
  const labels   = [];
  const cumPnls  = [];
  const colors   = [];

  for (const t of sorted) {
    cum += t.pnl;
    labels.push(new Date(t.datetime).toLocaleDateString('en-US', { month:'short', day:'numeric' }));
    cumPnls.push(Math.round(cum * 100) / 100);
    colors.push(cum >= 0 ? '#3fb950' : '#f85149');
  }

  const finalColor = cum >= 0 ? '#3fb950' : '#f85149';
  const fillColor  = cum >= 0 ? 'rgba(63,185,80,0.08)' : 'rgba(248,81,73,0.08)';

  destroyChart('plCurve');
  const plCtx = document.getElementById('plCurveChart').getContext('2d');
  charts.plCurve = new Chart(plCtx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: cumPnls,
        borderColor: finalColor,
        backgroundColor: fillColor,
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        pointHoverBackgroundColor: finalColor,
        fill: true,
        tension: 0.35,
      }],
    },
    options: sharedOpts('$'),
  });

  // Calibration chart
  // Bucket adjusted probabilities (YES side = myProb, NO side = 100-myProb)
  const buckets = {};
  for (let b = 10; b <= 90; b += 10) buckets[b] = { wins: 0, total: 0 };

  for (const t of trades) {
    if (t.outcome === 'push') continue;
    const adjProb = t.side === 'YES'
      ? (t.myProbability || t.entryPrice)
      : 100 - (t.myProbability || t.entryPrice);
    const key = Math.min(90, Math.max(10, Math.round(adjProb / 10) * 10));
    if (!buckets[key]) buckets[key] = { wins: 0, total: 0 };
    buckets[key].total++;
    if (t.outcome === 'win') buckets[key].wins++;
  }

  const calLabels  = Object.keys(buckets).map(b => b + '%');
  const calActual  = Object.keys(buckets).map(b => buckets[b].total > 0 ? Math.round(buckets[b].wins / buckets[b].total * 100) : null);
  const calIdeal   = Object.keys(buckets).map(Number);
  const calCounts  = Object.keys(buckets).map(b => buckets[b].total);

  destroyChart('calibration');
  const calCtx = document.getElementById('calibrationChart').getContext('2d');
  charts.calibration = new Chart(calCtx, {
    type: 'bar',
    data: {
      labels: calLabels,
      datasets: [
        {
          label: 'Actual Win %',
          data: calActual,
          backgroundColor: calActual.map((v, i) => {
            if (v === null) return 'rgba(48,54,61,0.3)';
            const diff = v - calIdeal[i];
            return diff > 5 ? 'rgba(63,185,80,0.75)' : diff < -5 ? 'rgba(248,81,73,0.75)' : 'rgba(88,166,255,0.75)';
          }),
          borderRadius: 3,
          order: 1,
        },
        {
          label: 'Perfect Calibration',
          data: calIdeal,
          type: 'line',
          borderColor: 'rgba(140,149,158,0.45)',
          borderDash: [5, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false,
          order: 0,
        },
      ],
    },
    options: {
      ...sharedOpts('%'),
      plugins: {
        legend: {
          display: true,
          labels: { color: '#8b949e', font: { family: 'monospace', size: 10 }, boxWidth: 14 },
        },
        tooltip: {
          ...sharedOpts('%').plugins.tooltip,
          callbacks: {
            label: ctx => {
              if (ctx.datasetIndex === 0) {
                const n = calCounts[ctx.dataIndex];
                const v = ctx.raw;
                return v === null ? `No data` : `Actual: ${v}% (n=${n})`;
              }
              return `Ideal: ${ctx.raw}%`;
            },
          },
        },
      },
    },
  });
}

// ── TRADE LOG ──────────────────────────────────────────────────────────────────
function renderTradeLog() {
  const typeFilter    = document.getElementById('filter-type').value;
  const outcomeFilter = document.getElementById('filter-outcome').value;

  let filtered = [...trades].sort((a, b) => new Date(b.datetime) - new Date(a.datetime));
  if (typeFilter)    filtered = filtered.filter(t => t.marketType === typeFilter);
  if (outcomeFilter) filtered = filtered.filter(t => t.outcome    === outcomeFilter);

  document.getElementById('trade-count').textContent = `${filtered.length} of ${trades.length} trades`;

  const tbody = document.getElementById('trade-table-body');
  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="11" style="text-align:center;color:var(--muted);padding:36px">No trades match these filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(t => {
    const dt = new Date(t.datetime);
    const pnlCls = t.pnl >= 0 ? 'pos' : 'neg';
    const pnlStr = (t.pnl >= 0 ? '+' : '') + '$' + Math.abs(t.pnl).toFixed(2);
    return `
      <tr>
        <td style="white-space:nowrap;color:var(--muted)">
          ${dt.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'2-digit'})}
          ${dt.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}
        </td>
        <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(t.market)}">${esc(t.market)}</td>
        <td><span class="badge badge-${t.marketType}">${t.marketType}</span></td>
        <td><span class="badge badge-${t.side.toLowerCase()}">${t.side}</span></td>
        <td>${t.entryPrice}%</td>
        <td style="color:var(--muted)">${t.myProbability != null ? t.myProbability + '%' : '—'}</td>
        <td>$${t.posSize}</td>
        <td class="${pnlCls}" style="font-weight:700">${pnlStr}</td>
        <td><span class="badge badge-${t.outcome}">${t.outcome}</span></td>
        <td style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)">${esc(t.notes) || '—'}</td>
        <td><button class="btn-danger" onclick="handleDelete('${t.id}')" title="Delete">×</button></td>
      </tr>
    `;
  }).join('');
}

function handleDelete(id) {
  if (!confirm('Delete this trade? This cannot be undone.')) return;
  trades = deleteTrade(id);
  renderAll();
}

function esc(str) {
  return String(str || '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

// ── EDGE ANALYSIS ──────────────────────────────────────────────────────────────
function calcEdge() {
  const myProb   = parseFloat(document.getElementById('edge-myprob').value)   || 0;
  const mktPrice = parseFloat(document.getElementById('edge-mktprice').value)  || 0;
  const spread   = parseFloat(document.getElementById('edge-spread').value)    || 0;
  const fees     = parseFloat(document.getElementById('edge-fees').value)      || 0;

  const rawEdge = myProb - mktPrice;
  const adjEdge = rawEdge - spread / 2 - fees;
  const evPer100 = adjEdge; // adj edge IS the EV as a % of stake for binary

  const rCls = rawEdge > 0 ? 'pos' : rawEdge < 0 ? 'neg' : '';
  const aCls = adjEdge > 0 ? 'pos' : adjEdge < 0 ? 'neg' : '';

  const rec = adjEdge < 3
    ? '<span class="neg">Skip — below noise floor</span>'
    : adjEdge < 5
    ? '<span class="warn">Weak: 1/8 Kelly max</span>'
    : adjEdge < 10
    ? '<span class="pos">Standard: 1/4 Kelly</span>'
    : adjEdge < 15
    ? '<span class="pos">Strong: up to 1/2 Kelly</span>'
    : '<span class="pos">Fat pitch: 1/2 Kelly (hard cap)</span>';

  document.getElementById('edge-results').innerHTML = `
    <div>
      <div class="r-label">Raw Edge</div>
      <div class="r-value ${rCls}">${rawEdge > 0 ? '+' : ''}${rawEdge.toFixed(1)}%</div>
    </div>
    <div>
      <div class="r-label">Adjusted Edge</div>
      <div class="r-value ${aCls}">${adjEdge > 0 ? '+' : ''}${adjEdge.toFixed(1)}%</div>
    </div>
    <div>
      <div class="r-label">EV / $100 Risked</div>
      <div class="r-value ${aCls}">${adjEdge >= 0 ? '+' : ''}$${evPer100.toFixed(2)}</div>
    </div>
    <div style="grid-column:1/-1;padding-top:4px;font-size:12px">
      <span style="color:var(--muted);margin-right:6px">Recommendation:</span>${rec}
    </div>
  `;
}

function renderEdgeCharts() {
  // P/L by market type
  const typeMap = {};
  for (const t of trades) {
    if (!typeMap[t.marketType]) typeMap[t.marketType] = { pnl: 0, wins: 0, total: 0 };
    typeMap[t.marketType].pnl   += t.pnl;
    typeMap[t.marketType].total += 1;
    if (t.outcome === 'win') typeMap[t.marketType].wins++;
  }

  const types = Object.keys(typeMap).sort((a, b) => typeMap[b].pnl - typeMap[a].pnl);
  const typePnls   = types.map(k => Math.round(typeMap[k].pnl * 100) / 100);
  const typeColors = typePnls.map(v => v >= 0 ? 'rgba(63,185,80,0.72)' : 'rgba(248,81,73,0.72)');

  destroyChart('plByType');
  charts.plByType = new Chart(
    document.getElementById('plByTypeChart').getContext('2d'),
    {
      type: 'bar',
      data: {
        labels: types,
        datasets: [{
          data: typePnls,
          backgroundColor: typeColors,
          borderRadius: 4,
        }],
      },
      options: {
        ...sharedOpts('$'),
        plugins: {
          ...sharedOpts('$').plugins,
          legend: { display: false },
          tooltip: {
            ...sharedOpts('$').plugins.tooltip,
            callbacks: {
              label: ctx => {
                const k = types[ctx.dataIndex];
                const wr = typeMap[k].total ? Math.round(typeMap[k].wins / typeMap[k].total * 100) : 0;
                return [`P/L: $${ctx.raw.toFixed(2)}`, `Win rate: ${wr}% (${typeMap[k].total} trades)`];
              },
            },
          },
        },
      },
    }
  );

  // Win rate by hour
  const hourMap = Array.from({ length: 24 }, () => ({ wins: 0, total: 0 }));
  for (const t of trades) {
    if (t.outcome === 'push') continue;
    const h = new Date(t.datetime).getHours();
    hourMap[h].total++;
    if (t.outcome === 'win') hourMap[h].wins++;
  }

  const hLabels = Array.from({ length: 24 }, (_, h) => {
    const ap = h >= 12 ? 'p' : 'a';
    const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
    return `${h12}${ap}`;
  });

  const winRates = hourMap.map(h => h.total > 0 ? Math.round(h.wins / h.total * 100) : null);
  const barColors = winRates.map(v =>
    v === null              ? 'rgba(48,54,61,0.3)'
    : v >= 55               ? 'rgba(63,185,80,0.72)'
    : v >= 45               ? 'rgba(88,166,255,0.72)'
    :                         'rgba(248,81,73,0.72)'
  );

  destroyChart('winByHour');
  charts.winByHour = new Chart(
    document.getElementById('winByHourChart').getContext('2d'),
    {
      type: 'bar',
      data: {
        labels: hLabels,
        datasets: [{
          data: winRates,
          backgroundColor: barColors,
          borderRadius: 3,
        }],
      },
      options: {
        ...sharedOpts('%'),
        plugins: {
          ...sharedOpts('%').plugins,
          legend: { display: false },
          tooltip: {
            ...sharedOpts('%').plugins.tooltip,
            callbacks: {
              label: ctx => {
                const h = hourMap[ctx.dataIndex];
                return ctx.raw === null ? 'No trades' : `Win rate: ${ctx.raw}% (${h.total} trades)`;
              },
            },
          },
        },
      },
    }
  );
}

// ── KELLY ──────────────────────────────────────────────────────────────────────
function calcKelly() {
  const winRate  = (parseFloat(document.getElementById('kelly-winrate').value)  || 0) / 100;
  const avgWin   =  parseFloat(document.getElementById('kelly-avgwin').value)   || 0;
  const avgLoss  =  parseFloat(document.getElementById('kelly-avgloss').value)  || 1;
  const bankroll =  parseFloat(document.getElementById('kelly-bankroll').value)  || 1000;

  const b = avgWin / avgLoss;                   // win/loss ratio
  const q = 1 - winRate;
  const kelly    = Math.max(0, (b * winRate - q) / b);
  const kellyPct = kelly * 100;

  const full    = kelly    * bankroll;
  const half    = full     / 2;
  const quarter = full     / 4;
  const eighth  = full     / 8;

  const rCls = kellyPct > 0 ? 'pos' : 'neg';

  document.getElementById('kelly-results').innerHTML = `
    <div>
      <div class="r-label">Full Kelly %</div>
      <div class="r-value ${rCls}">${kellyPct.toFixed(1)}%</div>
    </div>
    <div>
      <div class="r-label">1/2 Kelly ($)</div>
      <div class="r-value pos">$${half.toFixed(2)}</div>
    </div>
    <div>
      <div class="r-label">1/4 Kelly ($)</div>
      <div class="r-value pos">$${quarter.toFixed(2)}</div>
    </div>
  `;

  // Hard cap warning
  const pct5 = bankroll * 0.05;
  const noteEl = document.getElementById('kelly-note');
  if (half > pct5) {
    noteEl.textContent = `⚠ 1/2 Kelly ($${half.toFixed(2)}) exceeds 5% bankroll cap ($${pct5.toFixed(2)}). Use $${pct5.toFixed(2)} max.`;
  } else if (kelly <= 0) {
    noteEl.textContent = 'Negative edge — do not trade this setup.';
  } else {
    noteEl.textContent = '';
  }

}

// ── CHART SHARED OPTIONS ───────────────────────────────────────────────────────
function sharedOpts(unit) {
  return {
    responsive:          true,
    maintainAspectRatio: true,
    animation:           { duration: 250 },
    scales: {
      x: {
        ticks: { color: '#8b949e', font: { family: 'monospace', size: 10 }, maxTicksLimit: 10 },
        grid:  { color: 'rgba(48,54,61,0.35)' },
      },
      y: {
        ticks: {
          color: '#8b949e',
          font:  { family: 'monospace', size: 10 },
          callback: v => unit === '$' ? '$' + v.toFixed(0) : v + '%',
        },
        grid: { color: 'rgba(48,54,61,0.35)' },
      },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#1c2128',
        titleColor:      '#f0f6fc',
        bodyColor:       '#c9d1d9',
        borderColor:     '#30363d',
        borderWidth:     1,
        titleFont: { family: 'monospace', size: 11 },
        bodyFont:  { family: 'monospace', size: 11 },
        callbacks: {
          label: ctx => unit === '$'
            ? `$${typeof ctx.raw === 'number' ? ctx.raw.toFixed(2) : ctx.raw}`
            : `${typeof ctx.raw === 'number' ? ctx.raw.toFixed(1) : ctx.raw}%`,
        },
      },
    },
  };
}

function destroyChart(key) {
  if (charts[key]) { charts[key].destroy(); delete charts[key]; }
}

// ── MODAL ──────────────────────────────────────────────────────────────────────
function openModal() {
  document.getElementById('trade-modal').classList.add('open');
}

function closeModal() {
  document.getElementById('trade-modal').classList.remove('open');
}

function closeModalOverlay(e) {
  if (e.target === document.getElementById('trade-modal')) closeModal();
}

function setDefaultDatetime() {
  const now   = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  document.getElementById('f-datetime').value = local.toISOString().slice(0, 16);
}

function submitTrade() {
  const market    = document.getElementById('f-market').value.trim();
  const entryStr  = document.getElementById('f-entry').value;
  const sizeStr   = document.getElementById('f-size').value;
  const pnlStr    = document.getElementById('f-pnl').value;

  if (!market)          { alert('Please enter a market description.'); return; }
  if (entryStr === '')  { alert('Please enter the entry price.'); return; }
  if (sizeStr  === '')  { alert('Please enter the position size.'); return; }
  if (pnlStr   === '')  { alert('Please enter the P/L.'); return; }

  const myProbRaw = document.getElementById('f-myprob').value;
  const entryPrice    = parseFloat(entryStr);
  const myProbability = myProbRaw !== '' ? parseFloat(myProbRaw) : entryPrice;
  const posSize       = parseFloat(sizeStr);
  const pnl           = parseFloat(pnlStr);

  const datetimeRaw = document.getElementById('f-datetime').value;
  const datetime    = datetimeRaw ? new Date(datetimeRaw).toISOString() : new Date().toISOString();

  trades = addTrade({
    datetime,
    market,
    marketType:    document.getElementById('f-type').value,
    side:          document.getElementById('f-side').value,
    entryPrice,
    myProbability,
    posSize,
    outcome:       document.getElementById('f-outcome').value,
    pnl,
    notes: document.getElementById('f-notes').value.trim(),
  });

  closeModal();
  ['f-market','f-entry','f-myprob','f-size','f-pnl','f-notes'].forEach(id => {
    document.getElementById(id).value = '';
  });
  setDefaultDatetime();
  renderAll();
}

// ── EXPORT ─────────────────────────────────────────────────────────────────────
function exportData(format) {
  const date = new Date().toISOString().slice(0, 10);
  let content, filename, mime;

  if (format === 'csv') {
    content  = toCSV(trades);
    filename = `trading_os_${date}.csv`;
    mime     = 'text/csv';
  } else {
    content  = JSON.stringify(trades, null, 2);
    filename = `trading_os_${date}.json`;
    mime     = 'application/json';
  }

  const a = document.createElement('a');
  a.href     = URL.createObjectURL(new Blob([content], { type: mime }));
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
