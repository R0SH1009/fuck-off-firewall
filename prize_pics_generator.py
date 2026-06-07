#!/usr/bin/env python3
"""
Prize Pics Trading OS — Prize Picks Format
Displays real Prize Picks entries in the exact app format, alongside
full player trading cards and Finals picks with all 13 prop types.
"""

import pandas as pd
import json
import os

# ── Team config ───────────────────────────────────────────────────────────────
TEAMS = {
    "San Antonio Spurs": {
        "abbr":"SAS","primary":"#C4CED4",
        "bg":"linear-gradient(150deg,#0b0b14 0%,#1a1a2e 60%,#252535 100%)",
        "glow":"rgba(196,206,212,0.3)","border":"#C4CED4",
        "avatar_bg":"#C4CED4","avatar_fg":"#000",
    },
    "New York Knicks": {
        "abbr":"NYK","primary":"#F58426",
        "bg":"linear-gradient(150deg,#001e5c 0%,#003a9e 60%,#c96510 100%)",
        "glow":"rgba(245,132,38,0.4)","border":"#F58426",
        "avatar_bg":"#F58426","avatar_fg":"#000",
    },
}
# Abbreviation lookup for entries (team shown as abbr)
ABBR_TEAMS = {v["abbr"]: k for k, v in TEAMS.items()}
_DT = {"abbr":"NBA","primary":"#888","bg":"linear-gradient(150deg,#111,#333)",
       "glow":"rgba(136,136,136,0.2)","border":"#555",
       "avatar_bg":"#555","avatar_fg":"#fff"}


def tc(team, k):
    cfg = TEAMS.get(team) or TEAMS.get(ABBR_TEAMS.get(team, ""), _DT)
    return cfg.get(k, _DT[k])


def initials(name):
    parts = name.replace("'", "").split()
    return (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else name[:2].upper()


# ── Fantasy Score (Prize Picks official formula) ──────────────────────────────
def fantasy_score(pts, reb, ast, blk, stl, to_):
    return round(pts + reb*1.2 + ast*1.5 + blk*2 + stl*2 - to_, 1)


# ── Grade ─────────────────────────────────────────────────────────────────────
def compute_grade(pts, reb, ast):
    s = pts + reb*0.7 + ast*0.8
    if s >= 32: return "S+","#FFD700","#2a1f00"
    if s >= 25: return "S", "#FFD700","#2a1f00"
    if s >= 19: return "A+","#00FF88","#002211"
    if s >= 14: return "A", "#00CC66","#001a0e"
    if s >= 10: return "B+","#4488FF","#001133"
    if s >= 7:  return "B", "#2266CC","#000d22"
    return "C","#888888","#1a1a1a"


# ── Trend ─────────────────────────────────────────────────────────────────────
def compute_trend(games):
    if len(games) < 2: return "STEADY","→","#777"
    d = games[0]["pts"] - sum(g["pts"] for g in games)/len(games)
    if d >= 5:  return "HOT","↑","#ff6b35"
    if d <= -5: return "COLD","↓","#4488ff"
    return "STEADY","→","#777"


# ── Prop helpers ──────────────────────────────────────────────────────────────
def snap(v): return round(v*2)/2


def mk_prop(label, avg, offset, min_avg=0.0, show_more=True):
    if avg < min_avg: return None
    line = snap(max(0.5, avg+offset))
    ratio = line/avg if avg > 0 else 0.5
    diff = "DEMON" if ratio >= 0.93 else ("GOBLIN" if ratio <= 0.76 else "")
    return {"label":label,"avg":avg,"line":line,"diff":diff,"more":show_more}


def build_props(ps):
    pts=ps["ps_pts"]; reb=ps["ps_reb"]; ast=ps["ps_ast"]
    tpm=ps["ps_3pm"]; stl=ps["ps_stl"]; blk=ps["ps_blk"]; to_=ps["ps_to"]
    fs  = fantasy_score(pts,reb,ast,blk,stl,to_)
    pra = round(pts+reb+ast,1)
    pr  = round(pts+reb,1)
    pa  = round(pts+ast,1)
    ra  = round(reb+ast,1)
    bs  = round(blk+stl,1)
    props=[]
    for p in [
        mk_prop("PTS",     pts, -2.5, 3.0),
        mk_prop("REB",     reb, -1.5, 2.5),
        mk_prop("AST",     ast, -1.5, 2.0),
        mk_prop("3PM",     tpm, -0.5, 0.5),
        mk_prop("STL",     stl, -0.5, 0.3),
        mk_prop("BLK",     blk, -0.5, 0.3),
        mk_prop("TO",      to_, -0.5, 0.8, show_more=False),
        mk_prop("Fantasy", fs,  -4.5, 8.0),
        mk_prop("PRA",     pra, -3.5, 8.0),
        mk_prop("Pts+Reb", pr,  -3.0, 6.0),
        mk_prop("Pts+Ast", pa,  -3.0, 6.0),
        mk_prop("Reb+Ast", ra,  -1.5, 4.0),
        mk_prop("Blk+Stl", bs,  -0.5, 0.8),
    ]:
        if p: props.append(p)
    return props, fs, pra, pr, pa, ra, bs


def hit_rate(games, stat, line):
    if not games: return None
    return round(sum(1 for g in games if g[stat]>line)/len(games)*100)


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
                "pts":int(r["PTS"]),"ast":int(r["AST"]),
                "reb":int(r["REB"]),"min":int(r["MIN"]),
                "half_notes":str(r["1st_Half_Notes"]),
                "win":str(r["Game_Outcome"]).startswith("W"),
            })
        result[name] = {
            "team":grp_s["Team"].iloc[0],"games":games,
            "log_pts":round(grp["PTS"].mean(),1),
            "log_reb":round(grp["REB"].mean(),1),
            "log_ast":round(grp["AST"].mean(),1),
            "log_min":round(grp["MIN"].mean(),1),
        }
    return result


