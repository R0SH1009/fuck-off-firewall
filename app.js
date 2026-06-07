// app.js  —  all rendering, charts, UI logic

let trades = [];
let scanResults = [];
const CH = {};  // chart instances

// ── INIT ───────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  trades = loadTrades();
  initTabs();
  setDefaultDatetime();
  renderAll();
  runScan();
  runMC();
  calcKelly();
  calcEdge();
  checkGuardrails();
});

function cfg() {
  return {
    bankroll:  parseFloat(document.getElementById('g-bankroll').value) || 10000,
    kellyFrac: parseFloat(document.getElementById('g-kelly').value)    || 0.25,
    minEdge:   parseFloat(document.getElementById('g-min-edge').value) || 0.03,
    maxRisk:   parseFloat(document.getElementById('g-max-risk').value) || 0.05,
  };
}

function onSettingsChange() {
  renderAll();
  updateQuickStats();
  if (document.querySelector('[data-tab="risk"].active')) { calcKelly(); calcEdge(); checkGuardrails(); }
  if (document.querySelector('[data-tab="recs"].active')) renderRecs();
}

function renderAll() {
  const m = calcMetrics(trades);
  updateQuickStats(m);
  renderDashboard(m);
  renderTradeLog();
  renderAnalytics(m);
}

// ── QUICK STATS ────────────────────────────────────────────────────────────────
function updateQuickStats(m) {
  m = m || calcMetrics(trades);
  const c = cfg();
  const bankroll = c.bankroll + m.totalPnl;
  document.getElementById('qs-bankroll').textContent = '$' + bankroll.toLocaleString('en-US', {minimumFractionDigits:2,maximumFractionDigits:2});
  const pnlEl = document.getElementById('qs-pnl');
  pnlEl.textContent = m.settled ? (m.totalPnl>=0?'+':'')+'$'+Math.abs(m.totalPnl).toFixed(2) : '—';
  pnlEl.className = 'stat-val ' + (m.totalPnl>0?'pos':m.totalPnl<0?'neg':'');
  document.getElementById('qs-winrate').textContent = m.settled ? (m.winRate*100).toFixed(1)+'%' : '—';
  document.getElementById('qs-open').textContent = m.open;
}

// ── TABS ───────────────────────────────────────────────────────────────────────
function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
      // Lazy-render charts when tab becomes visible
      const t = btn.dataset.tab;
      if (t === 'dashboard')  renderDashboardCharts();
      if (t === 'analytics')  renderAnalyticsCharts();
      if (t === 'montecarlo') runMC();
      if (t === 'risk')       { calcKelly(); calcEdge(); checkGuardrails(); }
      if (t === 'recs')       renderRecs();
    });
  });
}

function activeTab() {
  const a = document.querySelector('.tab-btn.active');
  return a ? a.dataset.tab : 'dashboard';
}

// ── DASHBOARD ──────────────────────────────────────────────────────────────────
function renderDashboard(m) {
  m = m || calcMetrics(trades);
  const defs = [
    { label:'Total Trades',    val:m.total,        fmt:'int',     cls:'' },
    { label:'Win Rate',        val:m.winRate*100,   fmt:'pct',     cls:m.winRate>=.5?'pos':'neg' },
    { label:'Total P/L',       val:m.totalPnl,     fmt:'dollar',  cls:m.totalPnl>=0?'pos':'neg' },
    { label:'Avg P/L / Trade', val:m.avgPnl,       fmt:'dollar',  cls:m.avgPnl>=0?'pos':'neg' },
    { label:'Profit Factor',   val:m.profitFactor, fmt:'ratio',   cls:m.profitFactor>=1?'pos':'neg' },
    { label:'Max Drawdown',    val:m.maxDrawdown,  fmt:'ddollar', cls:'neg' },
    { label:'Best Trade',      val:m.bestTrade,    fmt:'dollar',  cls:'pos' },
    { label:'Worst Trade',     val:m.worstTrade,   fmt:'dollar',  cls:'neg' },
    { label:'Avg Winner',      val:m.avgWin,       fmt:'dollar',  cls:'pos' },
    { label:'Avg Loser',       val:m.avgLoss,      fmt:'ddollar', cls:'neg' },
    { label:'Current Streak',  val:m.curStreak,    fmt:'streak',  cls:m.curStreak>0?'pos':m.curStreak<0?'neg':'' },
    { label:'Longest Win Run', val:m.longestWin,   fmt:'int',     cls:'pos' },
  ];
  document.getElementById('metrics-grid').innerHTML = defs.map(d =>
    `<div class="metric-card"><div class="metric-label">${d.label}</div><div class="metric-value ${d.cls}">${fmtVal(d.val, d.fmt)}</div></div>`
  ).join('');

  renderStreak(m);
  if (activeTab() === 'dashboard') renderDashboardCharts();
}

function fmtVal(v, fmt) {
  if (fmt==='dollar')  return (v>=0?'+':'') + '$' + Math.abs(v).toFixed(2);
  if (fmt==='ddollar') return '-$' + Math.abs(v).toFixed(2);
  if (fmt==='pct')     return v.toFixed(1) + '%';
  if (fmt==='ratio')   return isFinite(v) ? v.toFixed(2)+'x' : '∞';
  if (fmt==='int')     return String(v);
  if (fmt==='streak')  return v===0?'—': v>0?`+${v}W`:`${Math.abs(v)}L`;
  return v;
}

