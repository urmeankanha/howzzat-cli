#!/usr/bin/env python3
"""
howzzat-cli — Live cricket score ticker for your terminal.
Data via: cricbuzz-cricket.p.rapidapi.com (free tier: 100 req/day)
Sign up free at: https://rapidapi.com/cricketapilive/api/cricbuzz-cricket

Usage:
    python3 howzzat.py                      # uses key from ~/.howzzat
    python3 howzzat.py --key YOUR_API_KEY   # set/save key and launch
"""

import sys
import os
import time
import json
import signal
import threading
import argparse
import textwrap
import requests
from datetime import datetime
from pathlib import Path

try:
    from blessed import Terminal
except ImportError:
    print("Missing dependency. Run:  pip install blessed requests")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Config / API key
# ─────────────────────────────────────────────────────────────────────────────
CONFIG_FILE   = Path.home() / ".howzzat"
RAPIDAPI_HOST = "cricbuzz-cricket.p.rapidapi.com"
BASE_URL      = f"https://{RAPIDAPI_HOST}"

def load_key():
    if CONFIG_FILE.exists():
        return CONFIG_FILE.read_text().strip()
    return None

def save_key(key):
    CONFIG_FILE.write_text(key.strip())
    CONFIG_FILE.chmod(0o600)

def api_headers(key):
    return {
        "X-RapidAPI-Key":  key,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }

# ─────────────────────────────────────────────────────────────────────────────
# Terminal + constants
# ─────────────────────────────────────────────────────────────────────────────
term = Terminal()
W    = 74   # fixed UI width

LOGO = r"""
██╗  ██╗ ██████╗ ██╗    ██╗███████╗███████╗ █████╗ ████████╗
██║  ██║██╔═══██╗██║    ██║╚══███╔╝╚══███╔╝██╔══██╗╚══██╔══╝
███████║██║   ██║██║ █╗ ██║  ███╔╝   ███╔╝ ███████║   ██║
██╔══██║██║   ██║██║███╗██║ ███╔╝   ███╔╝  ██╔══██║   ██║
██║  ██║╚██████╔╝╚███╔███╔╝███████╗███████╗██║  ██║   ██║
╚═╝  ╚═╝ ╚═════╝  ╚══╝╚══╝ ╚══════╝╚══════╝╚═╝  ╚═╝   ╚═╝"""

# ─────────────────────────────────────────────────────────────────────────────
# Shared state
# ─────────────────────────────────────────────────────────────────────────────
state = {
    "api_key":      None,
    "matches":      [],
    "selected":     None,
    "live":         None,
    "last_refresh": None,
    "error":        None,
    "mode":         "select",
    "req_count":    0,
}

REFRESH_SECS = 45

# ─────────────────────────────────────────────────────────────────────────────
# API helpers
# ─────────────────────────────────────────────────────────────────────────────
def _get(path, key, timeout=12):
    try:
        r = requests.get(
            f"{BASE_URL}{path}",
            headers=api_headers(key),
            timeout=timeout,
        )
        state["req_count"] += 1
        if r.status_code == 403:
            state["error"] = (
                "API key rejected (403). "
                "Check your key at rapidapi.com/cricketapilive/api/cricbuzz-cricket"
            )
            return None
        if r.status_code == 429:
            state["error"] = "Daily limit hit (100 req/day free tier). Try again tomorrow."
            return None
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        state["error"] = "No internet connection."
        return None
    except Exception as e:
        state["error"] = str(e)[:90]
        return None


def fetch_live_matches(key):
    data = _get("/matches/v1/live", key)
    return _parse_match_list(data) if data else []


def fetch_recent_matches(key):
    data = _get("/matches/v1/recent", key)
    return _parse_match_list(data) if data else []