def load_ps_avgs(path):
    df = pd.read_csv(path)
    result = {}
    for _, r in df.iterrows():
        result[str(r["Player"])] = {
            "team":str(r["Team"]),"position":str(r["Position"]),
            "ps_pts":float(r["PPG"]), "ps_reb":float(r["RPG"]),
            "ps_ast":float(r["APG"]), "ps_3pm":float(r["ThreePM"]),
            "ps_stl":float(r["STL"]), "ps_blk":float(r["BLK"]),
            "ps_to": float(r["TO"]),
        }
    return result


def load_past_entries(path):
    with open(path) as f:
        return json.load(f)


def build_players(gl, ps):
    players = {}
    for name in set(gl)|set(ps):
        g=gl.get(name,{}); p=ps.get(name,{})
        games=g.get("games",[]); team=p.get("team") or g.get("team","?")
        has_ps=bool(p); has_log=bool(games)
        pts=p.get("ps_pts",g.get("log_pts",0.0))
        reb=p.get("ps_reb",g.get("log_reb",0.0))
        ast=p.get("ps_ast",g.get("log_ast",0.0))
        grd,gcol,gbg = compute_grade(pts,reb,ast)
        trn,tarr,tcol = compute_trend(games) if has_log else ("—","—","#555")
        props,fs,pra,pr,pa,ra,bs = build_props(p) if has_ps else ([],0,0,0,0,0,0)
        lines={pp["label"]:pp["line"] for pp in props}

        players[name] = {
            "name":name,"team":team,"position":p.get("position","—"),
            "games":games,"game_count":len(games),
            "has_ps":has_ps,"has_log":has_log,
            "ps_pts":p.get("ps_pts"),"ps_reb":p.get("ps_reb"),
            "ps_ast":p.get("ps_ast"),"ps_3pm":p.get("ps_3pm"),
            "ps_stl":p.get("ps_stl"),"ps_blk":p.get("ps_blk"),
            "ps_to": p.get("ps_to"), "ps_fs":fs,"ps_pra":pra,
            "ps_pr":pr,"ps_pa":pa,"ps_ra":ra,"ps_bs":bs,
            "log_pts":g.get("log_pts"),"log_reb":g.get("log_reb"),
            "log_ast":g.get("log_ast"),"log_min":g.get("log_min"),
            "avg_pts":pts,"avg_reb":reb,"avg_ast":ast,
            "props":props,
            "grade":grd,"grade_color":gcol,"grade_bg":gbg,
            "trend":trn,"trend_arrow":tarr,"trend_color":tcol,
            "hit_pts":hit_rate(games,"pts",lines.get("PTS",9999)),
            "hit_reb":hit_rate(games,"reb",lines.get("REB",9999)) if "REB" in lines else None,
            "hit_ast":hit_rate(games,"ast",lines.get("AST",9999)) if "AST" in lines else None,
        }
    return players


# ── Progress bar ──────────────────────────────────────────────────────────────
def progress_bar_html(direction, line, actual, hit):
    max_val = max(actual, line) * 1.4 + 1
    lp = min(99, round(line/max_val*100))
    ap = min(99, round(actual/max_val*100))
    fill_col  = "#00ff88" if hit else "#ff4455"
    circ_bg   = "#00ff8820" if hit else "#ff445520"
    circ_bdr  = "#00ff88" if hit else "#ff4455"
    return (
        f'<div class="bar-wrap">'
        f'  <div class="bar-track">'
        f'    <div class="bar-fill" style="width:{ap}%;background:{fill_col}40"></div>'
        f'    <div class="bar-marker" style="left:{lp}%"></div>'
        f'  </div>'
        f'  <div class="bar-actual" style="left:calc({ap}% - 16px);'
        f'background:{circ_bg};border-color:{circ_bdr};color:{circ_bdr}">{actual}</div>'
        f'</div>'
    )


