#!/usr/bin/env python3
"""
Prize Pics Trading OS — Prize Picks Format
Generates a Prize Picks-style HTML dashboard from playoff stats.

Props covered: PTS · REB · AST · 3PM · STL · BLK · TO · Fantasy Score
Combos:        PRA · Pts+Reb · Pts+Ast · Reb+Ast · Blk+Stl
"""

import pandas as pd
import os

# ── Team config ───────────────────────────────────────────────────────────────
TEAMS = {
    "San Antonio Spurs": {
        "abbr": "SAS", "primary": "#C4CED4",
        "bg": "linear-gradient(150deg,#0b0b14 0%,#1a1a2e 60%,#252535 100%)",
        "glow": "rgba(196,206,212,0.3)", "border": "#C4CED4",
    },
    "New York Knicks": {
        "abbr": "NYK", "primary": "#F58426",
        "bg": "linear-gradient(150deg,#001e5c 0%,#003a9e 60%,#c96510 100%)",
        "glow": "rgba(245,132,38,0.4)", "border": "#F58426",
    },
}
_DT = {"abbr":"NBA","primary":"#888","bg":"linear-gradient(150deg,#111,#333)",
       "glow":"rgba(136,136,136,0.2)","border":"#555"}


def tc(team, k): return TEAMS.get(team, _DT).get(k, _DT[k])


# ── Fantasy Score formula (Prize Picks official) ──────────────────────────────
def fantasy_score(pts, reb, ast, blk, stl, to_):
    return round(pts*1 + reb*1.2 + ast*1.5 + blk*2 + stl*2 - to_*1, 1)


# ── Grade ─────────────────────────────────────────────────────────────────────
def grade(pts, reb, ast):
    s = pts + reb*0.7 + ast*0.8
    if s >= 32: return "S+", "#FFD700", "#2a1f00"
    if s >= 25: return "S",  "#FFD700", "#2a1f00"
    if s >= 19: return "A+", "#00FF88", "#002211"
    if s >= 14: return "A",  "#00CC66", "#001a0e"
    if s >= 10: return "B+", "#4488FF", "#001133"
    if s >= 7:  return "B",  "#2266CC", "#000d22"
    return "C", "#888888", "#1a1a1a"


# ── Trend ─────────────────────────────────────────────────────────────────────
def trend(games):
    if len(games) < 2: return "STEADY","→","#777"
    d = games[0]["pts"] - sum(g["pts"] for g in games)/len(games)
    if d >= 5:  return "HOT","↑","#ff6b35"
    if d <= -5: return "COLD","↓","#4488ff"
    return "STEADY","→","#777"


# ── Prop line helpers ─────────────────────────────────────────────────────────
def snap(v): return round(v * 2) / 2


def mk_prop(label, avg, offset, min_avg=0.0, show_more=True):
    """Return a prop dict or None if avg too low."""
    if avg < min_avg:
        return None
    line = snap(max(0.5, avg + offset))
    # Difficulty: compare line tightness to avg
    ratio = line / avg if avg > 0 else 0.5
    if ratio >= 0.93:   diff = "DEMON"
    elif ratio <= 0.76: diff = "GOBLIN"
    else:               diff = ""
    return {"label": label, "avg": avg, "line": line,
            "diff": diff, "more": show_more}


def build_props(ps):
    """Compute all Prize Picks-style props for a player's PS averages."""
    pts = ps["ps_pts"]; reb = ps["ps_reb"]; ast = ps["ps_ast"]
    tpm = ps["ps_3pm"]; stl = ps["ps_stl"]; blk = ps["ps_blk"]
    to_ = ps["ps_to"]
    fs  = fantasy_score(pts, reb, ast, blk, stl, to_)
    pra = round(pts + reb + ast, 1)
    pr  = round(pts + reb, 1)
    pa  = round(pts + ast, 1)
    ra  = round(reb + ast, 1)
    bs  = round(blk + stl, 1)

    props = []
    for p in [
        mk_prop("PTS",      pts,  -2.5, 3.0),
        mk_prop("REB",      reb,  -1.5, 2.5),
        mk_prop("AST",      ast,  -1.5, 2.0),
        mk_prop("3PM",      tpm,  -0.5, 0.5),
        mk_prop("STL",      stl,  -0.5, 0.3),
        mk_prop("BLK",      blk,  -0.5, 0.3),
        mk_prop("TO",       to_,  -0.5, 0.8,  show_more=False),
        mk_prop("Fantasy",  fs,   -4.5, 8.0),
        mk_prop("PRA",      pra,  -3.5, 8.0),
        mk_prop("Pts+Reb",  pr,   -3.0, 6.0),
        mk_prop("Pts+Ast",  pa,   -3.0, 6.0),
        mk_prop("Reb+Ast",  ra,   -1.5, 4.0),
        mk_prop("Blk+Stl",  bs,   -0.5, 0.8),
    ]:
        if p: props.append(p)
    return props, fs, pra, pr, pa, ra, bs


