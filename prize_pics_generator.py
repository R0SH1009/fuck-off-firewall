#!/usr/bin/env python3
"""
Prize Pics Trading OS
Reads playoff_stats.csv and generates an HTML trading card dashboard showing:
  - Past bet history (prop results across every tracked game)
  - Player trading cards with averages, grades, hit rates
  - New pick cards projecting recommended lines for the next game
"""

import pandas as pd
import json
import os

# ── Team config ──────────────────────────────────────────────────────────────
TEAMS = {
    "San Antonio Spurs": {
        "abbr": "SAS",
        "primary": "#C4CED4",
        "bg_gradient": "linear-gradient(150deg, #0b0b14 0%, #1a1a2e 55%, #252535 100%)",
        "glow": "rgba(196,206,212,0.35)",
        "border": "#C4CED4",
    },
    "New York Knicks": {
        "abbr": "NYK",
        "primary": "#F58426",
        "bg_gradient": "linear-gradient(150deg, #001e5c 0%, #003a9e 55%, #c96510 100%)",
        "glow": "rgba(245,132,38,0.45)",
        "border": "#F58426",
    },
}
_DEFAULT_TEAM = {
    "abbr": "NBA",
    "primary": "#888",
    "bg_gradient": "linear-gradient(150deg,#111,#333)",
    "glow": "rgba(136,136,136,0.2)",
    "border": "#555",
}


def tcfg(team, key):
    return TEAMS.get(team, _DEFAULT_TEAM).get(key, _DEFAULT_TEAM[key])


# ── Grades ───────────────────────────────────────────────────────────────────
def compute_grade(pts, reb, ast):
    score = pts * 1.0 + reb * 0.7 + ast * 0.8
    if score >= 32:
        return "S+", "#FFD700", "#2a1f00"
    if score >= 25:
        return "S", "#FFD700", "#2a1f00"
    if score >= 19:
        return "A+", "#00FF88", "#002211"
    if score >= 14:
        return "A", "#00CC66", "#001a0e"
    if score >= 10:
        return "B+", "#4488FF", "#001133"
    if score >= 7:
        return "B", "#2266CC", "#000d22"
    return "C", "#888888", "#1a1a1a"


# ── Trend ────────────────────────────────────────────────────────────────────
def compute_trend(games):
    if len(games) < 2:
        return "STEADY", "→", "#aaaaaa"
    latest = games[0]["pts"]
    avg = sum(g["pts"] for g in games) / len(games)
    diff = latest - avg
    if diff >= 5:
        return "HOT", "↑", "#ff6b35"
    if diff <= -5:
        return "COLD", "↓", "#4488ff"
    return "STEADY", "→", "#aaaaaa"


# ── Prop lines ────────────────────────────────────────────────────────────────
def snap_half(v):
    return round(v * 2) / 2


def gen_lines(avg_pts, avg_reb, avg_ast):
    lines = {"pts": snap_half(max(0.5, avg_pts - 2.5))}
    if avg_reb >= 3.5:
        lines["reb"] = snap_half(max(0.5, avg_reb - 1.5))
    if avg_ast >= 2.5:
        lines["ast"] = snap_half(max(0.5, avg_ast - 1.5))
    return lines


def hit_rate(games, stat, line):
    if not games:
        return 0
    return round(sum(1 for g in games if g[stat] > line) / len(games) * 100)


def hr_color(pct):
    if pct >= 75:
        return "#00ff88"
    if pct >= 50:
        return "#FFD700"
    return "#ff4455"