function renderStreak(m) {
  const settled = trades.filter(t => t.settled && t.outcome !== 'push');
  const last30  = settled.slice(-30);
  const cls     = m.curStreak>0?'pos':m.curStreak<0?'neg':'';
  const text    = m.curStreak===0?'—': m.curStreak>0?`${m.curStreak}W`:`${Math.abs(m.curStreak)}L`;
  document.getElementById('streak-tracker').innerHTML = `
    <div class="streak-block"><div class="streak-label">Current Streak</div><div class="streak-value ${cls}">${text}</div></div>
    <div class="streak-block"><div class="streak-label">Longest Win Run</div><div class="streak-value pos">${m.longestWin}W</div></div>
    <div style="flex:1">
      <div class="streak-label">Last ${last30.length} resolved</div>
      <div class="streak-dots">${last30.map(t=>`<div class="streak-dot ${t.outcome}" title="${new Date(t.datetime).toLocaleDateString()} · ${t.outcome} · $${(t.pnl||0)>=0?'+':''}${(t.pnl||0).toFixed(2)}"></div>`).join('')}</div>
    </div>`;
}

function renderDashboardCharts() {
  const sorted = [...trades].filter(t=>t.settled).sort((a,b)=>new Date(a.datetime)-new Date(b.datetime));
  let cum=0;
  const labels=[], vals=[];
  for (const t of sorted) {
    cum+=t.pnl||0;
    labels.push(new Date(t.datetime).toLocaleDateString('en-US',{month:'short',day:'numeric'}));
    vals.push(Math.round(cum*100)/100);
  }
  const c = cum>=0?'#3fb950':'#f85149';
  destroyChart('plCurve');
  CH.plCurve = new Chart(document.getElementById('plCurveChart').getContext('2d'), {
    type:'line',
    data:{ labels, datasets:[{ data:vals, borderColor:c, backgroundColor:c+'14', borderWidth:2, pointRadius:0, pointHoverRadius:4, fill:true, tension:.35 }] },
    options: chartOpts('$'),
  });

  // Calibration
  const bins={};
  for (let b=10;b<=90;b+=10) bins[b]={wins:0,total:0};
  for (const t of trades) {
    if (!t.settled || t.outcome==='push') continue;
    const raw = t.myProbability ?? t.entryPrice ?? 50;
    const adj = t.side==='YES' ? raw : 100-raw;
    const key = Math.min(90,Math.max(10,Math.round(adj/10)*10));
    bins[key].total++;
    if (t.outcome==='win') bins[key].wins++;
  }
  const bKeys = Object.keys(bins);
  const actual = bKeys.map(b => bins[b].total>0 ? Math.round(bins[b].wins/bins[b].total*100) : null);
  const ideal  = bKeys.map(Number);
  destroyChart('cal');
  CH.cal = new Chart(document.getElementById('calibrationChart').getContext('2d'), {
    type:'bar',
    data:{
      labels: bKeys.map(b=>b+'%'),
      datasets:[
        { label:'Actual Win%', data:actual, backgroundColor:actual.map((v,i)=>v===null?'rgba(48,54,61,.3)':Math.abs(v-ideal[i])<=5?'rgba(88,166,255,.72)':v>ideal[i]?'rgba(63,185,80,.72)':'rgba(248,81,73,.72)'), borderRadius:3, order:1 },
        { label:'Perfect', data:ideal, type:'line', borderColor:'rgba(140,149,158,.4)', borderDash:[5,4], borderWidth:1.5, pointRadius:0, fill:false, order:0 },
      ],
    },
    options:{ ...chartOpts('%'), plugins:{ ...chartOpts('%').plugins, legend:{ display:true, labels:{ color:'#8b949e', font:{family:'monospace',size:10}, boxWidth:12 } } } },
  });
}

// ── SCANNER ────────────────────────────────────────────────────────────────────
function runScan() {
  const seed  = parseInt(document.getElementById('sc-seed').value) || 42;
  const limit = parseInt(document.getElementById('sc-limit').value) || 80;
  scanResults = scanMarkets(limit, seed);
  renderScanner();
}