# ── Data loading ──────────────────────────────────────────────────────────────
def load_game_log(path):
    df = pd.read_csv(path)
    df["Game_Date"] = pd.to_datetime(df["Game_Date"])
    result = {}
    for name, grp in df.groupby("Player"):
        grp_s = grp.sort_values("Game_Date", ascending=False)
        games = []
        for _, r in grp_s.iterrows():
            games.append({
                "date": r["Game_Date"].strftime("%b %d"),
                "game": r["Game"], "opponent": r["Opponent"],
                "outcome": r["Game_Outcome"],
                "pts": int(r["PTS"]), "ast": int(r["AST"]),
                "reb": int(r["REB"]), "min": int(r["MIN"]),
                "half_notes": str(r["1st_Half_Notes"]),
                "win": str(r["Game_Outcome"]).startswith("W"),
            })
        result[name] = {
            "team":    grp_s["Team"].iloc[0],
            "games":   games,
            "log_pts": round(grp["PTS"].mean(), 1),
            "log_reb": round(grp["REB"].mean(), 1),
            "log_ast": round(grp["AST"].mean(), 1),
            "log_min": round(grp["MIN"].mean(), 1),
        }
    return result


def load_ps_avgs(path):
    df = pd.read_csv(path)
    result = {}
    for _, r in df.iterrows():
        result[str(r["Player"])] = {
            "team": str(r["Team"]), "position": str(r["Position"]),
            "ps_pts": float(r["PPG"]),  "ps_reb": float(r["RPG"]),
            "ps_ast": float(r["APG"]),  "ps_3pm": float(r["ThreePM"]),
            "ps_stl": float(r["STL"]),  "ps_blk": float(r["BLK"]),
            "ps_to":  float(r["TO"]),
        }
    return result


def build_players(gl, ps):
    players = {}
    for name in set(gl) | set(ps):
        g = gl.get(name, {})
        p = ps.get(name, {})
        games    = g.get("games", [])
        team     = p.get("team") or g.get("team", "?")
        has_ps   = bool(p)
        has_log  = bool(games)

        # Primary stats (PS preferred)
        pts = p.get("ps_pts", g.get("log_pts", 0.0))
        reb = p.get("ps_reb", g.get("log_reb", 0.0))
        ast = p.get("ps_ast", g.get("log_ast", 0.0))

        grd, gcol, gbg = grade(pts, reb, ast)
        trn, tarrow, tcol = trend(games) if has_log else ("—","—","#555")

        # Build props (needs PS data)
        props, fs, pra, pr, pa, ra, bs = (
            build_props(p) if has_ps else ([], 0, 0, 0, 0, 0, 0)
        )

        # Hit rates for PTS/REB/AST using PS-based lines
        lines = {pp["label"]: pp["line"] for pp in props}

        def hr(stat, key):
            line = lines.get(key)
            if line is None or not games: return None
            return round(sum(1 for gg in games if gg[stat] > line) / len(games) * 100)

        players[name] = {
            "name": name, "team": team,
            "position": p.get("position", "—"),
            "games": games, "game_count": len(games),
            "has_ps": has_ps, "has_log": has_log,
            # PS averages
            "ps_pts": p.get("ps_pts"), "ps_reb": p.get("ps_reb"),
            "ps_ast": p.get("ps_ast"), "ps_3pm": p.get("ps_3pm"),
            "ps_stl": p.get("ps_stl"), "ps_blk": p.get("ps_blk"),
            "ps_to":  p.get("ps_to"),
            "ps_fs":  fs, "ps_pra": pra, "ps_pr": pr,
            "ps_pa":  pa, "ps_ra":  ra,  "ps_bs": bs,
            # Game log sample
            "log_pts": g.get("log_pts"), "log_reb": g.get("log_reb"),
            "log_ast": g.get("log_ast"), "log_min": g.get("log_min"),
            # Primary refs
            "avg_pts": pts, "avg_reb": reb, "avg_ast": ast,
            # Card data
            "props":      props,
            "grade":      grd,  "grade_color": gcol, "grade_bg": gbg,
            "trend":      trn,  "trend_arrow": tarrow, "trend_color": tcol,
            "hit_pts": hr("pts","PTS"), "hit_reb": hr("reb","REB"),
            "hit_ast": hr("ast","AST"),
        }
    return players


