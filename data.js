// data.js  —  persistence, scanner, Monte Carlo

const STORAGE_KEY = 'tradingos_v2';

// ── SEEDED RNG (Mulberry32) ────────────────────────────────────────────────────
function mkRng(seed) {
  let s = seed >>> 0;
  const rand = () => {
    s = (s + 0x6D2B79F5) >>> 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 2 ** 32;
  };
  const normal = (mu = 0, sigma = 1) => {
    let u;
    do { u = rand(); } while (u === 0);
    const z = Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rand());
    return mu + sigma * z;
  };
  // Beta(a,b) via normal approximation (accurate for a=b=2.5 used in scanner)
  const beta = (a, b) => {
    const mu = a / (a + b);
    const va = (a * b) / ((a + b) ** 2 * (a + b + 1));
    return Math.max(0.02, Math.min(0.98, normal(mu, Math.sqrt(va))));
  };
  const lognormal = (mu, sigma) => Math.exp(normal(mu, sigma));
  const choice = (arr) => arr[Math.floor(rand() * arr.length)];
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  return { rand, normal, beta, lognormal, choice, clamp };
}

// ── SCANNER ────────────────────────────────────────────────────────────────────
const SCAN_CATEGORIES = ['politics', 'sports', 'economics', 'weather', 'crypto', 'culture'];

function scanMarkets(limit, seed) {
  const rng = mkRng(seed);
  const rows = [];

  for (let i = 0; i < limit; i++) {
    const implied   = rng.clamp(rng.beta(2.5, 2.5), 0.02, 0.98);
    const model     = rng.clamp(implied + rng.normal(0.035, 0.07), 0.01, 0.99);
    const liquidity = rng.lognormal(11.0, 0.65);
    const volume    = liquidity * rng.clamp(rng.rand(), 0.08, 0.55);
    const spread    = rng.clamp(rng.normal(0.025, 0.012), 0.005, 0.08);
    const category  = rng.choice(SCAN_CATEGORIES);
    const edge      = model - implied;

    const blocks = [];
    if (Math.abs(edge) < 0.03)  blocks.push('edge below threshold');
    if (liquidity < 25_000)     blocks.push('liquidity below floor');
    if (spread > 0.05)          blocks.push('spread too wide');

    rows.push({
      market_id:          `MKT-${seed}-${String(i).padStart(4,'0')}`,
      title:              `${category.charAt(0).toUpperCase()+category.slice(1)} contract #${i+1}`,
      category,
      implied_probability: implied,
      model_probability:   model,
      edge,
      adj_edge:            edge - spread / 2,
      liquidity,
      volume_24h:          volume,
      spread,
      cluster_id:          Math.floor(i / 8),
      passed_filters:      blocks.length === 0,
      block_reason:        blocks.length ? blocks.join('; ') : 'PASS',
    });
  }

  return rows.sort((a, b) => b.edge - a.edge);
}

// ── MONTE CARLO ────────────────────────────────────────────────────────────────
function runMonteCarlo(bankroll, winProb, avgWin, avgLoss, nTrades, nPaths, seed) {
  const rng = mkRng(seed);
  const paths = [];

  for (let p = 0; p < nPaths; p++) {
    const path = [bankroll];
    let bal = bankroll;
    for (let t = 0; t < nTrades; t++) {
      bal = Math.max(0, bal + (rng.rand() < winProb ? avgWin : -avgLoss));
      path.push(bal);
    }
    paths.push(path);
  }

  // Compute percentile bands
  const bands = { p5:[], p25:[], p50:[], p75:[], p95:[] };
  for (let t = 0; t <= nTrades; t++) {
    const col = paths.map(p => p[t]).sort((a,b) => a-b);
    const pct = (q) => {
      const idx = q * (col.length - 1);
      const lo = Math.floor(idx), hi = Math.ceil(idx);
      return col[lo] + (col[hi] - col[lo]) * (idx - lo);
    };
    bands.p5.push(pct(0.05));
    bands.p25.push(pct(0.25));
    bands.p50.push(pct(0.50));
    bands.p75.push(pct(0.75));
    bands.p95.push(pct(0.95));
  }

  const finals = paths.map(p => p[nTrades]);
  return {
    bands,
    finals,
    median:  finals.slice().sort((a,b)=>a-b)[Math.floor(finals.length/2)],
    p5:      bands.p5[nTrades],
    p95:     bands.p95[nTrades],
    ruinRate: finals.filter(f => f < bankroll * 0.1).length / finals.length,
    doubleRate: finals.filter(f => f > bankroll * 2).length / finals.length,
  };
}