function renderScanner() {
  const passedOnly = document.getElementById('sc-passed').checked;
  const cat        = document.getElementById('sc-category').value;
  const minEdge    = parseFloat(document.getElementById('sc-min-edge').value) || 0;

  let rows = [...scanResults];
  if (passedOnly) rows = rows.filter(r => r.passed_filters);
  if (cat)        rows = rows.filter(r => r.category === cat);
  rows = rows.filter(r => Math.abs(r.edge) >= minEdge);

  document.getElementById('sc-count').textContent = `${rows.length} of ${scanResults.length} markets`;

  // Summary metrics
  const passed = scanResults.filter(r=>r.passed_filters).length;
  const avgEdge = rows.length ? rows.reduce((s,r)=>s+r.edge,0)/rows.length : 0;
  const avgLiq  = rows.length ? rows.reduce((s,r)=>s+r.liquidity,0)/rows.length : 0;
  document.getElementById('sc-metrics').innerHTML = [
    { label:'Scanned',       val:scanResults.length, fmt:'int' },
    { label:'Passed Filters',val:passed,             fmt:'int' },
    { label:'Showing',       val:rows.length,         fmt:'int' },
    { label:'Avg Edge',      val:avgEdge*100,         fmt:'pct1' },
    { label:'Avg Liquidity', val:avgLiq,              fmt:'cash' },
  ].map(m=>`<div class="metric-card"><div class="metric-label">${m.label}</div><div class="metric-value">${fmtStat(m.val,m.fmt)}</div></div>`).join('');

  const tbody = document.getElementById('sc-tbody');
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:28px">No markets match current filters.</td></tr>`;
  } else {
    tbody.innerHTML = rows.map(r => {
      const edgeCls = r.edge>=.08?'pos':r.edge>=.03?'':'neg';
      const statusBadge = r.passed_filters
        ? `<span class="badge badge-pass">PASS</span>`
        : `<span class="badge badge-block" title="${esc(r.block_reason)}">BLOCKED</span>`;
      return `<tr>
        <td style="color:var(--muted);font-size:11px">${esc(r.market_id)}</td>
        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.title)}">${esc(r.title)}</td>
        <td><span class="badge badge-${r.category}">${r.category}</span></td>
        <td>${(r.implied_probability*100).toFixed(1)}%</td>
        <td>${(r.model_probability*100).toFixed(1)}%</td>
        <td class="${edgeCls}" style="font-weight:600">${r.edge>=0?'+':''}${(r.edge*100).toFixed(1)}%</td>
        <td>${(r.spread*100).toFixed(1)}%</td>
        <td>$${(r.liquidity/1000).toFixed(0)}k</td>
        <td>${statusBadge}</td>
      </tr>`;
    }).join('');
  }

  // Edge distribution histogram
  const edges = scanResults.map(r=>r.edge);
  const nBins = 20;
  const eMin = Math.min(...edges), eMax = Math.max(...edges);
  const bw = (eMax - eMin) / nBins;
  const hist = Array(nBins).fill(0);
  const histLabels = [];
  for (let i=0;i<nBins;i++) histLabels.push(((eMin+bw*(i+.5))*100).toFixed(1)+'%');
  edges.forEach(e => { const i=Math.min(nBins-1,Math.floor((e-eMin)/bw)); hist[i]++; });

  destroyChart('edgeDist');
  CH.edgeDist = new Chart(document.getElementById('edgeDistChart').getContext('2d'), {
    type:'bar',
    data:{ labels:histLabels, datasets:[{ data:hist, backgroundColor:histLabels.map((_,i)=>{const e=(eMin+bw*(i+.5))*100; return e>=8?'rgba(63,185,80,.72)':e>=3?'rgba(88,166,255,.72)':e<=-3?'rgba(248,81,73,.72)':'rgba(140,149,158,.4)';}), borderRadius:2 }] },
    options:{ ...chartOpts(''), plugins:{ ...chartOpts('').plugins, legend:{display:false} }, scales:{ ...chartOpts('').scales, y:{ ...chartOpts('').scales.y, ticks:{ ...chartOpts('').scales.y.ticks, callback:v=>v } } } },
  });
}

function fmtStat(v, fmt) {
  if (fmt==='int')  return String(v);
  if (fmt==='pct1') return (v>=0?'+':'')+v.toFixed(1)+'%';
  if (fmt==='cash') return '$'+(v/1000).toFixed(0)+'k';
  return v;
}