# ── Entry card (Prize Picks format) ──────────────────────────────────────────
def diff_icon_html(diff):
    if diff == "DEMON":
        return '<span class="diff-icon demon" title="DEMON">😈</span>'
    if diff == "GOBLIN":
        return '<span class="diff-icon goblin" title="GOBLIN">😈</span>'
    return ""


def entry_card_html(entry):
    result     = entry["result"]
    is_win     = result == "Win"
    res_cls    = "win" if is_win else "loss"
    res_badge  = f'<span class="res-badge {res_cls}">{result}</span>'

    amount_str = (
        f'${ entry["entry_amount"]} paid <span class="payout {res_cls}">'
        f'${entry["payout"]}</span>'
        if is_win else
        f'${ entry["entry_amount"]} for <span class="payout {res_cls}">'
        f'${entry["payout"]}</span>'
    )

    # Count hits
    hits   = sum(1 for pk in entry["picks"] if pk["hit"])
    total  = len(entry["picks"])

    picks_html = ""
    for pk in entry["picks"]:
        p_team  = pk["team"]
        full_team = ABBR_TEAMS.get(p_team, p_team)
        ab_bg   = tc(full_team,"avatar_bg")
        ab_fg   = tc(full_team,"avatar_fg")
        t_color = tc(full_team,"primary")
        ini     = initials(pk["player"])
        p_hit   = pk["hit"]
        hit_cls = "hit" if p_hit else "miss"
        dot_html= (
            f'<div class="result-dot win">✓</div>' if p_hit
            else f'<div class="result-dot loss">✗</div>'
        )

        direction = pk["direction"]
        arrow     = "↑" if direction == "MORE" else "↓"
        line_fl   = f'{pk["line"]:.1f}' if pk["line"]!=int(pk["line"]) else f'{int(pk["line"])}.0'

        diff_html = diff_icon_html(pk.get("difficulty",""))

        bar = progress_bar_html(direction, pk["line"], pk["actual"], p_hit)

        picks_html += f"""
<div class="pick-row">
  <div class="pick-left">
    <div class="player-circle {hit_cls}" style="background:{ab_bg}20;border-color:{'#00ff88' if p_hit else '#ff4455'}">
      <span class="p-initials" style="color:{ab_bg}">{ini}</span>
      {dot_html}
    </div>
    <div class="pick-info">
      <div class="pick-name">{pk['player']}</div>
      <div class="pick-meta">{p_team} &bull; {pk['position']} &bull; #{pk['jersey']}</div>
    </div>
  </div>
  <div class="line-badge {hit_cls}">
    {diff_html}<span class="lb-arrow">{arrow}</span>
    <div class="lb-num">{line_fl}</div>
    <div class="lb-stat">{pk['stat']}</div>
  </div>
</div>
{bar}"""

    return f"""
<div class="entry-card" data-result="{res_cls}" data-game="{entry['game']}">
  <div class="entry-header">
    <div class="pp-logo">P</div>
    <div class="entry-meta">
      <div class="entry-amount">{amount_str}</div>
      <div class="entry-type">{total}-Pick {entry['entry_type']} {res_badge}</div>
    </div>
    <div class="entry-score-tag">{hits}/{total}</div>
  </div>
  <div class="game-ctx">
    <span class="sport-tag">NBA</span>
    <span class="game-score">{entry['game']}</span>
    <span class="game-status">{entry['game_status']}</span>
  </div>
  <div class="picks-list">{picks_html}</div>
</div>"""


# ── Player card ───────────────────────────────────────────────────────────────
def fl(v):
    return f"{v:.1f}" if v!=int(v) else f"{int(v)}.0"


def prop_tile_html(pp, hit_rate_val=None, team_color="#888"):
    line_str = fl(pp["line"])
    more_lbl = "MORE" if pp["more"] else "LESS"
    more_cls = "more-btn" if pp["more"] else "less-btn"
    if hit_rate_val is not None:
        rate_str = f"{hit_rate_val}%"
        rc = "#00ff88" if hit_rate_val>=75 else "#FFD700" if hit_rate_val>=50 else "#ff4455"
    else:
        rate_str="PROJ"; rc="#666"
    diff_tag = ""
    if pp["diff"]=="DEMON":
        diff_tag='<span class="dt demon">DEMON</span>'
    elif pp["diff"]=="GOBLIN":
        diff_tag='<span class="dt goblin">GOBLIN</span>'
    return (
        f'<div class="prop-tile">'
        f'<div class="pt-label">{pp["label"]}</div>'
        f'<div class="pt-line" style="color:{team_color}">{line_str}</div>'
        f'<button class="{more_cls}">{more_lbl} <span style="color:{rc};font-size:9px">{rate_str}</span></button>'
        f'{diff_tag}'
        f'</div>'
    )