def _parse_match_list(data):
    matches = []
    for group in data.get("typeMatches", []):
        for series in group.get("seriesMatches", []):
            wrapper = series.get("seriesAdWrapper") or series
            for m in wrapper.get("matches", []):
                mi = m.get("matchInfo", {})
                ms = m.get("matchScore", {})
                matches.append({
                    "id":         mi.get("matchId"),
                    "format":     mi.get("matchFormat", ""),
                    "desc":       mi.get("matchDesc", ""),
                    "series":     mi.get("seriesName", ""),
                    "team1":      mi.get("team1", {}).get("teamSName", "?"),
                    "team2":      mi.get("team2", {}).get("teamSName", "?"),
                    "team1_full": mi.get("team1", {}).get("teamName", ""),
                    "team2_full": mi.get("team2", {}).get("teamName", ""),
                    "venue":      mi.get("venueInfo", {}).get("ground", ""),
                    "city":       mi.get("venueInfo", {}).get("city", ""),
                    "state":      mi.get("state", ""),
                    "status":     mi.get("status", ""),
                    "score":      ms,
                })
    return matches


def fetch_scorecard(key, match_id):
    return _get(f"/mcenter/v1/{match_id}/scard", key)


def fetch_commentary(key, match_id):
    return _get(f"/mcenter/v1/{match_id}/comm", key)


def fetch_match_info(key, match_id):
    return _get(f"/mcenter/v1/{match_id}", key)


# ─────────────────────────────────────────────────────────────────────────────
# Data parsing
# ─────────────────────────────────────────────────────────────────────────────
def parse_live(scard, comm, minfo):
    out = {
        "innings":      [],
        "live_idx":     0,
        "bat1":         None,
        "bat2":         None,
        "bowl":         None,
        "partnership":  {},
        "this_over":    [],
        "crr":          None,
        "rrr":          None,
        "target":       None,
        "need":         None,
        "balls_left":   None,
        "status":       "",
        "toss":         "",
        "venue":        "",
        "series":       "",
        "match_desc":   "",
        "commentary":   [],
    }

    # Match header info
    if minfo:
        mh = minfo.get("matchHeader", {})
        out["status"]     = mh.get("status", "")
        out["series"]     = mh.get("seriesName", "")
        out["match_desc"] = mh.get("matchDescription", "")
        toss = mh.get("toss", {})
        tw   = toss.get("tossWinnerName", "")
        td   = toss.get("decision", "")
        if tw and td:
            out["toss"] = f"{tw} won toss, elected to {td}"
        vi = minfo.get("venueInfo", {})
        out["venue"] = vi.get("ground", "")
        if vi.get("city"):
            out["venue"] += f", {vi['city']}"

    # Scorecard
    if scard:
        for inn in scard.get("scoreCard", []):
            sd       = inn.get("scoreDetails", {})
            bat_det  = inn.get("batTeamDetails", {})
            bowl_det = inn.get("bowlTeamDetails", {})

            batsmen_raw = bat_det.get("batsmenData", {})
            bowlers_raw = bowl_det.get("bowlersData", {})

            # Identify active batsmen
            batsmen = sorted(batsmen_raw.values(),
                             key=lambda b: b.get("batId", 0))
            active  = [b for b in batsmen
                       if not str(b.get("outDesc","")).strip()
                       or int(b.get("balls", b.get("ballsFaced", 0))) > 0]

            striker     = next((b for b in active if b.get("isStriker") is True),  None)
            non_striker = next((b for b in active if b.get("isStriker") is False), None)

            # Fallback: pick last two active
            if striker is None and active:
                striker = active[-1]
            if non_striker is None and len(active) >= 2:
                non_striker = active[-2]

            # Current bowler
            bowlers  = sorted(bowlers_raw.values(),
                              key=lambda b: b.get("bowlId", 0))
            cur_bowl = next((b for b in bowlers if b.get("isStriker") is True), None)
            if cur_bowl is None and bowlers:
                cur_bowl = bowlers[-1]

            # This over
            tor = inn.get("thisOver", []) or []
            if isinstance(tor, dict):
                tor = list(tor.values())

            out["innings"].append({
                "id":          inn.get("inningsId", len(out["innings"]) + 1),
                "bat_team":    bat_det.get("batTeamName", ""),
                "runs":        sd.get("runs", 0),
                "wickets":     sd.get("wickets", 0),
                "overs":       sd.get("overs", "0"),
                "inn_state":   inn.get("inningsType", ""),
                "striker":     striker,
                "non_striker": non_striker,
                "cur_bowl":    cur_bowl,
                "this_over":   tor,
                "partnership": inn.get("partnerShip", {}) or {},
                "crr":         sd.get("runRate"),
                "rrr":         sd.get("reqRunRate"),
                "target":      sd.get("target"),
                "need":        sd.get("runsToGet"),
                "balls_left":  sd.get("ballsToGo"),
            })

        # Live innings = last that isn't complete
        live_idx = len(out["innings"]) - 1
        for i, inn in enumerate(out["innings"]):
            if str(inn["inn_state"]).upper() not in ("COMPLETE",):
                live_idx = i
        out["live_idx"] = live_idx

        if out["innings"]:
            li = out["innings"][live_idx]
            out.update({
                "bat1":       li["striker"],
                "bat2":       li["non_striker"],
                "bowl":       li["cur_bowl"],
                "this_over":  li["this_over"],
                "partnership":li["partnership"],
                "crr":        li["crr"],
                "rrr":        li["rrr"],
                "target":     li["target"],
                "need":       li["need"],
                "balls_left": li["balls_left"],
            })

    # Commentary
    if comm:
        lines = []
        for c in (comm.get("commentaryList", []) or [])[:10]:
            txt   = (c.get("commText") or "").strip()
            event = c.get("event", "")
            ov    = c.get("overNumber", "")
            ball  = c.get("ballNumber", "")
            tag   = {
                "FOUR":    "[4]  ",
                "SIX":     "[6]  ",
                "WICKET":  "[W]  ",
                "WIDE":    "[Wd] ",
                "WD":      "[Wd] ",
                "NO_BALL": "[Nb] ",
            }.get(event, "     ")
            prefix = f"  {ov}.{ball}  {tag}" if ov else f"       {tag}"
            lines.append((prefix + txt, event))
        out["commentary"] = lines

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Drawing helpers
# ─────────────────────────────────────────────────────────────────────────────
def _w(s):
    sys.stdout.write(s)