// ── TRADE CRUD ─────────────────────────────────────────────────────────────────
function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function loadTrades() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (_) {}
  // Migrate from v1
  try {
    const old = localStorage.getItem('tradingos_v1');
    if (old) {
      const trades = JSON.parse(old).map(t => ({
        ...t,
        stake:    t.stake ?? t.posSize ?? 0,
        settled:  t.outcome && t.outcome !== 'open',
        settled_at: t.settled_at ?? null,
      }));
      saveTrades(trades);
      return trades;
    }
  } catch (_) {}
  return [];
}

function saveTrades(trades) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(trades));
}

function addTrade(trade) {
  const trades = loadTrades();
  trades.push({ ...trade, id: uid() });
  trades.sort((a, b) => new Date(a.datetime) - new Date(b.datetime));
  saveTrades(trades);
  return trades;
}

function updateTrade(id, updates) {
  const trades = loadTrades().map(t => t.id === id ? { ...t, ...updates } : t);
  saveTrades(trades);
  return trades;
}

function deleteTrade(id) {
  const trades = loadTrades().filter(t => t.id !== id);
  saveTrades(trades);
  return trades;
}

// ── METRICS ────────────────────────────────────────────────────────────────────
function calcMetrics(trades) {
  const settled  = trades.filter(t => t.settled);
  const wins     = settled.filter(t => t.outcome === 'win');
  const losses   = settled.filter(t => t.outcome === 'loss');
  const nonPush  = settled.filter(t => t.outcome !== 'push');
  const pnls     = settled.map(t => t.pnl || 0);

  const totalPnl  = pnls.reduce((s,v) => s+v, 0);
  const grossWin  = wins.reduce((s,t) => s+(t.pnl||0), 0);
  const grossLoss = Math.abs(losses.reduce((s,t) => s+(t.pnl||0), 0));
  const winRate   = nonPush.length ? wins.length / nonPush.length : 0;

  // Drawdown
  let peak=0, maxDD=0, cum=0;
  for (const p of pnls) { cum+=p; if(cum>peak) peak=cum; maxDD=Math.max(maxDD,peak-cum); }

  // Streaks
  let curStreak=0, longestWin=0, tmpW=0;
  if (nonPush.length) {
    const lastOut = nonPush[nonPush.length-1].outcome;
    let i = nonPush.length-1;
    while (i>=0 && nonPush[i].outcome===lastOut) { curStreak++; i--; }
    if (lastOut==='loss') curStreak=-curStreak;
  }
  for (const t of nonPush) {
    if (t.outcome==='win') { tmpW++; longestWin=Math.max(longestWin,tmpW); }
    else tmpW=0;
  }

  const avgEdge = trades.length
    ? trades.reduce((s,t)=>s+(t.edge||0),0)/trades.length
    : 0;

  return {
    total:       trades.length,
    settled:     settled.length,
    open:        trades.filter(t => !t.settled).length,
    winRate,
    totalPnl,
    avgPnl:      settled.length ? totalPnl/settled.length : 0,
    profitFactor: grossLoss>0 ? grossWin/grossLoss : grossWin>0 ? Infinity : 0,
    maxDrawdown:  maxDD,
    bestTrade:    pnls.length ? Math.max(...pnls) : 0,
    worstTrade:   pnls.length ? Math.min(...pnls) : 0,
    avgWin:       wins.length ? grossWin/wins.length : 0,
    avgLoss:      losses.length ? grossLoss/losses.length : 0,
    curStreak,
    longestWin,
    avgEdge,
  };
}

// ── KELLY ──────────────────────────────────────────────────────────────────────
function fracKelly(entryPrice, modelProb, kellyFrac, maxRisk, minEdge) {
  const edge = modelProb - entryPrice;
  if (edge <= minEdge) return 0;
  const b = (1 - entryPrice) / entryPrice;
  const p = modelProb, q = 1 - p;
  const full = Math.max(0, (b*p - q) / b);
  return Math.min(kellyFrac * full, maxRisk);
}

// ── EXPORT ─────────────────────────────────────────────────────────────────────
function toCSV(trades) {
  const cols = ['datetime','market','marketType','side','entryPrice','myProbability',
                'stake','edge','pnl','outcome','settled','notes'];
  const hdrs = ['Date/Time','Market','Type','Side','Entry%','ModelProb%',
                'Stake($)','Edge%','P/L($)','Outcome','Settled','Notes'];
  const esc = v => (typeof v==='string' && (v.includes(',')||v.includes('"')))
    ? `"${v.replace(/"/g,'""')}"` : (v??'');
  return [hdrs.join(','), ...trades.map(t => cols.map(c=>esc(t[c])).join(','))].join('\n');
}