def recent_boxes_html(games, line, stat_key, color):
    if not games: return ""
    return "".join(
        f'<div class="rg-box" style="color:{"#00ff88" if g[stat_key]>line else "#ff4455"};'
        f'border-color:{"#00ff8840" if g[stat_key]>line else "#ff445540"};'
        f'background:{"#00ff8812" if g[stat_key]>line else "#ff445512"}">'
        f'{g[stat_key]}</div>'
        for g in games[:5]
    )


def player_card_html(p):
    color=tc(p["team"],"primary"); grad=tc(p["team"],"bg")
    glow=tc(p["team"],"glow");    border=tc(p["team"],"border")
    abbr=tc(p["team"],"abbr")

    grade_badge = (
        f'<div class="grade-badge" style="background:{p["grade_bg"]};'
        f'color:{p["grade_color"]};border-color:{p["grade_color"]}">{p["grade"]}</div>'
    )
    pos_tag=f'<span class="pos-tag" style="border-color:{color}40;color:{color}">{p["position"]}</span>'

    chips=[]
    if p["has_ps"]:
        for v,lbl in [(p["ps_pts"],"PPG"),(p["ps_reb"],"RPG"),(p["ps_ast"],"APG"),
                      (p["ps_3pm"],"3PM"),(p["ps_stl"],"STL"),(p["ps_blk"],"BLK"),
                      (p["ps_to"],"TO"),(p["ps_fs"],"FS"),(p["ps_pra"],"PRA")]:
            if v is not None:
                chips.append(f'<span class="stat-chip">{v} <em>{lbl}</em></span>')
    stats_strip=(f'<div class="stats-strip">{"".join(chips)}</div>' if chips else "")

    hit_map={"PTS":p["hit_pts"],"REB":p["hit_reb"],"AST":p["hit_ast"]}
    tiles="".join(prop_tile_html(pp,hit_map.get(pp["label"]),color) for pp in p["props"])
    props_section=(
        f'<div class="props-label">PRIZE PICKS LINES</div><div class="props-grid">{tiles}</div>'
        if tiles else ""
    )

    pts_line=next((pp["line"] for pp in p["props"] if pp["label"]=="PTS"),None)
    recent_html=""
    if p["games"] and pts_line:
        boxes=recent_boxes_html(p["games"],pts_line,"pts",color)
        recent_html=(
            f'<div class="recent-header">LAST {min(len(p["games"]),5)} GAMES · PTS (O {fl(pts_line)})</div>'
            f'<div class="recent-boxes">{boxes}</div>'
        )

    last_note=""
    if p["games"]:
        lg=p["games"][0]
        last_note=(f'<div class="half-notes"><span class="hn-label">{lg["game"]} vs {lg["opponent"]}:</span>'
                   f' {lg["half_notes"]}</div>')

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
    color=tc(p["team"],"primary"); grad=tc(p["team"],"bg")
    glow=tc(p["team"],"glow");    border=tc(p["team"],"border")
    abbr=tc(p["team"],"abbr")

    hit_map={"PTS":p["hit_pts"],"REB":p["hit_reb"],"AST":p["hit_ast"]}
    sorted_props=sorted(p["props"],key=lambda pp:(pp["hit_rate_val"] is None if hasattr(pp,"hit_rate_val") else True,-(hit_map.get(pp["label"]) or 0))) if p["props"] else []
    sorted_props=sorted(p["props"],key=lambda pp:(hit_map.get(pp["label"]) is None,-(hit_map.get(pp["label"]) or 0)))
    best=sorted_props[0] if sorted_props else None

    grade_badge=(
        f'<div class="grade-badge" style="background:{p["grade_bg"]};'
        f'color:{p["grade_color"]};border-color:{p["grade_color"]}">{p["grade"]}</div>'
    )

    if best:
        hr=hit_map.get(best["label"])
        pick_color=("#00ff88" if hr and hr>=75 else "#FFD700" if hr and hr>=50 else "#888" if hr is None else "#ff4455")
        rate_label=f"{hr}% HIT RATE" if hr is not None else "PROJECTED"
        diff_h=""
        if best["diff"]=="DEMON": diff_h='<span class="dt demon">DEMON</span>'
        elif best["diff"]=="GOBLIN": diff_h='<span class="dt goblin">GOBLIN</span>'
        best_block=f"""
  <div class="pick-hero" style="border-color:{pick_color};background:{pick_color}12">
    <div class="ph-label">BEST BET · GAME 3</div>
    <div class="ph-stat">{best['label']}</div>
    <div class="ph-line" style="color:{pick_color}">{fl(best['line'])}</div>
    <button class="{'more-btn' if best['more'] else 'less-btn'}" style="font-size:14px;padding:6px 20px">
      {"MORE" if best['more'] else "LESS"}
    </button>
    <div class="ph-rate" style="color:{pick_color}">{rate_label}</div>
    {diff_h}
  </div>"""
        ribbon_col=pick_color
    else:
        best_block='<div class="no-props">No PS data</div>'; ribbon_col="#888"

    secondary="".join(prop_tile_html(pp,hit_map.get(pp["label"]),color) for pp in sorted_props[1:4])
    secondary_html=(f'<div class="props-grid" style="margin-bottom:12px">{secondary}</div>' if secondary else "")

    chips=[]
    if p["has_ps"]:
        for v,lbl in [(p["ps_pts"],"PPG"),(p["ps_reb"],"RPG"),(p["ps_ast"],"APG"),
                      (p["ps_3pm"],"3PM"),(p["ps_stl"],"STL"),(p["ps_blk"],"BLK"),
                      (p["ps_to"],"TO"),(p["ps_fs"],"FS")]:
            if v is not None: chips.append(f'<span class="stat-chip">{v} <em>{lbl}</em></span>')
    stats_strip=f'<div class="stats-strip">{"".join(chips)}</div>' if chips else ""

    pts_line=next((pp["line"] for pp in p["props"] if pp["label"]=="PTS"),None)
    recent_html=""
    if p["games"] and pts_line:
        boxes=recent_boxes_html(p["games"],pts_line,"pts",color)
        recent_html=(f'<div class="recent-header">LAST GAMES · PTS (O {fl(pts_line)})</div>'
                     f'<div class="recent-boxes">{boxes}</div>')

    return f"""
<div class="pick-card" style="background:{grad};box-shadow:0 0 36px {glow};border-color:{border}">
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

/* ── Header ── */
.header{background:linear-gradient(90deg,#0e0e1a,#12121f);border-bottom:1px solid #ffffff15;padding:20px 32px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px}
.brand-title{font-size:22px;font-weight:900;letter-spacing:3px;background:linear-gradient(90deg,#FFD700,#FF6B35,#FF4488);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;text-transform:uppercase}
.brand-sub{font-size:11px;letter-spacing:3px;color:#666;text-transform:uppercase;margin-top:3px}
.finals-badge{display:inline-block;margin-top:6px;font-size:10px;font-weight:800;letter-spacing:2px;padding:3px 10px;border-radius:4px;background:linear-gradient(90deg,#FFD70018,#FF6B3518);border:1px solid #FFD70040;color:#FFD700;text-transform:uppercase}
.header-stats{display:flex;gap:12px;flex-wrap:wrap}
.hstat{display:flex;flex-direction:column;align-items:center;padding:8px 14px;border-radius:8px;background:#ffffff08;border:1px solid #ffffff12}
.hstat-val{font-size:24px;font-weight:800;line-height:1}
.hstat-label{font-size:10px;letter-spacing:2px;color:#777;text-transform:uppercase;margin-top:4px}
.win-val{color:#00ff88}.loss-val{color:#ff4455}.rate-val{color:#FFD700}

/* ── Tabs ── */
.tab-bar{display:flex;gap:4px;padding:20px 32px 0;border-bottom:1px solid #ffffff10}
.tab-btn{padding:10px 24px;border:none;background:transparent;color:#888;font-size:13px;font-weight:700;letter-spacing:2px;text-transform:uppercase;cursor:pointer;border-bottom:2px solid transparent;transition:all .2s;border-radius:4px 4px 0 0}
.tab-btn:hover{color:#ccc;background:#ffffff08}
.tab-btn.active{color:#FFD700;border-bottom-color:#FFD700;background:#FFD70010}

/* ── Filter bar ── */
.filter-bar{display:none;gap:8px;flex-wrap:wrap;padding:16px 32px}
.filter-btn{padding:6px 16px;border-radius:20px;border:1px solid #333;background:transparent;color:#888;font-size:12px;font-weight:600;letter-spacing:1px;text-transform:uppercase;cursor:pointer;transition:all .15s}
.filter-btn:hover{border-color:#666;color:#ccc}
.filter-btn.active{border-color:#FFD700;color:#FFD700;background:#FFD70015}

/* ── Sections ── */
.section{display:none;padding:0 32px 48px}
.section.active{display:block}

/* ── Entry card grid ── */
.entry-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:20px;margin-top:16px}
.player-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:20px;margin-top:16px}
.pick-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:20px;margin-top:16px}

/* ════════════════════════════════════════
   ENTRY CARD — Prize Picks Style
   ════════════════════════════════════════ */
.entry-card{
  background:#111118;border-radius:18px;padding:0;
  border:1px solid #252530;overflow:hidden;
  transition:transform .2s,box-shadow .2s;cursor:default;
}
.entry-card:hover{transform:translateY(-3px);box-shadow:0 8px 32px rgba(0,0,0,.5)}

/* Entry header */
.entry-header{
  display:flex;align-items:center;gap:12px;
  padding:16px 16px 12px;
  border-bottom:1px solid #1e1e2a;
}
.pp-logo{
  width:42px;height:42px;border-radius:50%;flex-shrink:0;
  background:linear-gradient(135deg,#7B2FF7,#4A00E0);
  display:flex;align-items:center;justify-content:center;
  font-size:18px;font-weight:900;color:#fff;letter-spacing:-1px;
}
.entry-meta{flex:1}
.entry-amount{font-size:16px;font-weight:800;color:#fff}
.entry-amount .payout.win{color:#00ff88}
.entry-amount .payout.loss{color:#ff4455}
.entry-type{font-size:12px;color:#666;margin-top:2px;display:flex;align-items:center;gap:6px}
.res-badge{font-size:10px;font-weight:800;letter-spacing:1px;padding:2px 8px;border-radius:4px;text-transform:uppercase}
.res-badge.win{background:#00ff8820;color:#00ff88;border:1px solid #00ff8840}
.res-badge.loss{background:#ff445520;color:#ff6677;border:1px solid #ff445540}
.entry-score-tag{
  font-size:13px;font-weight:800;color:#888;
  padding:4px 10px;border-radius:8px;background:#ffffff08;
  border:1px solid #ffffff10;white-space:nowrap;
}

/* Game context */
.game-ctx{
  display:flex;align-items:center;gap:8px;
  padding:8px 16px;background:#0e0e1a;
  border-bottom:1px solid #1e1e2a;
}
.sport-tag{font-size:10px;font-weight:800;letter-spacing:2px;color:#FFD700;background:#FFD70015;padding:2px 8px;border-radius:4px;border:1px solid #FFD70030}
.game-score{font-size:13px;font-weight:700;color:#ccc;flex:1}
.game-status{font-size:11px;color:#555;font-weight:600;letter-spacing:1px}

/* Pick rows */
.picks-list{padding:0 0 8px}
.pick-row{
  display:flex;align-items:center;justify-content:space-between;
  padding:12px 16px 4px;gap:10px;
}

/* Player circle */
.player-circle{
  width:50px;height:50px;border-radius:50%;flex-shrink:0;
  border:2px solid;
  display:flex;align-items:center;justify-content:center;
  position:relative;
}
.player-circle.hit{border-color:#00ff88}
.player-circle.miss{border-color:#ff4455}
.p-initials{font-size:15px;font-weight:900;letter-spacing:-.5px}
.result-dot{
  position:absolute;bottom:-3px;right:-3px;
  width:18px;height:18px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  font-size:10px;font-weight:900;border:2px solid #111118;
}
.result-dot.win{background:#00ff88;color:#000}
.result-dot.loss{background:#ff4455;color:#fff}

/* Pick info */
.pick-left{display:flex;align-items:center;gap:10px;flex:1;min-width:0}
.pick-info{min-width:0}
.pick-name{font-size:14px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pick-meta{font-size:11px;color:#666;margin-top:1px}

/* Line badge */
.line-badge{
  display:flex;flex-direction:column;align-items:center;gap:1px;
  padding:8px 10px;border-radius:10px;background:#1e1e2a;
  border:1px solid #2a2a3a;min-width:72px;flex-shrink:0;
}
.line-badge.hit{border-color:#00ff8830}
.line-badge.miss{border-color:#ff445530}
.lb-arrow{font-size:14px;font-weight:900;color:#ccc;line-height:1}
.lb-num{font-size:22px;font-weight:900;letter-spacing:-.5px;line-height:1}
.lb-stat{font-size:9px;color:#777;letter-spacing:1px;text-transform:uppercase}
.diff-icon{font-size:13px;line-height:1}
.diff-icon.demon{filter:sepia(1) saturate(3) hue-rotate(-20deg)}
.diff-icon.goblin{filter:sepia(1) saturate(3) hue-rotate(80deg)}

/* Progress bar */
.bar-wrap{
  position:relative;padding:0 16px;margin-bottom:10px;margin-top:6px;
  height:30px;
}
.bar-track{
  position:absolute;left:16px;right:16px;top:12px;
  height:6px;background:#1e1e2a;border-radius:3px;overflow:visible;
}
.bar-fill{
  position:absolute;left:0;top:0;height:100%;
  border-radius:3px;transition:width .3s;
}
.bar-marker{
  position:absolute;top:-5px;
  width:3px;height:16px;background:#ffffff80;
  border-radius:2px;transform:translateX(-50%);
}
.bar-actual{
  position:absolute;top:-10px;
  width:30px;height:30px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  font-size:11px;font-weight:800;border:2px solid;
  z-index:1;
}

/* ── Player card ── */
.player-card{border-radius:16px;padding:20px;border:1px solid #333;transition:transform .2s;cursor:default;position:relative;overflow:hidden}
.player-card:hover{transform:translateY(-3px)}
.pc-header{display:flex;align-items:flex-start;gap:10px;margin-bottom:14px}
.grade-badge{font-size:15px;font-weight:900;padding:4px 10px;border-radius:6px;border:2px solid;min-width:42px;text-align:center;flex-shrink:0}
.pc-title{flex:1;min-width:0}
.pc-teampos{font-size:10px;font-weight:700;letter-spacing:2px;display:flex;align-items:center;gap:6px}
.pos-tag{font-size:9px;font-weight:800;letter-spacing:1px;padding:1px 6px;border-radius:3px;border:1px solid}
.pc-name{font-size:20px;font-weight:900;letter-spacing:-.3px;line-height:1.1;margin-top:2px}
.pc-abbr{font-size:40px;font-weight:900;letter-spacing:-1px;position:absolute;right:14px;top:12px;opacity:.5}
.stats-strip{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:14px;padding:8px 10px;background:#00000020;border-radius:8px}
.stat-chip{font-size:11px;font-weight:700;color:#ccc;padding:2px 7px;background:#ffffff08;border-radius:4px;white-space:nowrap}
.stat-chip em{font-style:normal;font-size:9px;color:#777;letter-spacing:1px;margin-left:2px}
.props-label{font-size:9px;font-weight:800;letter-spacing:3px;color:#555;text-transform:uppercase;margin-bottom:8px;margin-top:4px}
.props-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:14px}
.prop-tile{display:flex;flex-direction:column;align-items:center;gap:4px;padding:8px 4px;background:#00000030;border-radius:8px;border:1px solid #ffffff0a}
.pt-label{font-size:9px;font-weight:800;letter-spacing:1.5px;color:#777;text-transform:uppercase}
.pt-line{font-size:20px;font-weight:900;line-height:1}
.more-btn,.less-btn{border:none;cursor:default;font-size:10px;font-weight:800;letter-spacing:.5px;padding:3px 8px;border-radius:10px}
.more-btn{background:#00ff8820;color:#00ff88}
.less-btn{background:#ff445520;color:#ff6677}
.dt{font-size:8px;font-weight:800;letter-spacing:1.5px;padding:2px 5px;border-radius:3px}
.dt.demon{background:#ff448830;color:#ff4488}
.dt.goblin{background:#00ffaa20;color:#00ffaa}
.recent-header{font-size:9px;font-weight:800;letter-spacing:2px;color:#555;text-transform:uppercase;margin-bottom:6px}
.recent-boxes{display:flex;gap:5px;margin-bottom:12px}
.rg-box{min-width:36px;height:36px;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;border-radius:6px;border:1px solid}
.half-notes{font-size:10px;color:#666;line-height:1.4;padding:8px 10px;background:#ffffff05;border-radius:6px;border-left:2px solid #ffffff12}
.hn-label{color:#888;font-weight:700}
.no-props{font-size:11px;color:#444;padding:12px 0;font-style:italic}

/* ── Pick card ── */
.pick-card{border-radius:16px;padding:20px;border:1px solid #333;transition:transform .2s;cursor:default;position:relative;overflow:hidden}
.pick-card:hover{transform:translateY(-4px) scale(1.01)}
.pick-ribbon{font-size:9px;font-weight:800;letter-spacing:3px;text-transform:uppercase;padding:4px 14px;border:1px solid;border-radius:0 0 8px 0;position:absolute;top:0;left:0;border-top:none;border-left:none}
.pick-hero{display:flex;flex-direction:column;align-items:center;gap:6px;padding:16px 12px;border-radius:12px;border:1px solid;margin-bottom:12px;text-align:center}
.ph-label{font-size:9px;font-weight:800;letter-spacing:2.5px;color:#888;text-transform:uppercase}
.ph-stat{font-size:13px;font-weight:800;letter-spacing:3px;color:#aaa;text-transform:uppercase}
.ph-line{font-size:44px;font-weight:900;letter-spacing:-2px;line-height:1}
.ph-rate{font-size:11px;font-weight:600}

/* Responsive */
@media(max-width:600px){
  .header{padding:16px}
  .tab-bar,.filter-bar,.section{padding-left:16px;padding-right:16px}
  .entry-grid,.player-grid,.pick-grid{grid-template-columns:1fr}
  .props-grid{grid-template-columns:repeat(3,1fr)}
  .pc-abbr{display:none}
}
"""