# ── Bet simulation (game-log only, PTS/REB/AST) ───────────────────────────────
def simulate_bets(players):
    bets, bid = [], 0
    for p in players.values():
        if not p["has_log"]: continue
        lines = {pp["label"]: pp["line"] for pp in p["props"]}
        for g in p["games"]:
            base = {"player": p["name"], "team": p["team"],
                    "date": g["date"], "game_label": g["game"],
                    "opponent": g["opponent"],
                    "game_result": "W" if g["win"] else "L"}
            for stat_key, prop_label in [("pts","PTS"),("reb","REB"),("ast","AST")]:
                line = lines.get(prop_label)
                if line is None: continue
                bets.append({**base, "id": bid, "prop": prop_label,
                             "line": line, "actual": g[stat_key],
                             "hit": g[stat_key] > line})
                bid += 1
    return sorted(bets, key=lambda b: (b["date"], b["player"]), reverse=True)


# ── HTML helpers ──────────────────────────────────────────────────────────────
def fl(v):
    return f"{v:.1f}" if v != int(v) else f"{int(v)}.0"


def diff_tag(diff):
    if diff == "DEMON":
        return '<span class="diff-tag demon">DEMON</span>'
    if diff == "GOBLIN":
        return '<span class="diff-tag goblin">GOBLIN</span>'
    return ""


def prop_tile_html(pp, hit_rate=None, team_color="#888"):
    line_str = fl(pp["line"])
    more_label = "MORE" if pp["more"] else "LESS"
    more_cls   = "more-btn" if pp["more"] else "less-btn"
    if hit_rate is not None:
        rate_str = f"{hit_rate}%"
        rate_col = ("#00ff88" if hit_rate >= 75 else
                    "#FFD700" if hit_rate >= 50 else "#ff4455")
    else:
        rate_str = "PROJ"
        rate_col = "#666"

    return f"""<div class="prop-tile">
  <div class="pt-label">{pp['label']}</div>
  <div class="pt-line" style="color:{team_color}">{line_str}</div>
  <button class="{more_cls}">{more_label} <span style="color:{rate_col};font-size:9px">{rate_str}</span></button>
  {diff_tag(pp['diff'])}
</div>"""


def recent_boxes_html(games, line, stat_key, team_color):
    if not games: return ""
    boxes = []
    for g in games[:5]:
        val = g[stat_key]
        hit = val > line
        col = "#00ff88" if hit else "#ff4455"
        bg  = "#00ff8812" if hit else "#ff445512"
        boxes.append(
            f'<div class="rg-box" style="color:{col};border-color:{col}40;background:{bg}">'
            f'{val}</div>'
        )
    return "".join(boxes)


# ── Card builders ─────────────────────────────────────────────────────────────
def bet_card_html(b):
    color = tc(b["team"],"primary"); abbr = tc(b["team"],"abbr")
    diff  = b["actual"] - b["line"]
    dc    = "#00ff88" if diff > 0 else "#ff4455"
    ds    = f"+{diff:.0f}" if diff > 0 else f"{diff:.0f}"
    badge = ('<span class="result-badge hit">HIT ✓</span>'
             if b["hit"] else '<span class="result-badge miss">MISS ✗</span>')
    return f"""
<div class="bet-card {'hit' if b['hit'] else 'miss'}" data-prop="{b['prop']}" data-hit="{str(b['hit']).lower()}">
  <div class="bc-top">
    <span class="team-tag" style="color:{color};border-color:{color}">{abbr}</span>
    <span class="bc-date">{b['date']}</span>
    <span class="bc-game">{b['game_label']}</span>
  </div>
  <div class="bc-player">{b['player']}</div>
  <div class="bc-prop-row">
    <span class="bc-prop-type">{b['prop']}</span>
    <span class="bc-dir">{"MORE" if b['hit'] else "LESS"}</span>
    <span class="bc-line" style="color:{color}">O {fl(b['line'])}</span>
  </div>
  <div class="bc-result-row">
    <span class="bc-actual">{b['actual']}</span>
    <span class="bc-diff" style="color:{dc}">{ds}</span>
    {badge}
  </div>
  <div class="bc-footer">vs {b['opponent']} &bull; {b['game_result']} {b['date']}</div>
</div>"""