# ── Data loading ──────────────────────────────────────────────────────────────
def load_players(filepath):
    df = pd.read_csv(filepath)
    df["Game_Date"] = pd.to_datetime(df["Game_Date"])

    players = {}
    for name, grp in df.groupby("Player"):
        grp_s = grp.sort_values("Game_Date", ascending=False)
        team = grp_s["Team"].iloc[0]

        games = []
        for _, r in grp_s.iterrows():
            games.append(
                {
                    "date": r["Game_Date"].strftime("%b %d"),
                    "game": r["Game"],
                    "opponent": r["Opponent"],
                    "outcome": r["Game_Outcome"],
                    "pts": int(r["PTS"]),
                    "ast": int(r["AST"]),
                    "reb": int(r["REB"]),
                    "min": int(r["MIN"]),
                    "pf": int(r["PF"]),
                    "half_notes": str(r["1st_Half_Notes"]),
                    "win": str(r["Game_Outcome"]).startswith("W"),
                }
            )

        avg_pts = round(grp["PTS"].mean(), 1)
        avg_reb = round(grp["REB"].mean(), 1)
        avg_ast = round(grp["AST"].mean(), 1)
        avg_min = round(grp["MIN"].mean(), 1)

        lines = gen_lines(avg_pts, avg_reb, avg_ast)
        grade, grade_color, grade_bg = compute_grade(avg_pts, avg_reb, avg_ast)
        trend_label, trend_arrow, trend_color = compute_trend(games)

        # Last-game sparkline (up to 5 most recent)
        spark = [g["pts"] for g in games[:5]]

        players[name] = {
            "name": name,
            "team": team,
            "games": games,
            "avg_pts": avg_pts,
            "avg_reb": avg_reb,
            "avg_ast": avg_ast,
            "avg_min": avg_min,
            "game_count": len(games),
            "lines": lines,
            "grade": grade,
            "grade_color": grade_color,
            "grade_bg": grade_bg,
            "trend": trend_label,
            "trend_arrow": trend_arrow,
            "trend_color": trend_color,
            "spark": spark,
            "hit_pts": hit_rate(games, "pts", lines["pts"]),
            "hit_reb": hit_rate(games, "reb", lines.get("reb", 9999)) if "reb" in lines else None,
            "hit_ast": hit_rate(games, "ast", lines.get("ast", 9999)) if "ast" in lines else None,
        }

    return players


# ── Bet simulation ────────────────────────────────────────────────────────────
def simulate_bets(players):
    bets = []
    bid = 0
    for p in players.values():
        for g in p["games"]:
            base = {
                "player": p["name"],
                "team": p["team"],
                "date": g["date"],
                "game_label": g["game"],
                "opponent": g["opponent"],
                "game_result": "W" if g["win"] else "L",
            }
            bets.append(
                {
                    **base,
                    "id": bid,
                    "prop": "PTS",
                    "line": p["lines"]["pts"],
                    "actual": g["pts"],
                    "hit": g["pts"] > p["lines"]["pts"],
                }
            )
            bid += 1
            if "reb" in p["lines"]:
                bets.append(
                    {
                        **base,
                        "id": bid,
                        "prop": "REB",
                        "line": p["lines"]["reb"],
                        "actual": g["reb"],
                        "hit": g["reb"] > p["lines"]["reb"],
                    }
                )
                bid += 1
            if "ast" in p["lines"]:
                bets.append(
                    {
                        **base,
                        "id": bid,
                        "prop": "AST",
                        "line": p["lines"]["ast"],
                        "actual": g["ast"],
                        "hit": g["ast"] > p["lines"]["ast"],
                    }
                )
                bid += 1

    return sorted(bets, key=lambda b: (b["date"], b["player"]), reverse=True)


# ── HTML helpers ──────────────────────────────────────────────────────────────
def spark_html(spark, color):
    if not spark:
        return ""
    mx = max(spark) or 1
    bars = []
    for v in reversed(spark):
        h = max(4, round(v / mx * 32))
        bars.append(f'<div class="spark-bar" style="height:{h}px;background:{color}"></div>')
    return '<div class="sparkline">' + "".join(bars) + "</div>"


def hit_badge(pct, label, line, direction="OVER"):
    color = hr_color(pct)
    fmt_line = f"{line:.1f}" if line != int(line) else f"{int(line)}.0"
    return (
        f'<div class="prop-badge" style="border-color:{color}">'
        f'<span class="pb-prop">{label}</span>'
        f'<span class="pb-dir">{direction}</span>'
        f'<span class="pb-line" style="color:{color}">O {fmt_line}</span>'
        f'<span class="pb-rate" style="color:{color}">{pct}%</span>'
        f"</div>"
    )


def fmt_line(v):
    return f"{v:.1f}" if v != int(v) else f"{int(v)}.0"