JS = """
function showTab(id) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === id));
  document.querySelectorAll('.section').forEach(s => s.classList.toggle('active', s.id === id));
  const fb = document.querySelector('.filter-bar');
  if (fb) fb.style.display = (id === 'entries') ? 'flex' : 'none';
}
function filterEntries(type) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', b.dataset.filter === type));
  document.querySelectorAll('.entry-card').forEach(card => {
    let show = true;
    if (type === 'wins')   show = card.dataset.result === 'win';
    if (type === 'losses') show = card.dataset.result === 'loss';
    card.style.display = show ? '' : 'none';
  });
}
document.addEventListener('DOMContentLoaded', () => { showTab('entries'); filterEntries('all'); });
"""


# ── Generate HTML ─────────────────────────────────────────────────────────────
def generate_html(players, entries, out):
    ps_ct  = sum(1 for p in players.values() if p["has_ps"])
    log_ct = sum(1 for p in players.values() if p["has_log"])

    total_bets = sum(len(e["picks"]) for e in entries)
    total_hits = sum(sum(1 for pk in e["picks"] if pk["hit"]) for e in entries)
    total_wins = sum(1 for e in entries if e["result"]=="Win")
    total_paid = sum(e["entry_amount"] for e in entries)
    total_won  = sum(e["payout"] for e in entries if e["result"]=="Win")
    net        = total_won - total_paid

    entry_cards = "\n".join(entry_card_html(e) for e in entries)

    sorted_p = sorted(players.values(), key=lambda p: p["avg_pts"], reverse=True)
    pcards   = "\n".join(player_card_html(p) for p in sorted_p)

    def pick_key(p):
        hr=max((v for v in [p["hit_pts"],p["hit_reb"],p["hit_ast"]] if v is not None),default=-1)
        return (0 if p["has_ps"] else 1, -hr, -p["avg_pts"])
    picks = "\n".join(pick_card_html(p) for p in sorted(players.values(), key=pick_key))

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
    <div class="hstat"><span class="hstat-val">{len(entries)}</span><span class="hstat-label">Entries</span></div>
    <div class="hstat"><span class="hstat-val win-val">{total_wins}</span><span class="hstat-label">Wins</span></div>
    <div class="hstat"><span class="hstat-val">{total_hits}/{total_bets}</span><span class="hstat-label">Picks Hit</span></div>
    <div class="hstat"><span class="hstat-val {'win-val' if net>=0 else 'loss-val'}">${abs(net)}</span><span class="hstat-label">{'Net Win' if net>=0 else 'Net Loss'}</span></div>
    <div class="hstat"><span class="hstat-val">{ps_ct}</span><span class="hstat-label">PS Profiles</span></div>
  </div>