def player_card_html(p):
    color = tc(p["team"],"primary"); grad = tc(p["team"],"bg")
    glow  = tc(p["team"],"glow");   border = tc(p["team"],"border")
    abbr  = tc(p["team"],"abbr")

    # ── Header ────────────────────────────────────────────────────────────────
    grade_badge = (
        f'<div class="grade-badge" style="background:{p["grade_bg"]};'
        f'color:{p["grade_color"]};border-color:{p["grade_color"]}">{p["grade"]}</div>'
    )
    pos_tag = f'<span class="pos-tag" style="border-color:{color}40;color:{color}">{p["position"]}</span>'

    # ── Running stats strip ───────────────────────────────────────────────────
    chips = []
    def chip(v, label):
        if v is not None: chips.append(f'<span class="stat-chip">{v} <em>{label}</em></span>')

    if p["has_ps"]:
        chip(p["ps_pts"],  "PPG"); chip(p["ps_reb"],  "RPG"); chip(p["ps_ast"],  "APG")
        chip(p["ps_3pm"],  "3PM"); chip(p["ps_stl"],  "STL"); chip(p["ps_blk"],  "BLK")
        chip(p["ps_to"],   "TO");  chip(p["ps_fs"],   "FS");  chip(p["ps_pra"],  "PRA")
    stats_strip = f'<div class="stats-strip">{"".join(chips)}</div>' if chips else ""

    # ── Props grid ────────────────────────────────────────────────────────────
    hit_map = {"PTS": p["hit_pts"], "REB": p["hit_reb"], "AST": p["hit_ast"]}
    tiles = "".join(
        prop_tile_html(pp, hit_map.get(pp["label"]), color)
        for pp in p["props"]
    )
    props_section = (
        f'<div class="props-label">PRIZE PICKS LINES</div>'
        f'<div class="props-grid">{tiles}</div>'
    ) if tiles else '<div class="no-props">No PS data available</div>'

    # ── Recent games (PTS line) ───────────────────────────────────────────────
    pts_line = next((pp["line"] for pp in p["props"] if pp["label"] == "PTS"), None)
    recent_html = ""
    if p["games"] and pts_line is not None:
        boxes = recent_boxes_html(p["games"], pts_line, "pts", color)
        recent_html = (
            f'<div class="recent-header">'
            f'LAST {min(len(p["games"]),5)} GAMES · PTS (O {fl(pts_line)})'
            f'</div>'
            f'<div class="recent-boxes">{boxes}</div>'
        )

    # ── Last game note ────────────────────────────────────────────────────────
    last_note = ""
    if p["games"]:
        lg = p["games"][0]
        last_note = (
            f'<div class="half-notes">'
            f'<span class="hn-label">{lg["game"]} vs {lg["opponent"]}:</span> '
            f'{lg["half_notes"]}</div>'
        )

    return f"""
<div class="player-card" style="background:{grad};box-shadow:0 0 28px {glow};border-color:{border}">
  <div class="pc-header">
    {grade_badge}
    <div class="pc-title">
      <div class="pc-teampos" style="color:{color}">{p['team'].upper()} {pos_tag}</div>
      <div class="pc-name">{p['name']}</div>
    </div>
    <div class="pc-abbr" style="color:{color}30">{abbr}</div>
  </div>
  {stats_strip}
  {props_section}
  {recent_html}
  {last_note}
</div>"""