# ── Card builders ─────────────────────────────────────────────────────────────
def bet_card_html(b):
    badge = (
        '<span class="result-badge hit">HIT ✓</span>'
        if b["hit"]
        else '<span class="result-badge miss">MISS ✗</span>'
    )
    team_color = tcfg(b["team"], "primary")
    abbr = tcfg(b["team"], "abbr")
    diff = b["actual"] - b["line"]
    diff_str = f"+{diff:.0f}" if diff > 0 else f"{diff:.0f}"
    diff_color = "#00ff88" if diff > 0 else "#ff4455"
    gr_class = "hit" if b["hit"] else "miss"

    return f"""
<div class="bet-card {gr_class}" data-prop="{b['prop']}" data-hit="{str(b['hit']).lower()}">
  <div class="bc-top">
    <span class="team-tag" style="color:{team_color};border-color:{team_color}">{abbr}</span>
    <span class="bc-date">{b['date']}</span>
    <span class="bc-game">{b['game_label']}</span>
  </div>
  <div class="bc-player">{b['player']}</div>
  <div class="bc-prop-row">
    <span class="bc-prop-type">{b['prop']}</span>
    <span class="bc-arrow">OVER</span>
    <span class="bc-line" style="color:{team_color}">O {fmt_line(b['line'])}</span>
  </div>
  <div class="bc-result-row">
    <span class="bc-actual">{b['actual']}</span>
    <span class="bc-diff" style="color:{diff_color}">{diff_str}</span>
    {badge}
  </div>
  <div class="bc-footer">vs {b['opponent']} &bull; {b['game_result']} {b['date']}</div>
</div>"""


def player_card_html(p):
    color = tcfg(p["team"], "primary")
    grad = tcfg(p["team"], "bg_gradient")
    glow = tcfg(p["team"], "glow")
    border = tcfg(p["team"], "border")
    abbr = tcfg(p["team"], "abbr")

    grade_badge = (
        f'<div class="grade-badge" style="background:{p["grade_bg"]};'
        f'color:{p["grade_color"]};border-color:{p["grade_color"]}">{p["grade"]}</div>'
    )

    props_html = hit_badge(p["hit_pts"], "PTS", p["lines"]["pts"])
    if p["hit_reb"] is not None:
        props_html += hit_badge(p["hit_reb"], "REB", p["lines"]["reb"])
    if p["hit_ast"] is not None:
        props_html += hit_badge(p["hit_ast"], "AST", p["lines"]["ast"])

    sparkline = spark_html(p["spark"], color)

    trend_html = (
        f'<span class="trend-label" style="color:{p["trend_color"]}">'
        f'{p["trend_arrow"]} {p["trend"]}</span>'
    )

    last_game = p["games"][0] if p["games"] else None
    last_note = ""
    if last_game:
        last_note = (
            f'<div class="half-notes">'
            f'<span class="hn-label">Last {last_game["game"]}:</span> '
            f'{last_game["half_notes"]}</div>'
        )

    return f"""
<div class="player-card" style="background:{grad};box-shadow:0 0 28px {glow};border-color:{border}">
  <div class="pc-header">
    {grade_badge}
    <div class="pc-team" style="color:{color}">{p['team'].upper()}</div>
    <div class="pc-abbr" style="color:{color}40">{abbr}</div>
  </div>
  <div class="pc-name">{p['name']}</div>
  <div class="pc-stats">
    <div class="pc-stat"><span class="sv">{p['avg_pts']}</span><span class="sl">PPG</span></div>
    <div class="pc-stat"><span class="sv">{p['avg_reb']}</span><span class="sl">RPG</span></div>
    <div class="pc-stat"><span class="sv">{p['avg_ast']}</span><span class="sl">APG</span></div>
    <div class="pc-stat"><span class="sv">{p['avg_min']}</span><span class="sl">MPG</span></div>
  </div>
  <div class="pc-props">{props_html}</div>
  <div class="pc-footer">
    {sparkline}
    <div class="pc-meta">
      {trend_html}
      <span class="games-played">{p['game_count']}G played</span>
    </div>
  </div>
  {last_note}
</div>"""