def _row(y):
    _w(term.move(y, 0))

def draw_logo(start):
    lines = LOGO.strip("\n").split("\n")
    for i, line in enumerate(lines):
        _row(start + i)
        pad = max(0, (W - len(line)) // 2)
        _w(" " * pad + term.bold + term.color_rgb(230, 80, 60) + line + term.normal)
    return start + len(lines)

def box_top(y, title=""):
    _row(y)
    if title:
        t  = f" {title} "
        lp = max(0, (W - len(t) - 2) // 2)
        rp = max(0, W - 2 - len(t) - lp)
        _w(term.dim + "┌" + "─"*lp + term.normal
           + term.bold + t + term.normal
           + term.dim + "─"*rp + "┐" + term.normal)
    else:
        _w(term.dim + "┌" + "─"*(W-2) + "┐" + term.normal)

def box_bot(y):
    _row(y)
    _w(term.dim + "└" + "─"*(W-2) + "┘" + term.normal)

def box_div(y):
    _row(y)
    _w(term.dim + "├" + "─"*(W-2) + "┤" + term.normal)

def box_row(y, left="", right="", lc="", rc=""):
    _row(y)
    inner = W - 2
    if right:
        gap  = max(1, inner - len(left) - len(right))
        line = lc + left + term.normal + " "*gap + rc + right + term.normal
    else:
        line = lc + left[:inner].ljust(inner) + term.normal
    _w(term.dim + "│" + term.normal
       + line
       + term.move_x(W-1) + term.dim + "│" + term.normal)

def ball_fmt(b):
    s = str(b).upper().strip()
    if s in ("W","WICKET","OUT"):     return term.bold+term.red    +" W "+term.normal
    if s == "4":                       return term.bold+term.green  +" 4 "+term.normal
    if s == "6":                       return term.bold+term.yellow +" 6 "+term.normal
    if s in ("WD","WIDE"):             return term.cyan             +"Wd "+term.normal
    if s in ("NB","NO_BALL","NBALL"):  return term.magenta          +"Nb "+term.normal
    if s in ("0","DOT","•"):           return term.dim              +" • "+term.normal
    return term.white + f" {s} " + term.normal

def fmt_r(v):
    if v is None: return "  -  "
    try:    return f"{float(v):.2f}"
    except: return str(v)

def _bat_name(b, n=18): return (b or {}).get("batName",  (b or {}).get("name",  "?"))[:n]
def _bowl_name(b, n=18):return (b or {}).get("bowlName", (b or {}).get("name",  "?"))[:n]

def _bat_stat(b):
    if not b: return ""
    r  = b.get("runs",  b.get("r",  0))
    bl = b.get("balls", b.get("b",  0))
    f  = b.get("fours", b.get("4s", 0))
    s  = b.get("sixes", b.get("6s", 0))
    sr = b.get("strikeRate", b.get("sr", "-"))
    try: sr = f"{float(sr):.1f}"
    except: pass
    return f"{r:>4}({bl:>3}b)  4s:{f}  6s:{s}  SR:{sr:>5}"

def _bowl_stat(b):
    if not b: return ""
    ov = b.get("overs",   b.get("ov", 0))
    md = b.get("maidens", b.get("m",  0))
    r  = b.get("runs",    b.get("r",  0))
    w  = b.get("wickets", b.get("w",  0))
    ec = b.get("economy", b.get("eco", "-"))
    try: ec = f"{float(ec):.2f}"
    except: pass
    return f"{ov}-{md}-{r}-{w}   eco:{ec}"


# ─────────────────────────────────────────────────────────────────────────────
# Screens
# ─────────────────────────────────────────────────────────────────────────────
def draw_setup_screen():
    _w(term.clear)
    r = draw_logo(0) + 1
    setup_lines = [
        "",
        "  ⚡  First-time setup",
        "",
        "  howzzat-cli uses the Cricbuzz API via RapidAPI.",
        "  The FREE plan gives you 100 requests/day — plenty for personal use.",
        "",
        "  Steps:",
        "    1. Open:  https://rapidapi.com/cricketapilive/api/cricbuzz-cricket",
        "    2. Click 'Subscribe to Test'  →  select the FREE Basic plan",
        "    3. Copy your  X-RapidAPI-Key  from the dashboard",
        "    4. Paste it here and press Enter:",
        "",
    ]
    for line in setup_lines:
        _row(r); _w(term.dim + line + term.normal)
        r += 1
    _row(r); _w("  API Key: " + term.bold)
    sys.stdout.flush()


def draw_select_screen(input_buf=""):
    _w(term.clear)
    r = draw_logo(0) + 1
    matches = state["matches"]

    if state["error"] and not matches:
        _row(r); _w(term.red + f"  ✗ {state['error']}" + term.normal); r += 1
        _row(r); _w(term.dim + "  Press [R] to retry, [Q] to quit." + term.normal)
        _draw_footer(r + 2); sys.stdout.flush(); return

    if not matches:
        _row(r); _w(term.yellow + "  Fetching matches…" + term.normal)
        sys.stdout.flush(); return

    box_top(r, "LIVE  &  RECENT  MATCHES"); r += 1

    entry_rows = []   # track display rows per match for interleaved scores
    disp_row = r
    for i, m in enumerate(matches[:16]):
        num   = term.bold + term.cyan + f" [{i+1:>2}]" + term.normal
        teams = term.bold + f" {m['team1']} vs {m['team2']}" + term.normal
        fmt   = term.dim + f"  {m['format']}" + term.normal
        state_tag = ""
        if m["state"] == "In Progress":
            state_tag = term.green + "  ● LIVE" + term.normal
        _row(disp_row); _w(f"{num}{teams}{fmt}{state_tag}")
        disp_row += 1

        # compact score on next line
        s  = m.get("score", {})
        t1 = s.get("team1Score", {})
        t2 = s.get("team2Score", {})
        def _sc(ts, label):
            i1 = ts.get("inngs1", {})
            i2 = ts.get("inngs2", {})
            parts = []
            if i1: parts.append(f"{i1.get('runs','?')}/{i1.get('wickets','?')} ({i1.get('overs','?')} ov)")
            if i2: parts.append(f"{i2.get('runs','?')}/{i2.get('wickets','?')} ({i2.get('overs','?')} ov)")
            return f"{label}: " + " & ".join(parts) if parts else ""
        parts = []
        if t1: parts.append(_sc(t1, m["team1"]))
        if t2: parts.append(_sc(t2, m["team2"]))
        if parts:
            line = "  " + "     ".join(parts)
            _row(disp_row); _w(term.dim + line[:W-2] + term.normal)
            disp_row += 1

        # status line
        if m["status"]:
            _row(disp_row); _w(term.dim + "       " + m["status"][:W-10] + term.normal)
            disp_row += 1

        disp_row += 1  # gap between matches

    box_bot(disp_row); disp_row += 1

    now = datetime.now().strftime("%H:%M:%S")
    _row(disp_row)
    _w(term.dim + f"  {now}  •  req: {state['req_count']}/100 today" + term.normal)
    disp_row += 1
    _row(disp_row)
    _w(term.dim + f"  Enter match number: " + term.normal + term.bold + input_buf + term.normal
       + term.dim + "   [R] refresh  [Q] quit" + term.normal)
    sys.stdout.flush()


def draw_live_screen():
    lv = state["live"]
    m  = state["selected"]

    _w(term.clear)
    r = draw_logo(0) + 1

    if not lv:
        _row(r); _w(term.yellow + "  Fetching match data…" + term.normal)
        _draw_footer(r+2); sys.stdout.flush(); return

    # ── Header ────────────────────────────────────────────────────────────
    t1 = m.get("team1_full") or m["team1"]
    t2 = m.get("team2_full") or m["team2"]
    box_top(r, ""); r += 1
    box_row(r, f" {t1} vs {t2}  •  {m['format']}",
               f" {lv['venue'] or m.get('city','')} ",
            lc=term.bold+term.white, rc=term.dim); r += 1

    if lv["series"]:
        box_row(r, f" {lv['series'][:W-4]}", "", lc=term.dim); r += 1
    if lv["toss"]:
        box_row(r, f" {lv['toss'][:W-4]}", "", lc=term.dim); r += 1
    box_div(r); r += 1

    # ── Innings scores ────────────────────────────────────────────────────
    live_idx = lv["live_idx"]
    for i, inn in enumerate(lv["innings"]):
        is_live = (i == live_idx)
        sfx = {1:"st",2:"nd",3:"rd"}.get(inn["id"],"th")
        lc  = (term.bold+term.green) if is_live else term.white
        rc  = (term.bold+term.green) if is_live else term.dim
        box_row(r,
                f" {inn['bat_team']}  {inn['id']}{sfx} Inn",
                f"{inn['runs']}/{inn['wickets']}  ({inn['overs']} ov) ",
                lc=lc, rc=rc); r += 1
    box_div(r); r += 1

    # ── Batting ───────────────────────────────────────────────────────────
    _row(r)
    _w(term.dim+"│"+term.normal
       + term.bold + " BATTING" + " "*18 + "  R   ( B )  4s  6s     SR"[:W-28] + term.normal
       + term.dim+"│"+term.normal); r += 1

    for bat, on_strike in [(lv["bat1"], True), (lv["bat2"], False)]:
        star = (term.bold+term.green+"* "+term.normal) if on_strike else "  "
        nc   = (term.bold+term.white) if on_strike else term.white
        name = _bat_name(bat)
        stat = _bat_stat(bat)
        _row(r)
        _w(term.dim+"│"+term.normal
           + star + nc + f"{name:<18}" + term.normal
           + term.dim + " " + stat + term.normal
           + term.move_x(W-1) + term.dim+"│"+term.normal); r += 1
    box_div(r); r += 1

    # ── Bowling ───────────────────────────────────────────────────────────
    _row(r)
    _w(term.dim+"│"+term.normal
       + term.bold + " BOWLING" + " "*18 + " O - M - R - W    eco"[:W-28] + term.normal
       + term.dim+"│"+term.normal); r += 1
    bl = lv["bowl"]
    box_row(r, f"  {_bowl_name(bl):<18}", _bowl_stat(bl),
            lc=term.white, rc=term.dim); r += 1
    box_div(r); r += 1

    # ── Partnership ───────────────────────────────────────────────────────
    part = lv["partnership"]
    pr   = part.get("runs",  part.get("totalRuns",  None))
    pb   = part.get("balls", part.get("totalBalls", None))
    if pr is not None:
        box_row(r, f" PARTNERSHIP   {pr} runs  ({pb} balls)", "",
                lc=term.bold+term.cyan); r += 1
        box_div(r); r += 1

    # ── This over ─────────────────────────────────────────────────────────
    ov = lv["this_over"]
    if ov:
        _row(r)
        _w(term.dim+"│"+term.normal + term.bold+" THIS OVER  "+term.normal)
        for b in ov[:10]:
            raw = b.get("score", b.get("ballStr", b)) if isinstance(b, dict) else b
            _w(ball_fmt(str(raw)))
        _w(term.move_x(W-1) + term.dim+"│"+term.normal); r += 1
        box_div(r); r += 1

    # ── Run rates + chase ─────────────────────────────────────────────────
    crr_s = fmt_r(lv["crr"])
    rrr_s = fmt_r(lv["rrr"])
    tgt   = lv["target"]
    need  = lv["need"]
    bleft = lv["balls_left"]

    if tgt and need:
        try:    ov_left = f"{int(bleft)//6}.{int(bleft)%6} ov"
        except: ov_left = "?"
        box_row(r,
                f" TARGET  {tgt}    NEED  {need} off {bleft} balls ({ov_left})",
                "", lc=term.bold+term.yellow); r += 1
        box_div(r); r += 1

    try:    rrr_hi = float(rrr_s) > float(crr_s)
    except: rrr_hi = False

    box_row(r,
            f" CRR  {crr_s}",
            f"RRR  {rrr_s} ",
            lc=term.bold+term.white,
            rc=term.bold+(term.red if rrr_hi else term.green)); r += 1
    box_bot(r); r += 1

    # ── Commentary ────────────────────────────────────────────────────────
    comms = lv["commentary"]
    if comms:
        box_top(r, "LIVE COMMENTARY"); r += 1
        for text, event in comms[:6]:
            ec = {
                "FOUR":   term.green,
                "SIX":    term.yellow,
                "WICKET": term.red,
            }.get(event, term.dim)
            _row(r)
            _w(term.dim+"│"+term.normal
               + ec + text[:W-2].ljust(W-2) + term.normal
               + term.dim+"│"+term.normal); r += 1
        box_bot(r); r += 1

    # ── Status + countdown ────────────────────────────────────────────────
    if lv["status"]:
        _row(r); _w(term.bold+term.yellow+f" {lv['status'][:W-2]}"+term.normal); r += 1

    now     = datetime.now().strftime("%H:%M:%S")
    elapsed = int(time.time() - (state["last_refresh"] or time.time()))
    nxt     = max(0, REFRESH_SECS - elapsed)
    _row(r)
    _w(term.dim
       + f"  {now}  •  refreshes in {nxt}s  •  req: {state['req_count']}/100"
       + "   [M] matches  [R] refresh  [Q] quit"
       + term.normal)
    sys.stdout.flush()


def _draw_footer(y):
    _row(y)
    _w(term.reverse + " [Q] Quit   [R] Refresh   [M] Match list " + term.normal)


# ─────────────────────────────────────────────────────────────────────────────
# Background refresh thread
# ─────────────────────────────────────────────────────────────────────────────
_stop = threading.Event()

def _bg_worker():
    while not _stop.is_set():
        key = state["api_key"]
        if key:
            if state["mode"] == "select":
                ms = fetch_live_matches(key)
                if not ms:
                    ms = fetch_recent_matches(key)
                if ms:
                    state["matches"] = ms
                    state["error"]   = None
            elif state["mode"] == "live" and state["selected"]:
                mid  = state["selected"]["id"]
                sc   = fetch_scorecard(key, mid)
                cm   = fetch_commentary(key, mid)
                mi   = fetch_match_info(key, mid)
                if sc or cm:
                    state["live"]  = parse_live(sc, cm, mi)
                    state["error"] = None
            state["last_refresh"] = time.time()
        _stop.wait(REFRESH_SECS)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog="howzzat",
        description="Live cricket scores in your terminal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Get a free API key (100 req/day) at:
              https://rapidapi.com/cricketapilive/api/cricbuzz-cricket
            Key is saved to ~/.howzzat after first use.
        """),
    )
    parser.add_argument("--key", metavar="RAPIDAPI_KEY",
                        help="Set/update your RapidAPI key")
    args = parser.parse_args()

    key = args.key or load_key()
    if args.key:
        save_key(args.key)
        key = args.key

    def _exit(sig=None, frame=None):
        _stop.set()
        _w(term.normal + term.clear)
        sys.stdout.flush()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _exit)
    signal.signal(signal.SIGTERM, _exit)

    with term.fullscreen(), term.cbreak(), term.hidden_cursor():

        # ── Setup screen (no key yet) ─────────────────────────────────────
        if not key:
            draw_setup_screen()
            buf = ""
            while True:
                k  = term.inkey(timeout=None)
                ks = str(k)
                if k.name in ("KEY_ENTER", "KEY_RETURN") or ks in ("\n", "\r"):
                    buf = buf.strip()
                    if len(buf) > 10:
                        save_key(buf)
                        key = buf
                        state["api_key"] = key
                        break
                elif k.name == "KEY_BACKSPACE":
                    buf = buf[:-1]
                    _row(20)
                    _w(f"  API Key: {term.bold}{buf}  {term.normal}")
                    sys.stdout.flush()
                elif ks.lower() == "q" or k.name == "KEY_ESCAPE":
                    _exit()
                elif ks.isprintable():
                    buf += ks
                    _w(ks)
                    sys.stdout.flush()

        state["api_key"] = key

        # ── Initial load ──────────────────────────────────────────────────
        _w(term.clear)
        r = draw_logo(0) + 1
        _row(r); _w(term.dim + "  Fetching live matches…" + term.normal)
        sys.stdout.flush()

        ms = fetch_live_matches(key)
        if not ms:
            ms = fetch_recent_matches(key)
        state["matches"]      = ms
        state["last_refresh"] = time.time()
        state["mode"]         = "select"

        # ── Background thread ─────────────────────────────────────────────
        t = threading.Thread(target=_bg_worker, daemon=True)
        t.start()

        # ── Event loop ────────────────────────────────────────────────────
        input_buf = ""
        while True:
            if state["mode"] == "select":
                draw_select_screen(input_buf)
                k  = term.inkey(timeout=1)
                if not k: continue
                ks = str(k)

                if ks.lower() == "q":
                    _exit()
                elif ks.lower() == "r":
                    state["error"] = None
                    ms = fetch_live_matches(key)
                    if not ms: ms = fetch_recent_matches(key)
                    state["matches"]      = ms
                    state["last_refresh"] = time.time()
                    input_buf = ""
                elif ks.isdigit():
                    input_buf += ks
                elif k.name in ("KEY_BACKSPACE",) and input_buf:
                    input_buf = input_buf[:-1]
                elif ks in ("\n", "\r") or k.name in ("KEY_ENTER", "KEY_RETURN"):
                    try:
                        idx = int(input_buf) - 1
                        if 0 <= idx < len(state["matches"]):
                            state["selected"] = state["matches"][idx]
                            state["mode"]     = "live"
                            state["live"]     = None
                            mid = state["selected"]["id"]
                            sc  = fetch_scorecard(key, mid)
                            cm  = fetch_commentary(key, mid)
                            mi  = fetch_match_info(key, mid)
                            state["live"]         = parse_live(sc, cm, mi)
                            state["last_refresh"] = time.time()
                    except (ValueError, TypeError):
                        pass
                    input_buf = ""

            elif state["mode"] == "live":
                # Manual auto-refresh (background thread also does it)
                if (state["last_refresh"]
                        and time.time() - state["last_refresh"] >= REFRESH_SECS):
                    mid = state["selected"]["id"]
                    sc  = fetch_scorecard(key, mid)
                    cm  = fetch_commentary(key, mid)
                    mi  = fetch_match_info(key, mid)
                    if sc or cm:
                        state["live"] = parse_live(sc, cm, mi)
                    state["last_refresh"] = time.time()

                draw_live_screen()
                k  = term.inkey(timeout=1)
                if not k: continue
                ks = str(k)

                if ks.lower() == "q":
                    _exit()
                elif ks.lower() == "m":
                    state["mode"]     = "select"
                    state["selected"] = None
                    state["live"]     = None
                    input_buf         = ""
                elif ks.lower() == "r":
                    mid = state["selected"]["id"]
                    sc  = fetch_scorecard(key, mid)
                    cm  = fetch_commentary(key, mid)
                    mi  = fetch_match_info(key, mid)
                    if sc or cm:
                        state["live"] = parse_live(sc, cm, mi)
                    state["last_refresh"] = time.time()


if __name__ == "__main__":
    main()