def pick_card_html(p):
    color = tc(p["team"],"primary"); grad = tc(p["team"],"bg")
    glow  = tc(p["team"],"glow");   border = tc(p["team"],"border")
    abbr  = tc(p["team"],"abbr")

    # Best prop = tracked hit rate first, then projected
    hit_map = {"PTS": p["hit_pts"], "REB": p["hit_reb"], "AST": p["hit_ast"]}

    def sort_key(pp):
        hr = hit_map.get(pp["label"])
        return (hr is None, -(hr or 0))

    sorted_props = sorted(p["props"], key=sort_key) if p["props"] else []
    best = sorted_props[0] if sorted_props else None

    grade_badge = (
        f'<div class="grade-badge" style="background:{p["grade_bg"]};'
        f'color:{p["grade_color"]};border-color:{p["grade_color"]}">{p["grade"]}</div>'
    )

    if best:
        hr = hit_map.get(best["label"])
        pick_color = ("#00ff88" if hr and hr >= 75 else
                      "#FFD700" if hr and hr >= 50 else
                      "#888" if hr is None else "#ff4455")
        rate_label = f"{hr}% HIT RATE" if hr is not None else "PROJECTED"
        ribbon_col = pick_color
        best_block = f"""
  <div class="pick-hero" style="border-color:{pick_color};background:{pick_color}12">
    <div class="ph-label">BEST BET · GAME 3</div>
    <div class="ph-stat">{best['label']}</div>
    <div class="ph-line" style="color:{pick_color}">{fl(best['line'])}</div>
    <div class="ph-dir {'more-btn' if best['more'] else 'less-btn'}" style="font-size:14px;padding:6px 20px">
      {"MORE" if best['more'] else "LESS"}
    </div>
    <div class="ph-rate" style="color:{pick_color}">{rate_label}</div>
    {diff_tag(best['diff'])}
  </div>"""
    else:
        best_block = '<div class="no-props">No PS data</div>'
        ribbon_col = "#888"

    # Secondary props (next 3)
    secondary = "".join(
        prop_tile_html(pp, hit_map.get(pp["label"]), color)
        for pp in sorted_props[1:4]
    )
    secondary_html = (
        f'<div class="secondary-props"><div class="props-grid">{secondary}</div></div>'
        if secondary else ""
    )

    # Running stats
    chips = []
    if p["has_ps"]:
        for v, lbl in [
            (p["ps_pts"],"PPG"),(p["ps_reb"],"RPG"),(p["ps_ast"],"APG"),
            (p["ps_3pm"],"3PM"),(p["ps_stl"],"STL"),(p["ps_blk"],"BLK"),
            (p["ps_to"],"TO"),(p["ps_fs"],"FS"),
        ]:
            if v is not None:
                chips.append(f'<span class="stat-chip">{v} <em>{lbl}</em></span>')
    stats_strip = f'<div class="stats-strip">{"".join(chips)}</div>' if chips else ""

    # Recent games
    pts_line = best["line"] if best and best["label"] == "PTS" else (
        next((pp["line"] for pp in p["props"] if pp["label"] == "PTS"), None)
    )
    recent_html = ""
    if p["games"] and pts_line is not None:
        boxes = recent_boxes_html(p["games"], pts_line, "pts", color)
        recent_html = (
            f'<div class="recent-header">LAST GAMES · PTS (O {fl(pts_line)})</div>'
            f'<div class="recent-boxes">{boxes}</div>'
        )

    return f"""
<div class="pick-card" style="background:{grad};box-shadow:0 0 36px {glow};border-color:{border};--ribbon:{ribbon_col}">
  <div class="pick-ribbon" style="background:{ribbon_col}20;border-color:{ribbon_col}">
    {"FINALS PICK" if p["has_ps"] else "PICK"}
  </div>
  <div class="pc-header">
    {grade_badge}
    <div class="pc-title">
      <div class="pc-teampos" style="color:{color}">{p['team'].upper()}
        <span class="pos-tag" style="border-color:{color}40;color:{color}">{p['position']}</span>
      </div>
      <div class="pc-name">{p['name']}</div>
    </div>
    <div class="pc-abbr" style="color:{color}30">{abbr}</div>
  </div>
  {stats_strip}
  {best_block}
  {secondary_html}
  {recent_html}
</div>"""


# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:#08080f;color:#e8e8f0;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;min-height:100vh;overflow-x:hidden}