def new_pick_card_html(p):
    color = tcfg(p["team"], "primary")
    grad = tcfg(p["team"], "bg_gradient")
    glow = tcfg(p["team"], "glow")
    border = tcfg(p["team"], "border")
    abbr = tcfg(p["team"], "abbr")

    # Best pick = highest hit rate prop
    best_prop, best_line, best_hr = "PTS", p["lines"]["pts"], p["hit_pts"]
    if p["hit_reb"] is not None and p["hit_reb"] > best_hr:
        best_prop, best_line, best_hr = "REB", p["lines"]["reb"], p["hit_reb"]
    if p["hit_ast"] is not None and p["hit_ast"] > best_hr:
        best_prop, best_line, best_hr = "AST", p["lines"]["ast"], p["hit_ast"]

    pick_color = hr_color(best_hr)
    grade_badge = (
        f'<div class="grade-badge" style="background:{p["grade_bg"]};'
        f'color:{p["grade_color"]};border-color:{p["grade_color"]}">{p["grade"]}</div>'
    )

    last_game = p["games"][0] if p["games"] else {}
    last_pts = last_game.get("pts", "—")
    last_reb = last_game.get("reb", "—")
    last_ast = last_game.get("ast", "—")
    last_date = last_game.get("date", "—")
    last_opp = last_game.get("opponent", "—")

    return f"""
<div class="new-card" style="background:{grad};box-shadow:0 0 36px {glow};border-color:{border}">
  <div class="nc-ribbon" style="background:{pick_color}20;border-color:{pick_color}">FRESH PICK</div>
  <div class="pc-header">
    {grade_badge}
    <div class="pc-team" style="color:{color}">{p['team'].upper()}</div>
    <div class="pc-abbr" style="color:{color}40">{abbr}</div>
  </div>
  <div class="pc-name">{p['name']}</div>
  <div class="nc-avg-header">SEASON AVGS ({p['game_count']}G)</div>
  <div class="pc-stats">
    <div class="pc-stat"><span class="sv">{p['avg_pts']}</span><span class="sl">PPG</span></div>
    <div class="pc-stat"><span class="sv">{p['avg_reb']}</span><span class="sl">RPG</span></div>
    <div class="pc-stat"><span class="sv">{p['avg_ast']}</span><span class="sl">APG</span></div>
  </div>
  <div class="nc-last-header">LAST GAME vs {last_opp} ({last_date})</div>
  <div class="pc-stats">
    <div class="pc-stat"><span class="sv">{last_pts}</span><span class="sl">PTS</span></div>
    <div class="pc-stat"><span class="sv">{last_reb}</span><span class="sl">REB</span></div>
    <div class="pc-stat"><span class="sv">{last_ast}</span><span class="sl">AST</span></div>
  </div>
  <div class="nc-best-pick" style="border-color:{pick_color};background:{pick_color}15">
    <span class="nc-pick-label">BEST BET</span>
    <span class="nc-pick-prop" style="color:{pick_color}">{best_prop} OVER {fmt_line(best_line)}</span>
    <span class="nc-pick-rate" style="color:{pick_color}">{best_hr}% hit rate</span>
  </div>
  <div class="pc-footer">
    <span class="trend-label" style="color:{p['trend_color']}">{p['trend_arrow']} {p['trend']}</span>
  </div>
</div>"""


# ── Full HTML ─────────────────────────────────────────────────────────────────
CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: #08080f;
  color: #e8e8f0;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  min-height: 100vh;
  overflow-x: hidden;
}