</div>

<div class="tab-bar">
  <button class="tab-btn" data-tab="entries" onclick="showTab('entries')">Past Bets</button>
  <button class="tab-btn" data-tab="players" onclick="showTab('players')">Player Cards</button>
  <button class="tab-btn" data-tab="picks"   onclick="showTab('picks')">Finals Picks</button>
</div>

<div class="filter-bar">
  <button class="filter-btn" data-filter="all"    onclick="filterEntries('all')">All Entries</button>
  <button class="filter-btn" data-filter="wins"   onclick="filterEntries('wins')">Wins</button>
  <button class="filter-btn" data-filter="losses" onclick="filterEntries('losses')">Losses</button>
</div>

<div id="entries" class="section"><div class="entry-grid">{entry_cards}</div></div>
<div id="players" class="section"><div class="player-grid">{pcards}</div></div>
<div id="picks"   class="section"><div class="pick-grid">{picks}</div></div>

<script>{JS}</script>
</body></html>"""

    with open(out,"w") as f: f.write(html)
    net_str = f"+${net}" if net>=0 else f"-${abs(net)}"
    print(f"Generated {out}")
    print(f"  Entries: {len(entries)}  ({total_wins} wins, {len(entries)-total_wins} losses)")
    print(f"  Picks:   {total_hits}/{total_bets} hit ({round(total_hits/total_bets*100)}%)")
    print(f"  Net P&L: {net_str}  (paid ${total_paid}, won ${total_won})")
    print(f"  Players: {len(players)}  ({ps_ct} PS profiles, {log_ct} game logs)")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    d       = os.path.dirname(os.path.abspath(__file__))
    gl      = load_game_log(os.path.join(d,"playoff_stats.csv"))
    ps      = load_ps_avgs(os.path.join(d,"postseason_averages.csv"))
    entries = load_past_entries(os.path.join(d,"past_entries.json"))
    players = build_players(gl, ps)
    generate_html(players, entries, os.path.join(d,"prize_pics_dashboard.html"))