/* Header */
.header{background:linear-gradient(90deg,#0e0e1a,#12121f);border-bottom:1px solid #ffffff15;padding:20px 32px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px}
.brand-title{font-size:22px;font-weight:900;letter-spacing:3px;background:linear-gradient(90deg,#FFD700,#FF6B35,#FF4488);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;text-transform:uppercase}
.brand-sub{font-size:11px;letter-spacing:3px;color:#666;text-transform:uppercase;margin-top:3px}
.finals-badge{display:inline-block;margin-top:6px;font-size:10px;font-weight:800;letter-spacing:2px;padding:3px 10px;border-radius:4px;background:linear-gradient(90deg,#FFD70018,#FF6B3518);border:1px solid #FFD70040;color:#FFD700;text-transform:uppercase}
.header-stats{display:flex;gap:14px;flex-wrap:wrap}
.hstat{display:flex;flex-direction:column;align-items:center;padding:8px 14px;border-radius:8px;background:#ffffff08;border:1px solid #ffffff12}
.hstat-val{font-size:24px;font-weight:800;line-height:1}
.hstat-label{font-size:10px;letter-spacing:2px;color:#777;text-transform:uppercase;margin-top:4px}
.win-val{color:#00ff88}.loss-val{color:#ff4455}.rate-val{color:#FFD700}

/* Tabs */
.tab-bar{display:flex;gap:4px;padding:20px 32px 0;border-bottom:1px solid #ffffff10}
.tab-btn{padding:10px 24px;border:none;background:transparent;color:#888;font-size:13px;font-weight:700;letter-spacing:2px;text-transform:uppercase;cursor:pointer;border-bottom:2px solid transparent;transition:all .2s;border-radius:4px 4px 0 0}
.tab-btn:hover{color:#ccc;background:#ffffff08}
.tab-btn.active{color:#FFD700;border-bottom-color:#FFD700;background:#FFD70010}

/* Filter bar */
.filter-bar{display:flex;gap:8px;flex-wrap:wrap;padding:16px 32px}
.filter-btn{padding:6px 16px;border-radius:20px;border:1px solid #333;background:transparent;color:#888;font-size:12px;font-weight:600;letter-spacing:1px;text-transform:uppercase;cursor:pointer;transition:all .15s}
.filter-btn:hover{border-color:#666;color:#ccc}
.filter-btn.active{border-color:#FFD700;color:#FFD700;background:#FFD70015}

/* Sections */
.section{display:none;padding:0 32px 48px}
.section.active{display:block}

/* Grids */
.bet-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px;margin-top:16px}
.player-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:20px;margin-top:16px}
.pick-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:20px;margin-top:16px}

/* ── Bet card ── */
.bet-card{border-radius:12px;padding:16px;border:1px solid #222;background:#0e0e1a;transition:transform .18s,box-shadow .18s;cursor:default}
.bet-card:hover{transform:translateY(-3px)}
.bet-card.hit{border-color:#00ff8830;box-shadow:0 0 16px rgba(0,255,136,.12)}
.bet-card.miss{border-color:#ff445530;box-shadow:0 0 12px rgba(255,68,85,.08)}
.bc-top{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.team-tag{font-size:10px;font-weight:800;letter-spacing:1.5px;padding:2px 7px;border-radius:4px;border:1px solid currentColor}
.bc-date{font-size:11px;color:#666;margin-left:auto}
.bc-game{font-size:10px;color:#555;padding:2px 6px;background:#ffffff08;border-radius:4px}
.bc-player{font-size:15px;font-weight:700;margin-bottom:10px}
.bc-prop-row{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.bc-prop-type{font-size:11px;font-weight:800;letter-spacing:2px;padding:3px 8px;background:#ffffff0f;border-radius:4px}
.bc-dir{font-size:10px;color:#666}
.bc-line{font-size:20px;font-weight:900}
.bc-result-row{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.bc-actual{font-size:32px;font-weight:900;letter-spacing:-1px}
.bc-diff{font-size:14px;font-weight:700}
.result-badge{margin-left:auto;font-size:11px;font-weight:800;letter-spacing:1px;padding:5px 10px;border-radius:6px}
.result-badge.hit{background:#00ff8820;color:#00ff88;border:1px solid #00ff8840}
.result-badge.miss{background:#ff445520;color:#ff6677;border:1px solid #ff445540}
.bc-footer{font-size:11px;color:#555}

/* ── Player card ── */
.player-card{border-radius:16px;padding:20px;border:1px solid #333;transition:transform .2s,box-shadow .25s;cursor:default;position:relative;overflow:hidden}
.player-card:hover{transform:translateY(-3px)}

.pc-header{display:flex;align-items:flex-start;gap:10px;margin-bottom:14px}
.grade-badge{font-size:15px;font-weight:900;padding:4px 10px;border-radius:6px;border:2px solid;min-width:42px;text-align:center;flex-shrink:0}
.pc-title{flex:1;min-width:0}
.pc-teampos{font-size:10px;font-weight:700;letter-spacing:2px;display:flex;align-items:center;gap:6px}
.pos-tag{font-size:9px;font-weight:800;letter-spacing:1px;padding:1px 6px;border-radius:3px;border:1px solid}
.pc-name{font-size:20px;font-weight:900;letter-spacing:-.3px;line-height:1.1;margin-top:2px}
.pc-abbr{font-size:40px;font-weight:900;letter-spacing:-1px;position:absolute;right:14px;top:12px;opacity:.5}

/* Running stats strip */
.stats-strip{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:14px;padding:8px 10px;background:#00000020;border-radius:8px}
.stat-chip{font-size:11px;font-weight:700;color:#ccc;padding:2px 7px;background:#ffffff08;border-radius:4px;white-space:nowrap}
.stat-chip em{font-style:normal;font-size:9px;color:#777;letter-spacing:1px;margin-left:2px}

/* Props */
.props-label{font-size:9px;font-weight:800;letter-spacing:3px;color:#555;text-transform:uppercase;margin-bottom:8px;margin-top:4px}
.props-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:14px}
.prop-tile{display:flex;flex-direction:column;align-items:center;gap:4px;padding:8px 4px;background:#00000030;border-radius:8px;border:1px solid #ffffff0a}
.pt-label{font-size:9px;font-weight:800;letter-spacing:1.5px;color:#777;text-transform:uppercase}
.pt-line{font-size:20px;font-weight:900;line-height:1}
.more-btn,.less-btn{border:none;cursor:default;font-size:10px;font-weight:800;letter-spacing:.5px;padding:3px 8px;border-radius:10px}
.more-btn{background:#00ff8820;color:#00ff88}
.less-btn{background:#ff445520;color:#ff6677}
.diff-tag{font-size:8px;font-weight:800;letter-spacing:1.5px;padding:2px 5px;border-radius:3px}
.diff-tag.demon{background:#ff448830;color:#ff4488}
.diff-tag.goblin{background:#00ffaa20;color:#00ffaa}

/* Recent games */
.recent-header{font-size:9px;font-weight:800;letter-spacing:2px;color:#555;text-transform:uppercase;margin-bottom:6px}
.recent-boxes{display:flex;gap:5px;margin-bottom:12px}
.rg-box{min-width:36px;height:36px;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;border-radius:6px;border:1px solid}

/* Half notes */
.half-notes{font-size:10px;color:#666;line-height:1.4;padding:8px 10px;background:#ffffff05;border-radius:6px;border-left:2px solid #ffffff12}
.hn-label{color:#888;font-weight:700}
.no-props{font-size:11px;color:#444;padding:12px 0;font-style:italic}

/* ── Pick card ── */
.pick-card{border-radius:16px;padding:20px;border:1px solid #333;transition:transform .2s,box-shadow .25s;cursor:default;position:relative;overflow:hidden}
.pick-card:hover{transform:translateY(-4px) scale(1.01)}
.pick-ribbon{font-size:9px;font-weight:800;letter-spacing:3px;text-transform:uppercase;padding:4px 14px;border:1px solid;border-radius:0 0 8px 0;position:absolute;top:0;left:0;border-top:none;border-left:none}

/* Pick hero block */
.pick-hero{display:flex;flex-direction:column;align-items:center;gap:6px;padding:16px 12px;border-radius:12px;border:1px solid;margin-bottom:12px;text-align:center}
.ph-label{font-size:9px;font-weight:800;letter-spacing:2.5px;color:#888;text-transform:uppercase}
.ph-stat{font-size:13px;font-weight:800;letter-spacing:3px;color:#aaa;text-transform:uppercase}
.ph-line{font-size:44px;font-weight:900;letter-spacing:-2px;line-height:1}
.ph-dir{border:none;cursor:default;font-size:14px;font-weight:800;letter-spacing:1px;padding:6px 20px;border-radius:12px}
.ph-rate{font-size:11px;font-weight:600}
.secondary-props{margin-bottom:12px}

/* Responsive */
@media(max-width:600px){
  .header{padding:16px}
  .tab-bar,.filter-bar,.section{padding-left:16px;padding-right:16px}
  .bet-grid,.player-grid,.pick-grid{grid-template-columns:1fr}
  .props-grid{grid-template-columns:repeat(3,1fr)}
  .pc-abbr{display:none}
}
"""

JS = """
function showTab(id) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === id));
  document.querySelectorAll('.section').forEach(s => s.classList.toggle('active', s.id === id));
  document.querySelector('.filter-bar').style.display = (id === 'bets') ? 'flex' : 'none';
}
function filterBets(type) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', b.dataset.filter === type));
  document.querySelectorAll('.bet-card').forEach(card => {
    let show = true;
    if (type==='PTS')    show = card.dataset.prop==='PTS';
    if (type==='REB')    show = card.dataset.prop==='REB';
    if (type==='AST')    show = card.dataset.prop==='AST';
    if (type==='hits')   show = card.dataset.hit==='true';
    if (type==='misses') show = card.dataset.hit==='false';
    card.style.display = show ? '' : 'none';
  });
}
document.addEventListener('DOMContentLoaded', () => { showTab('bets'); filterBets('all'); });
"""


# ── Generate HTML ─────────────────────────────────────────────────────────────
def generate_html(players, bets, out):
    total   = len(bets)
    wins    = sum(1 for b in bets if b["hit"])
    losses  = total - wins
    pct     = round(wins / total * 100) if total else 0
    ps_ct   = sum(1 for p in players.values() if p["has_ps"])
    log_ct  = sum(1 for p in players.values() if p["has_log"])

    bet_cards = "\n".join(bet_card_html(b) for b in bets)

    sorted_p = sorted(players.values(), key=lambda p: p["avg_pts"], reverse=True)
    pcards   = "\n".join(player_card_html(p) for p in sorted_p)

    def pick_key(p):
        hr = max((v for v in [p["hit_pts"],p["hit_reb"],p["hit_ast"]] if v is not None), default=-1)
        return (0 if p["has_ps"] else 1, -hr, -p["avg_pts"])
    pick_p  = sorted(players.values(), key=pick_key)
    picks    = "\n".join(pick_card_html(p) for p in pick_p)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Prize Pics Trading OS — 2026 NBA Finals</title>
<style>{CSS}</style>
</head>
<body>
<div class="header">
  <div>
    <div class="brand-title">Prize Pics Trading OS</div>
    <div class="brand-sub">NYK vs SAS &bull; Prop Card System</div>
    <div class="finals-badge">2026 NBA Finals &bull; Heading Into Game 3</div>
  </div>
  <div class="header-stats">
    <div class="hstat"><span class="hstat-val">{total}</span><span class="hstat-label">Tracked Bets</span></div>
    <div class="hstat"><span class="hstat-val win-val">{wins}</span><span class="hstat-label">Hits</span></div>
    <div class="hstat"><span class="hstat-val loss-val">{losses}</span><span class="hstat-label">Misses</span></div>
    <div class="hstat"><span class="hstat-val rate-val">{pct}%</span><span class="hstat-label">Hit Rate</span></div>
    <div class="hstat"><span class="hstat-val">{ps_ct}</span><span class="hstat-label">PS Profiles</span></div>
    <div class="hstat"><span class="hstat-val">{log_ct}</span><span class="hstat-label">Game Logs</span></div>
  </div>
</div>

<div class="tab-bar">
  <button class="tab-btn" data-tab="bets"    onclick="showTab('bets')">Past Bets</button>
  <button class="tab-btn" data-tab="players" onclick="showTab('players')">Player Cards</button>
  <button class="tab-btn" data-tab="picks"   onclick="showTab('picks')">Finals Picks</button>
</div>

<div class="filter-bar">
  <button class="filter-btn" data-filter="all"    onclick="filterBets('all')">All</button>
  <button class="filter-btn" data-filter="PTS"    onclick="filterBets('PTS')">PTS</button>
  <button class="filter-btn" data-filter="REB"    onclick="filterBets('REB')">REB</button>
  <button class="filter-btn" data-filter="AST"    onclick="filterBets('AST')">AST</button>
  <button class="filter-btn" data-filter="hits"   onclick="filterBets('hits')">Hits Only</button>
  <button class="filter-btn" data-filter="misses" onclick="filterBets('misses')">Misses Only</button>
</div>

<div id="bets" class="section"><div class="bet-grid">{bet_cards}</div></div>
<div id="players" class="section"><div class="player-grid">{pcards}</div></div>
<div id="picks" class="section"><div class="pick-grid">{picks}</div></div>

<script>{JS}</script>
</body></html>"""

    with open(out, "w") as f:
        f.write(html)
    print(f"Generated {out}")
    print(f"  Players:  {len(players)} ({ps_ct} PS profiles, {log_ct} game logs)")
    print(f"  Bets:     {total} ({wins} hits / {losses} misses, {pct}%)")
    print(f"  Picks:    {len(pick_p)}")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    d       = os.path.dirname(os.path.abspath(__file__))
    gl      = load_game_log(os.path.join(d, "playoff_stats.csv"))
    ps      = load_ps_avgs(os.path.join(d, "postseason_averages.csv"))
    players = build_players(gl, ps)
    bets    = simulate_bets(players)
    generate_html(players, bets, os.path.join(d, "prize_pics_dashboard.html"))