/* ── Header ── */
.header {
  background: linear-gradient(90deg, #0e0e1a 0%, #12121f 100%);
  border-bottom: 1px solid #ffffff15;
  padding: 20px 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}
.header-brand { display: flex; flex-direction: column; }
.brand-title {
  font-size: 22px;
  font-weight: 900;
  letter-spacing: 3px;
  background: linear-gradient(90deg, #FFD700, #FF6B35, #FF4488);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  text-transform: uppercase;
}
.brand-sub { font-size: 11px; letter-spacing: 4px; color: #666; text-transform: uppercase; margin-top: 2px; }

.header-stats { display: flex; gap: 24px; flex-wrap: wrap; }
.hstat {
  display: flex; flex-direction: column; align-items: center;
  padding: 8px 16px; border-radius: 8px; background: #ffffff08;
  border: 1px solid #ffffff12;
}
.hstat-val { font-size: 26px; font-weight: 800; line-height: 1; }
.hstat-label { font-size: 10px; letter-spacing: 2px; color: #777; text-transform: uppercase; margin-top: 4px; }
.win-val { color: #00ff88; }
.loss-val { color: #ff4455; }
.rate-val { color: #FFD700; }

/* ── Tabs ── */
.tab-bar {
  display: flex; gap: 4px;
  padding: 20px 32px 0;
  border-bottom: 1px solid #ffffff10;
}
.tab-btn {
  padding: 10px 24px; border: none; background: transparent;
  color: #888; font-size: 13px; font-weight: 700;
  letter-spacing: 2px; text-transform: uppercase;
  cursor: pointer; border-bottom: 2px solid transparent;
  transition: all 0.2s; border-radius: 4px 4px 0 0;
}
.tab-btn:hover { color: #ccc; background: #ffffff08; }
.tab-btn.active { color: #FFD700; border-bottom-color: #FFD700; background: #FFD70010; }

/* ── Filter bar ── */
.filter-bar {
  display: flex; gap: 8px; flex-wrap: wrap;
  padding: 16px 32px;
}
.filter-btn {
  padding: 6px 16px; border-radius: 20px;
  border: 1px solid #333; background: transparent;
  color: #888; font-size: 12px; font-weight: 600;
  letter-spacing: 1px; text-transform: uppercase;
  cursor: pointer; transition: all 0.15s;
}
.filter-btn:hover { border-color: #666; color: #ccc; }
.filter-btn.active { border-color: #FFD700; color: #FFD700; background: #FFD70015; }

/* ── Sections ── */
.section { display: none; padding: 0 32px 40px; }
.section.active { display: block; }

/* ── Card grids ── */
.bet-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
  margin-top: 16px;
}
.player-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
  margin-top: 16px;
}
.new-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
  margin-top: 16px;
}

/* ── Bet card ── */
.bet-card {
  border-radius: 12px;
  padding: 16px;
  border: 1px solid #222;
  background: #0e0e1a;
  transition: transform 0.18s, box-shadow 0.18s;
  cursor: default;
}
.bet-card:hover { transform: translateY(-3px); }
.bet-card.hit { border-color: #00ff8830; box-shadow: 0 0 16px rgba(0,255,136,0.12); }
.bet-card.miss { border-color: #ff445530; box-shadow: 0 0 16px rgba(255,68,85,0.08); }

.bc-top { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.team-tag {
  font-size: 10px; font-weight: 800; letter-spacing: 1.5px;
  padding: 2px 7px; border-radius: 4px; border: 1px solid currentColor;
}
.bc-date { font-size: 11px; color: #666; margin-left: auto; }
.bc-game { font-size: 10px; color: #555; padding: 2px 6px; background: #ffffff08; border-radius: 4px; }

.bc-player { font-size: 15px; font-weight: 700; margin-bottom: 10px; line-height: 1.2; }

.bc-prop-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.bc-prop-type {
  font-size: 11px; font-weight: 800; letter-spacing: 2px;
  padding: 3px 8px; background: #ffffff0f; border-radius: 4px;
}
.bc-arrow { font-size: 10px; color: #666; }
.bc-line { font-size: 20px; font-weight: 900; letter-spacing: -0.5px; }

.bc-result-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.bc-actual { font-size: 32px; font-weight: 900; letter-spacing: -1px; }
.bc-diff { font-size: 14px; font-weight: 700; }

.result-badge {
  margin-left: auto; font-size: 11px; font-weight: 800;
  letter-spacing: 1px; padding: 5px 10px; border-radius: 6px;
}
.result-badge.hit { background: #00ff8820; color: #00ff88; border: 1px solid #00ff8840; }
.result-badge.miss { background: #ff445520; color: #ff6677; border: 1px solid #ff445540; }

.bc-footer { font-size: 11px; color: #555; }

/* ── Player card ── */
.player-card {
  border-radius: 16px; padding: 20px;
  border: 1px solid #333;
  transition: transform 0.2s, box-shadow 0.25s;
  cursor: default;
  position: relative; overflow: hidden;
}
.player-card:hover { transform: translateY(-4px) scale(1.01); }

.pc-header { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 12px; }
.pc-team { font-size: 10px; font-weight: 700; letter-spacing: 2px; line-height: 1.2; flex: 1; }
.pc-abbr { font-size: 42px; font-weight: 900; letter-spacing: -1px; position: absolute; right: 16px; top: 14px; }

.grade-badge {
  font-size: 16px; font-weight: 900;
  padding: 4px 10px; border-radius: 6px;
  border: 2px solid currentColor; min-width: 44px; text-align: center;
}

.pc-name {
  font-size: 20px; font-weight: 900; letter-spacing: -0.3px;
  margin-bottom: 16px; line-height: 1.1;
}

.pc-stats {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px;
  margin-bottom: 14px;
}
.pc-stat {
  display: flex; flex-direction: column; align-items: center;
  padding: 8px 4px; background: #00000025; border-radius: 6px;
}
.sv { font-size: 18px; font-weight: 800; line-height: 1; }
.sl { font-size: 9px; color: #888; letter-spacing: 1.5px; text-transform: uppercase; margin-top: 3px; }

.pc-props { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.prop-badge {
  display: flex; align-items: center; gap: 5px;
  padding: 5px 8px; border-radius: 6px;
  border: 1px solid #333; background: #00000020; font-size: 11px;
}
.pb-prop { font-weight: 800; letter-spacing: 1px; color: #aaa; }
.pb-dir { color: #666; font-size: 10px; }
.pb-line { font-weight: 700; }
.pb-rate { font-weight: 700; margin-left: 2px; }

.pc-footer {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-bottom: 8px;
}
.sparkline { display: flex; align-items: flex-end; gap: 3px; height: 36px; }
.spark-bar { width: 6px; border-radius: 3px 3px 0 0; min-height: 4px; opacity: 0.85; }

.pc-meta { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }
.trend-label { font-size: 12px; font-weight: 700; letter-spacing: 1px; }
.games-played { font-size: 10px; color: #666; }

.half-notes {
  font-size: 10px; color: #666; line-height: 1.4;
  padding: 8px 10px; background: #ffffff05; border-radius: 6px;
  border-left: 2px solid #ffffff15;
}
.hn-label { color: #888; font-weight: 700; }

/* ── New pick card ── */
.new-card {
  border-radius: 16px; padding: 20px;
  border: 1px solid #333;
  transition: transform 0.2s, box-shadow 0.25s;
  cursor: default; position: relative; overflow: hidden;
}
.new-card:hover { transform: translateY(-5px) scale(1.015); }

.nc-ribbon {
  font-size: 10px; font-weight: 800; letter-spacing: 3px;
  text-transform: uppercase; padding: 4px 12px;
  border: 1px solid; border-radius: 0 0 8px 0;
  position: absolute; top: 0; left: 0;
  border-top: none; border-left: none;
}

.nc-avg-header, .nc-last-header {
  font-size: 9px; font-weight: 700; letter-spacing: 2px;
  color: #666; text-transform: uppercase; margin-bottom: 6px; margin-top: 4px;
}

.nc-best-pick {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 12px; border-radius: 10px; border: 1px solid;
  margin: 12px 0; text-align: center;
}
.nc-pick-label { font-size: 9px; font-weight: 700; letter-spacing: 2.5px; color: #888; text-transform: uppercase; }
.nc-pick-prop { font-size: 18px; font-weight: 900; letter-spacing: 0.5px; }
.nc-pick-rate { font-size: 11px; font-weight: 600; }

/* ── Empty state ── */
.empty { color: #555; font-size: 14px; padding: 40px; text-align: center; }

/* ── Responsive ── */
@media (max-width: 600px) {
  .header { padding: 16px; }
  .tab-bar, .filter-bar, .section { padding-left: 16px; padding-right: 16px; }
  .bet-grid, .player-grid, .new-grid { grid-template-columns: 1fr; }
}
"""

JS = """
function showTab(id) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === id));
  document.querySelectorAll('.section').forEach(s => s.classList.toggle('active', s.id === id));
  document.querySelectorAll('.filter-bar').forEach(fb => {
    fb.style.display = (id === 'bets') ? 'flex' : 'none';
  });
}

function filterBets(type) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', b.dataset.filter === type));
  document.querySelectorAll('.bet-card').forEach(card => {
    const prop = card.dataset.prop;
    const hit  = card.dataset.hit;
    let show = true;
    if (type === 'PTS')   show = prop === 'PTS';
    if (type === 'REB')   show = prop === 'REB';
    if (type === 'AST')   show = prop === 'AST';
    if (type === 'hits')  show = hit === 'true';
    if (type === 'misses') show = hit === 'false';
    card.style.display = show ? '' : 'none';
  });
}

document.addEventListener('DOMContentLoaded', () => {
  showTab('bets');
  filterBets('all');
});
"""


def generate_html(players, bets, output_path):
    total = len(bets)
    wins = sum(1 for b in bets if b["hit"])
    losses = total - wins
    win_pct = round(wins / total * 100) if total else 0

    # ── Bet cards ──────────────────────────────────────────────────────────
    bet_cards = "\n".join(bet_card_html(b) for b in bets)

    # ── Player cards (sorted by avg_pts desc) ─────────────────────────────
    sorted_players = sorted(players.values(), key=lambda p: p["avg_pts"], reverse=True)
    player_cards = "\n".join(player_card_html(p) for p in sorted_players)

    # ── New pick cards (only players with ≥2 games, best hit rate first) ─
    eligible = [p for p in players.values() if p["game_count"] >= 2]
    eligible.sort(key=lambda p: max(
        p["hit_pts"],
        p["hit_reb"] or 0,
        p["hit_ast"] or 0
    ), reverse=True)
    new_cards = "\n".join(new_pick_card_html(p) for p in eligible)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Prize Pics Trading OS</title>
  <style>{CSS}</style>
</head>
<body>

<div class="header">
  <div class="header-brand">
    <div class="brand-title">Prize Pics Trading OS</div>
    <div class="brand-sub">NBA Playoffs &bull; 2026 &bull; Prop Card System</div>
  </div>
  <div class="header-stats">
    <div class="hstat"><span class="hstat-val">{total}</span><span class="hstat-label">Total Bets</span></div>
    <div class="hstat"><span class="hstat-val win-val">{wins}</span><span class="hstat-label">Hits</span></div>
    <div class="hstat"><span class="hstat-val loss-val">{losses}</span><span class="hstat-label">Misses</span></div>
    <div class="hstat"><span class="hstat-val rate-val">{win_pct}%</span><span class="hstat-label">Hit Rate</span></div>
    <div class="hstat"><span class="hstat-val">{len(players)}</span><span class="hstat-label">Players</span></div>
  </div>
</div>

<div class="tab-bar">
  <button class="tab-btn" data-tab="bets" onclick="showTab('bets')">Past Bets</button>
  <button class="tab-btn" data-tab="players" onclick="showTab('players')">Player Cards</button>
  <button class="tab-btn" data-tab="picks" onclick="showTab('picks')">New Picks</button>
</div>

<div class="filter-bar">
  <button class="filter-btn" data-filter="all"    onclick="filterBets('all')">All</button>
  <button class="filter-btn" data-filter="PTS"    onclick="filterBets('PTS')">PTS</button>
  <button class="filter-btn" data-filter="REB"    onclick="filterBets('REB')">REB</button>
  <button class="filter-btn" data-filter="AST"    onclick="filterBets('AST')">AST</button>
  <button class="filter-btn" data-filter="hits"   onclick="filterBets('hits')">Hits Only</button>
  <button class="filter-btn" data-filter="misses" onclick="filterBets('misses')">Misses Only</button>
</div>

<!-- PAST BETS -->
<div id="bets" class="section">
  <div class="bet-grid">{bet_cards}</div>
</div>

<!-- PLAYER CARDS -->
<div id="players" class="section">
  <div class="player-grid">{player_cards}</div>
</div>

<!-- NEW PICKS -->
<div id="picks" class="section">
  <div class="new-grid">{new_cards}</div>
</div>

<script>{JS}</script>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)

    print(f"Generated {output_path}")
    print(f"  Players: {len(players)}")
    print(f"  Bets:    {total}  ({wins} hits / {losses} misses, {win_pct}% rate)")
    print(f"  New pick cards: {len(eligible)}")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path   = os.path.join(script_dir, "playoff_stats.csv")
    html_path  = os.path.join(script_dir, "prize_pics_dashboard.html")

    players = load_players(csv_path)
    bets    = simulate_bets(players)
    generate_html(players, bets, html_path)