// ── TRADE LOG ──────────────────────────────────────────────────────────────────
function renderTradeLog() {
  const typeF    = document.getElementById('filter-type').value;
  const outcomeF = document.getElementById('filter-outcome').value;

  let filtered = [...trades].sort((a,b)=>new Date(b.datetime)-new Date(a.datetime));
  if (typeF)    filtered = filtered.filter(t => t.marketType===typeF || t.category===typeF);
  if (outcomeF==='open')  filtered = filtered.filter(t => !t.settled);
  else if (outcomeF)      filtered = filtered.filter(t => t.outcome===outcomeF);

  document.getElementById('trade-count').textContent = `${filtered.length} of ${trades.length} trades`;

  const openCount = trades.filter(t=>!t.settled).length;
  document.getElementById('settle-btn').textContent = `⚖️ Settle Open Trades (${openCount})`;

  const tbody = document.getElementById('trade-table-body');
  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="12" style="text-align:center;color:var(--muted);padding:32px">No trades match these filters.</td></tr>`;
    return;
  }
  tbody.innerHTML = filtered.map(t => {
    const dt = new Date(t.datetime);
    const pnl = t.pnl ?? null;
    const pnlStr = pnl!==null ? (pnl>=0?'+':'')+'$'+Math.abs(pnl).toFixed(2) : '—';
    const pnlCls = pnl!==null ? (pnl>=0?'pos':'neg') : 'muted';
    const edge = t.edge ?? (t.myProbability && t.entryPrice ? (t.myProbability-t.entryPrice)/100 : null);
    const edgeStr = edge!==null ? (edge>=0?'+':'')+(edge*100).toFixed(1)+'%' : '—';
    const outcome = t.settled ? t.outcome : 'open';
    const stake = t.stake ?? t.posSize ?? 0;
    return `<tr>
      <td style="white-space:nowrap;color:var(--muted)">${dt.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'2-digit'})} ${dt.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</td>
      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(t.market||t.title||'')}">${esc(t.market||t.title||'')}</td>
      <td><span class="badge badge-${t.marketType||t.category||'other'}">${t.marketType||t.category||'—'}</span></td>
      <td><span class="badge badge-${(t.side||'YES').toLowerCase()}">${t.side||'YES'}</span></td>
      <td>${t.entryPrice != null ? t.entryPrice+'%' : '—'}</td>
      <td style="color:var(--muted)">${t.myProbability != null ? t.myProbability+'%' : '—'}</td>
      <td style="color:var(--muted)">${edgeStr}</td>
      <td>$${(+stake).toFixed(2)}</td>
      <td class="${pnlCls}" style="font-weight:700">${pnlStr}</td>
      <td><span class="badge badge-${outcome}">${outcome}</span></td>
      <td style="max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)">${esc(t.notes||'—')}</td>
      <td><button class="btn-danger" onclick="handleDelete('${t.id}')" title="Delete">×</button></td>
    </tr>`;
  }).join('');
}

function handleDelete(id) {
  if (!confirm('Delete this trade?')) return;
  trades = deleteTrade(id);
  renderAll();
}

function confirmClear() {
  if (confirm('Delete ALL trade history? This cannot be undone.')) {
    saveTrades([]);
    trades = [];
    renderAll();
  }
}

// ── SETTLE PANEL ───────────────────────────────────────────────────────────────
function openSettlePanel() {
  const open = trades.filter(t => !t.settled);
  if (!open.length) { alert('No open trades to settle.'); return; }
  const panel = document.getElementById('settle-panel');
  const list  = document.getElementById('settle-list');

  list.innerHTML = open.map(t => {
    const stake = t.stake ?? t.posSize ?? 0;
    const ep    = t.entryPrice/100 || 0.5;
    const sd    = t.side||'YES';
    const winPnl  = sd==='YES' ? stake*(1-ep)/ep   : stake*ep/(1-ep);
    const lossPnl = -stake;
    return `<div class="settle-row">
      <div class="settle-market" title="${esc(t.market||t.title||'')}">${esc(t.market||t.title||'')} <span style="color:var(--muted);font-size:11px">· $${(+stake).toFixed(2)}</span></div>
      <select id="sout-${t.id}" onchange="updateSettlePnl('${t.id}',${winPnl.toFixed(2)},${lossPnl.toFixed(2)})">
        <option value="">—</option>
        <option value="win">Win</option>
        <option value="loss">Loss</option>
        <option value="push">Push</option>
      </select>
      <input type="number" id="spnl-${t.id}" step="0.01" placeholder="P/L ($)" value="">
      <span style="font-size:11px;color:var(--muted)">${esc(t.market_id||'')}</span>
    </div>`;
  }).join('');

  panel.style.display = 'block';
}

function updateSettlePnl(id, winPnl, lossPnl) {
  const outcome = document.getElementById(`sout-${id}`).value;
  const pnlEl   = document.getElementById(`spnl-${id}`);
  if (outcome==='win')  pnlEl.value = winPnl.toFixed(2);
  else if (outcome==='loss') pnlEl.value = lossPnl.toFixed(2);
  else if (outcome==='push') pnlEl.value = '0';
}

function batchSettle() {
  const open = trades.filter(t => !t.settled);
  let count = 0;
  for (const t of open) {
    const outEl = document.getElementById(`sout-${t.id}`);
    const pnlEl = document.getElementById(`spnl-${t.id}`);
    if (!outEl || !outEl.value) continue;
    trades = updateTrade(t.id, {
      outcome:    outEl.value,
      pnl:        parseFloat(pnlEl.value) || 0,
      settled:    true,
      settled_at: new Date().toISOString(),
    });
    count++;
  }
  document.getElementById('settle-panel').style.display = 'none';
  renderAll();
  if (count) alert(`Settled ${count} trade${count>1?'s':''}.`);
}

// ── ANALYTICS ──────────────────────────────────────────────────────────────────
function renderAnalytics(m) {
  m = m || calcMetrics(trades);
  const defs = [
    { label:'Settled Trades', val:m.settled,      fmt:'int',     cls:'' },
    { label:'Win Rate',       val:m.winRate*100,   fmt:'pct',     cls:m.winRate>=.5?'pos':'neg' },
    { label:'Total P/L',      val:m.totalPnl,     fmt:'dollar',  cls:m.totalPnl>=0?'pos':'neg' },
    { label:'Profit Factor',  val:m.profitFactor, fmt:'ratio',   cls:m.profitFactor>=1?'pos':'neg' },
    { label:'Max Drawdown',   val:m.maxDrawdown,  fmt:'ddollar', cls:'neg' },
    { label:'Avg Edge',       val:m.avgEdge*100,   fmt:'pct',     cls:m.avgEdge>0?'pos':'neg' },
  ];
  const el = document.getElementById('an-metrics');
  if (!el) return;
  el.innerHTML = defs.map(d=>
    `<div class="metric-card"><div class="metric-label">${d.label}</div><div class="metric-value ${d.cls}">${fmtVal(d.val,d.fmt)}</div></div>`
  ).join('');
  if (activeTab()==='analytics') renderAnalyticsCharts();
}

function renderAnalyticsCharts() {
  const settled = trades.filter(t=>t.settled).sort((a,b)=>new Date(a.datetime)-new Date(b.datetime));
  if (!settled.length) return;

  // Cumulative P/L
  let cum=0;
  const plLabels=[], plVals=[];
  for (const t of settled) { cum+=t.pnl||0; plLabels.push(plLabels.length+1); plVals.push(Math.round(cum*100)/100); }
  const c = cum>=0?'#3fb950':'#f85149';
  destroyChart('an_pl');
  CH.an_pl = new Chart(document.getElementById('an-plChart').getContext('2d'), {
    type:'line',
    data:{ labels:plLabels, datasets:[{ data:plVals, borderColor:c, backgroundColor:c+'14', borderWidth:2, pointRadius:0, fill:true, tension:.3 }] },
    options:{ ...chartOpts('$'), plugins:{...chartOpts('$').plugins, legend:{display:false}} },
  });

  // P/L by category
  const catMap={};
  for (const t of settled) { const k=t.marketType||t.category||'other'; catMap[k]=(catMap[k]||0)+(t.pnl||0); }
  const catKeys=Object.keys(catMap).sort((a,b)=>catMap[b]-catMap[a]);
  destroyChart('an_cat');
  CH.an_cat = new Chart(document.getElementById('an-catChart').getContext('2d'), {
    type:'bar',
    data:{ labels:catKeys, datasets:[{ data:catKeys.map(k=>Math.round(catMap[k]*100)/100), backgroundColor:catKeys.map(k=>catMap[k]>=0?'rgba(63,185,80,.72)':'rgba(248,81,73,.72)'), borderRadius:4 }] },
    options:{ ...chartOpts('$'), plugins:{...chartOpts('$').plugins, legend:{display:false}}, indexAxis:'y' },
  });

  // Win vs Loss bars
  const m = calcMetrics(trades);
  destroyChart('an_wl');
  CH.an_wl = new Chart(document.getElementById('an-winlossChart').getContext('2d'), {
    type:'bar',
    data:{ labels:['Avg Winner','Avg Loser'], datasets:[{ data:[m.avgWin, -m.avgLoss], backgroundColor:['rgba(63,185,80,.72)','rgba(248,81,73,.72)'], borderRadius:4 }] },
    options:{ ...chartOpts('$'), plugins:{...chartOpts('$').plugins, legend:{display:false}} },
  });

  // Win rate by category
  const wrMap={};
  for (const t of settled) {
    const k=t.marketType||t.category||'other';
    if (!wrMap[k]) wrMap[k]={w:0,n:0};
    wrMap[k].n++;
    if (t.outcome==='win') wrMap[k].w++;
  }
  const wrKeys=Object.keys(wrMap);
  const wrVals=wrKeys.map(k=>Math.round(wrMap[k].w/wrMap[k].n*100));
  destroyChart('an_wr');
  CH.an_wr = new Chart(document.getElementById('an-wrCatChart').getContext('2d'), {
    type:'bar',
    data:{ labels:wrKeys, datasets:[{ data:wrVals, backgroundColor:wrVals.map(v=>v>=55?'rgba(63,185,80,.72)':v>=45?'rgba(88,166,255,.72)':'rgba(248,81,73,.72)'), borderRadius:4 }] },
    options:{ ...chartOpts('%'), plugins:{...chartOpts('%').plugins, legend:{display:false}} },
  });
}

// ── MONTE CARLO ────────────────────────────────────────────────────────────────
function seedMCFromHistory() {
  const m = calcMetrics(trades);
  if (m.settled < 10) { alert('Need at least 10 settled trades to seed from history.'); return; }
  document.getElementById('mc-winrate').value = Math.round(m.winRate*100);
  document.getElementById('mc-avgwin').value  = m.avgWin.toFixed(2);
  document.getElementById('mc-avgloss').value = m.avgLoss.toFixed(2);
  runMC();
}

function runMC() {
  const c       = cfg();
  const winProb = (parseFloat(document.getElementById('mc-winrate').value)||55)/100;
  const avgWin  =  parseFloat(document.getElementById('mc-avgwin').value)  || 35;
  const avgLoss =  parseFloat(document.getElementById('mc-avgloss').value) || 25;
  const nTrades =  parseInt(document.getElementById('mc-ntrades').value)   || 100;
  const nPaths  =  parseInt(document.getElementById('mc-paths').value)     || 300;
  const seed    =  parseInt(document.getElementById('mc-seed').value)      || 99;

  const result = runMonteCarlo(c.bankroll, winProb, avgWin, avgLoss, nTrades, nPaths, seed);

  // EV
  const ev = winProb*avgWin - (1-winProb)*avgLoss;
  const evCls = ev>0?'pos':'neg';
  document.getElementById('mc-ev').innerHTML =
    `EV/trade: <span class="${evCls}">${ev>=0?'+':''}$${ev.toFixed(2)}</span> &nbsp;·&nbsp; EV after ${nTrades} trades: <span class="${evCls}">${ev*nTrades>=0?'+':''}$${(ev*nTrades).toFixed(2)}</span>`;

  // Stats
  document.getElementById('mc-stats').innerHTML = [
    { label:'Median Final',   val:'$'+result.median.toLocaleString('en-US',{maximumFractionDigits:0}) },
    { label:'p5 (worst 5%)', val:'$'+result.p5.toLocaleString('en-US',{maximumFractionDigits:0}) },
    { label:'p95 (best 5%)', val:'$'+result.p95.toLocaleString('en-US',{maximumFractionDigits:0}) },
    { label:'Ruin Rate (<10%)',val:(result.ruinRate*100).toFixed(1)+'%' },
    { label:'2× Rate',        val:(result.doubleRate*100).toFixed(1)+'%' },
    { label:'Paths',           val:nPaths },
  ].map(s=>`<div><div class="r-label">${s.label}</div><div class="r-value">${s.val}</div></div>`).join('');

  // Chart
  const labels = Array.from({length:nTrades+1},(_,i)=>i);
  destroyChart('mc');
  CH.mc = new Chart(document.getElementById('mcChart').getContext('2d'), {
    type:'line',
    data:{
      labels,
      datasets:[
        { label:'p5',  data:result.bands.p5,  borderColor:'rgba(248,81,73,.5)',  borderWidth:1, pointRadius:0, fill:false },
        { label:'p25', data:result.bands.p25, borderColor:'rgba(248,81,73,.3)',  borderWidth:1, pointRadius:0, fill:'-1', backgroundColor:'rgba(248,81,73,.04)' },
        { label:'p50', data:result.bands.p50, borderColor:'rgba(88,166,255,.9)', borderWidth:2, pointRadius:0, fill:false },
        { label:'p75', data:result.bands.p75, borderColor:'rgba(63,185,80,.3)',  borderWidth:1, pointRadius:0, fill:'+1', backgroundColor:'rgba(63,185,80,.04)' },
        { label:'p95', data:result.bands.p95, borderColor:'rgba(63,185,80,.5)',  borderWidth:1, pointRadius:0, fill:false },
      ],
    },
    options:{
      responsive:true, maintainAspectRatio:true, animation:{duration:200},
      scales:{
        x:{ ticks:{color:'#8b949e',font:{family:'monospace',size:10},maxTicksLimit:10}, grid:{color:'rgba(48,54,61,.35)'} },
        y:{ ticks:{color:'#8b949e',font:{family:'monospace',size:10},callback:v=>'$'+v.toLocaleString('en-US',{maximumFractionDigits:0})}, grid:{color:'rgba(48,54,61,.35)'} },
      },
      plugins:{
        legend:{ display:true, labels:{color:'#8b949e',font:{family:'monospace',size:10},boxWidth:12} },
        tooltip:{ backgroundColor:'#1c2128', titleColor:'#f0f6fc', bodyColor:'#c9d1d9', borderColor:'#30363d', borderWidth:1, callbacks:{ label:ctx=>`${ctx.dataset.label}: $${ctx.raw.toFixed(0)}` } },
      },
    },
  });
}

// ── RISK ENGINE ────────────────────────────────────────────────────────────────
function calcKelly() {
  const c     = cfg();
  const entry = (parseFloat(document.getElementById('ke-entry').value)||55)/100;
  const model = (parseFloat(document.getElementById('ke-model').value)||63)/100;
  const frac  = fracKelly(entry, model, c.kellyFrac, c.maxRisk, c.minEdge);
  const stake = c.bankroll * frac;
  const edge  = model - entry;
  const eCls  = edge>0?'pos':'neg';
  const fCls  = frac>0?'pos':'neg';

  document.getElementById('ke-results').innerHTML = `
    <div><div class="r-label">Edge</div><div class="r-value ${eCls}">${edge>=0?'+':''}${(edge*100).toFixed(1)}%</div></div>
    <div><div class="r-label">${(c.kellyFrac*100).toFixed(0)}% Kelly</div><div class="r-value ${fCls}">${(frac*100).toFixed(2)}%</div></div>
    <div><div class="r-label">Rec. Stake</div><div class="r-value ${fCls}">$${stake.toFixed(2)}</div></div>`;

  // Sizing recommendation note
  const adjEdge = edge*100;
  const note = adjEdge < 3
    ? '🔴 Skip — below noise floor'
    : adjEdge < 5  ? '🟡 Weak: 1/8 Kelly max'
    : adjEdge < 10 ? '🔵 Standard: 1/4 Kelly'
    : adjEdge < 15 ? '🟢 Strong: up to 1/2 Kelly'
    : '🟢 Fat pitch: 1/2 Kelly (hard cap)';
  document.getElementById('ke-note').innerHTML = note;
  checkGuardrails();
}

function checkGuardrails() {
  const c     = cfg();
  const stake = parseFloat(document.getElementById('ke-test-stake').value) || 150;
  const msgs  = [];

  if (stake > c.bankroll*0.05) msgs.push({ text:`🚫 Stake $${stake.toFixed(2)} exceeds 5% cap ($${(c.bankroll*.05).toFixed(2)})`, t:'error' });

  const settled = trades.filter(t=>t.settled);
  if (settled.length >= 3) {
    const last3 = settled.slice(-3).map(t=>t.outcome);
    if (last3.every(o=>o==='loss')) msgs.push({ text:'⚠️ 3-loss streak — reduce size 50% until recovery', t:'warn' });
  }

  const today = new Date().toDateString();
  const todayPnl = settled.filter(t=>t.settled_at && new Date(t.settled_at).toDateString()===today).reduce((s,t)=>s+(t.pnl||0),0);
  if (todayPnl < -(c.bankroll*0.05)) msgs.push({ text:`🚫 Daily loss limit hit: $${todayPnl.toFixed(2)}`, t:'error' });

  if (!msgs.length) msgs.push({ text:'✅ All guardrails clear', t:'ok' });

  const el = document.getElementById('ke-guardrails');
  if (!el) return;
  el.innerHTML = msgs.map(m=>`<div style="padding:6px 10px;border-radius:4px;font-size:12px;margin-bottom:6px;background:${m.t==='error'?'rgba(248,81,73,.12)':m.t==='warn'?'rgba(210,153,34,.12)':'rgba(63,185,80,.1)'};color:${m.t==='error'?'var(--red)':m.t==='warn'?'var(--yellow)':'var(--green)'}">${m.text}</div>`).join('');
}

function calcEdge() {
  const myProb   = parseFloat(document.getElementById('edge-myprob').value)   || 0;
  const mktPrice = parseFloat(document.getElementById('edge-mktprice').value)  || 0;
  const spread   = parseFloat(document.getElementById('edge-spread').value)    || 0;
  const fees     = parseFloat(document.getElementById('edge-fees').value)      || 0;
  const raw  = myProb - mktPrice;
  const adj  = raw - spread/2 - fees;
  const rCls = raw>0?'pos':raw<0?'neg':'';
  const aCls = adj>0?'pos':adj<0?'neg':'';
  const rec  = adj<3?'<span class="neg">Skip</span>':adj<5?'<span style="color:var(--yellow)">1/8 Kelly</span>':adj<10?'<span class="pos">1/4 Kelly</span>':adj<15?'<span class="pos">1/2 Kelly</span>':'<span class="pos">1/2 Kelly (cap)</span>';
  document.getElementById('edge-results').innerHTML = `
    <div><div class="r-label">Raw Edge</div><div class="r-value ${rCls}">${raw>=0?'+':''}${raw.toFixed(1)}%</div></div>
    <div><div class="r-label">Adjusted Edge</div><div class="r-value ${aCls}">${adj>=0?'+':''}${adj.toFixed(1)}%</div></div>
    <div><div class="r-label">EV / $100</div><div class="r-value ${aCls}">${adj>=0?'+':''}$${adj.toFixed(2)}</div></div>
    <div class="r-note" style="grid-column:1/-1"><span style="color:var(--muted)">Sizing: </span>${rec}</div>`;
}

// ── RECOMMENDATIONS ────────────────────────────────────────────────────────────
function renderRecs() {
  const c = cfg();
  if (!scanResults.length) {
    document.getElementById('recs-list').innerHTML = '<div style="color:var(--muted);padding:32px;text-align:center">Run the Scanner tab first to generate recommendations.</div>';
    return;
  }

  const m = calcMetrics(trades);
  document.getElementById('recs-metrics').innerHTML = [
    { label:'Bankroll',    val:'$'+(c.bankroll+m.totalPnl).toLocaleString('en-US',{maximumFractionDigits:2}) },
    { label:'Win Rate',    val:m.settled ? (m.winRate*100).toFixed(1)+'%' : '—' },
    { label:'Avg Edge',    val:m.total ? (m.avgEdge*100).toFixed(1)+'%' : '—' },
    { label:'Open Trades', val:m.open },
  ].map(s=>`<div class="metric-card"><div class="metric-label">${s.label}</div><div class="metric-value">${s.val}</div></div>`).join('');

  const top = scanResults
    .filter(r => r.passed_filters && r.adj_edge > c.minEdge)
    .sort((a,b) => b.adj_edge - a.adj_edge)
    .slice(0, 8);

  if (!top.length) {
    document.getElementById('recs-list').innerHTML = '<div style="color:var(--muted);padding:32px;text-align:center">No markets cleared all filters. Lower the Min Edge threshold or rescan.</div>';
    return;
  }

  document.getElementById('recs-list').innerHTML = top.map(r => {
    const adjPct  = r.adj_edge*100;
    const stakeF  = fracKelly(r.implied_probability, r.model_probability, c.kellyFrac, c.maxRisk, c.minEdge);
    const stake   = (c.bankroll * stakeF).toFixed(2);
    const [tier, tierCls, pillCls] =
      adjPct>=15 ? ['FAT PITCH','tier-fat','tier-fat-pill']
      : adjPct>=10 ? ['STRONG','tier-strong','tier-strong-pill']
      : adjPct>=5  ? ['STANDARD','tier-standard','tier-std-pill']
      :              ['MARGINAL','tier-marginal','tier-marg-pill'];
    const edgeCls = r.adj_edge>=.08?'pos':r.adj_edge>=.05?'':'neg';
    return `<div class="rec-card ${tierCls}">
      <div class="rec-header">
        <div>
          <div class="rec-title">${esc(r.title)}</div>
          <div class="rec-meta">
            <span class="tier-badge ${pillCls}">${tier}</span>
            <span class="badge badge-${r.category}" style="font-size:9px">${r.category}</span>
            &nbsp;·&nbsp;Spread ${(r.spread*100).toFixed(1)}%
            &nbsp;·&nbsp;Liq $${(r.liquidity/1000).toFixed(0)}k
            &nbsp;·&nbsp;<span style="color:var(--muted)">${r.market_id}</span>
          </div>
        </div>
        <div class="rec-metric"><div class="rec-metric-label">Adj Edge</div><div class="rec-metric-value ${edgeCls}">${adjPct>=0?'+':''}${adjPct.toFixed(1)}%</div></div>
        <div class="rec-metric"><div class="rec-metric-label">Mkt Price</div><div class="rec-metric-value">${(r.implied_probability*100).toFixed(1)}%</div></div>
        <div class="rec-metric"><div class="rec-metric-label">Model Est.</div><div class="rec-metric-value">${(r.model_probability*100).toFixed(1)}%</div></div>
        <div class="rec-metric"><div class="rec-metric-label">Rec Stake</div><div class="rec-metric-value pos">$${stake}</div></div>
      </div>
    </div>`;
  }).join('');
}

// ── MODAL ──────────────────────────────────────────────────────────────────────
function openModal() {
  document.getElementById('trade-modal').classList.add('open');
}
function closeModal() {
  document.getElementById('trade-modal').classList.remove('open');
}
function closeModalOverlay(e) {
  if (e.target===document.getElementById('trade-modal')) closeModal();
}
function setDefaultDatetime() {
  const now = new Date();
  const local = new Date(now.getTime()-now.getTimezoneOffset()*60000);
  document.getElementById('f-datetime').value = local.toISOString().slice(0,16);
}

function updateModalKelly() {
  const c     = cfg();
  const entry = (parseFloat(document.getElementById('f-entry').value)||0)/100;
  const model = (parseFloat(document.getElementById('f-myprob').value)||0)/100;
  if (!entry || !model) return;
  const frac  = fracKelly(entry, model, c.kellyFrac, c.maxRisk, c.minEdge);
  const stake = (c.bankroll*frac).toFixed(2);
  document.getElementById('f-kelly-hint').textContent = `Kelly rec: $${stake}`;

  // Guardrail in modal
  const msgs=[];
  if (+stake > c.bankroll*.05) msgs.push('🚫 Exceeds 5% cap');
  const settled=trades.filter(t=>t.settled);
  if (settled.length>=3&&settled.slice(-3).every(t=>t.outcome==='loss')) msgs.push('⚠️ 3-loss streak');
  document.getElementById('f-guardrail').innerHTML = msgs.length
    ? msgs.map(m=>`<div style="color:var(--red)">${m}</div>`).join('')
    : '<div style="color:var(--green)">✅ Guardrails clear</div>';
}

function submitTrade() {
  const market = document.getElementById('f-market').value.trim();
  const entry  = document.getElementById('f-entry').value;
  const size   = document.getElementById('f-size').value;
  if (!market)  { alert('Enter a market description.'); return; }
  if (!entry)   { alert('Enter the entry price.'); return; }
  if (!size)    { alert('Enter the stake.'); return; }

  const myProb  = document.getElementById('f-myprob').value;
  const pnlRaw  = document.getElementById('f-pnl').value;
  const outcome = document.getElementById('f-outcome').value;
  const entryN  = parseFloat(entry);
  const myProbN = myProb ? parseFloat(myProb) : entryN;
  const pnl     = pnlRaw !== '' ? parseFloat(pnlRaw) : null;
  const settled = outcome !== 'open';
  const dtRaw   = document.getElementById('f-datetime').value;

  trades = addTrade({
    datetime:      dtRaw ? new Date(dtRaw).toISOString() : new Date().toISOString(),
    market,
    marketType:    document.getElementById('f-type').value,
    side:          document.getElementById('f-side').value,
    entryPrice:    entryN,
    myProbability: myProbN,
    edge:          (myProbN - entryN) / 100,
    stake:         parseFloat(size),
    outcome:       settled ? outcome : null,
    pnl:           pnl,
    settled,
    settled_at:    settled ? new Date().toISOString() : null,
    notes:         document.getElementById('f-notes').value.trim(),
  });

  closeModal();
  ['f-market','f-entry','f-myprob','f-size','f-pnl','f-notes','f-kelly-hint','f-guardrail'].forEach(id=>{
    const el=document.getElementById(id); if(el) el.value!==undefined?el.value='':el.textContent='';
  });
  document.getElementById('f-outcome').value='open';
  setDefaultDatetime();
  renderAll();
}

// ── EXPORT ─────────────────────────────────────────────────────────────────────
function exportData(fmt) {
  const date = new Date().toISOString().slice(0,10);
  let content, filename, mime;
  if (fmt==='csv') {
    content=toCSV(trades); filename=`trademet_${date}.csv`; mime='text/csv';
  } else {
    content=JSON.stringify(trades,null,2); filename=`trademet_${date}.json`; mime='application/json';
  }
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([content],{type:mime}));
  a.download=filename; a.click();
  URL.revokeObjectURL(a.href);
}

// ── CHART HELPERS ──────────────────────────────────────────────────────────────
function chartOpts(unit) {
  return {
    responsive:true, maintainAspectRatio:true, animation:{duration:220},
    scales:{
      x:{ ticks:{color:'#8b949e',font:{family:'monospace',size:10},maxTicksLimit:10}, grid:{color:'rgba(48,54,61,.35)'} },
      y:{ ticks:{color:'#8b949e',font:{family:'monospace',size:10},callback:v=>unit==='$'?'$'+v.toFixed(0):unit==='%'?v+'%':v}, grid:{color:'rgba(48,54,61,.35)'} },
    },
    plugins:{
      legend:{display:false},
      tooltip:{ backgroundColor:'#1c2128', titleColor:'#f0f6fc', bodyColor:'#c9d1d9', borderColor:'#30363d', borderWidth:1, titleFont:{family:'monospace',size:11}, bodyFont:{family:'monospace',size:11},
        callbacks:{ label:ctx=>unit==='$'?`$${(ctx.raw??0).toFixed(2)}`:unit==='%'?`${(ctx.raw??0).toFixed(1)}%`:ctx.raw } },
    },
  };
}

function destroyChart(key) {
  if (CH[key]) { CH[key].destroy(); delete CH[key]; }
}

function esc(str) {
  return String(str||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
