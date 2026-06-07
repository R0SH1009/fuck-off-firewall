// data.js  —  persistence + seed data

const STORAGE_KEY = 'tradingos_v1';

function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

// ── SEED DATA ──────────────────────────────────────────────────────────────────
const SEED_MARKETS = [
  { market: 'BTC above $61,500 by EOD',            type: 'crypto'   },
  { market: 'BTC above $65,000 this week',          type: 'crypto'   },
  { market: 'ETH above $3,500 by Friday',           type: 'crypto'   },
  { market: 'ETH above $3,200 today',               type: 'crypto'   },
  { market: 'SOL above $150 EOD',                   type: 'crypto'   },
  { market: 'BTC 15-min candle closes above open',  type: 'crypto'   },
  { market: 'BTC dominance above 52% this week',    type: 'crypto'   },
  { market: 'Lakers win tonight',                   type: 'sports'   },
  { market: 'Chiefs cover -7.5 vs Raiders',         type: 'sports'   },
  { market: 'Celtics win Game 5',                   type: 'sports'   },
  { market: 'Warriors cover +4.5 vs Nuggets',       type: 'sports'   },
  { market: 'Yankees win tonight',                  type: 'sports'   },
  { market: 'Knicks advance to conference finals',  type: 'sports'   },
  { market: 'Spurs win the draft lottery',          type: 'sports'   },
  { market: 'NYC rain > 0.5 in tomorrow',           type: 'weather'  },
  { market: 'NYC max temp > 85°F today',            type: 'weather'  },
  { market: 'LA rain this week',                    type: 'weather'  },
  { market: 'Atlantic hurricane forms this week',   type: 'weather'  },
  { market: 'Chicago snow > 1 in this week',        type: 'weather'  },
  { market: 'Fed rate hike this meeting',           type: 'econ'     },
  { market: 'CPI above 3.5% this month',            type: 'econ'     },
  { market: 'Unemployment below 4% this month',     type: 'econ'     },
  { market: 'GDP Q1 positive growth confirmed',     type: 'econ'     },
  { market: 'NASDAQ closes up > 1% today',          type: 'econ'     },
  { market: 'Senate passes budget bill this week',  type: 'politics' },
  { market: 'Trump approval > 45%',                type: 'politics' },
  { market: 'Shutdown avoided before deadline',     type: 'politics' },
  { market: 'SCOTUS overturns EPA ruling',          type: 'politics' },
];

function generateSeedTrades() {
  const trades = [];
  const now = new Date('2026-06-07T12:00:00');
  const irng = (lo, hi) => Math.floor(Math.random() * (hi - lo + 1)) + lo;

  for (let i = 0; i < 50; i++) {
    const d = new Date(now);
    d.setDate(d.getDate() - irng(0, 89));
    d.setHours(irng(7, 22));
    d.setMinutes(irng(0, 59));

    const src       = SEED_MARKETS[irng(0, SEED_MARKETS.length - 1)];
    const side      = Math.random() < 0.5 ? 'YES' : 'NO';
    const entry     = irng(25, 75);           // market price at entry
    const edge      = irng(4, 14);            // estimated edge
    const myProb    = Math.min(95, Math.max(5, side === 'YES' ? entry + edge : entry - edge));
    const posSize   = irng(5, 30) * 10;       // $50–$300, multiples of $10

    // ~55% win rate
    const roll = Math.random();
    const outcome = roll < 0.04 ? 'push' : roll < 0.58 ? 'win' : 'loss';

    // Binary market P/L:
    //   posSize = face value of contracts (max payout)
    //   YES win:  gain (100 - entry)% of face
    //   YES loss: lose entry% of face
    //   NO  win:  gain entry% of face
    //   NO  loss: lose (100 - entry)% of face
    let pnl = 0;
    if (outcome === 'win') {
      pnl = side === 'YES'
        ? posSize * (100 - entry) / 100
        : posSize * entry / 100;
    } else if (outcome === 'loss') {
      pnl = side === 'YES'
        ? -(posSize * entry / 100)
        : -(posSize * (100 - entry) / 100);
    }
    pnl = Math.round(pnl * 100) / 100;

    trades.push({
      id:          uid(),
      datetime:    d.toISOString(),
      market:      src.market,
      marketType:  src.type,
      side,
      entryPrice:  entry,
      myProbability: myProb,
      posSize,
      outcome,
      pnl,
      notes: '',
    });
  }

  trades.sort((a, b) => new Date(a.datetime) - new Date(b.datetime));
  return trades;
}

// ── CRUD ───────────────────────────────────────────────────────────────────────
function loadTrades() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (_) {}
  const seed = generateSeedTrades();
  saveTrades(seed);
  return seed;
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

function deleteTrade(id) {
  const trades = loadTrades().filter(t => t.id !== id);
  saveTrades(trades);
  return trades;
}

// ── EXPORT ─────────────────────────────────────────────────────────────────────
function toCSV(trades) {
  const cols    = ['datetime','market','marketType','side','entryPrice','myProbability','posSize','pnl','outcome','notes'];
  const headers = ['Date/Time','Market','Type','Side','Entry%','MyEst%','Size($)','P/L($)','Outcome','Notes'];
  const esc     = v => (typeof v === 'string' && (v.includes(',') || v.includes('"')))
    ? `"${v.replace(/"/g,'""')}"`
    : v;
  const rows = trades.map(t => cols.map(c => esc(t[c] ?? '')).join(','));
  return [headers.join(','), ...rows].join('\n');
}
