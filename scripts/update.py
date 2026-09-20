#!/usr/bin/env python3
"""Rebuild data/standings.json for the DTF Club Lifetime Win/Loss page.

* Seasons up to `frozen_through` (data/history.json) come from the original Google Sheet and are never recomputed.
* Every later season is pulled live from the Sleeper API (regular season only, completed weeks only).
* Rumbles: +1 for every team you outscore in a week, plus 9 more if you also beat your head-to-head opponent.

Usage:
    python scripts/update.py                       # normal run (used by the GitHub Action)
    python scripts/update.py --offline raw.json    # test against a saved copy of the Sleeper responses
"""
import argparse
import datetime as dt
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.sleeper.app/v1"
DEFAULT_REGULAR_WEEKS = 14


# --------------------------------------------------------------------------- Sleeper access
def get(path):
    last = None
    for _ in range(4):
        try:
            with urllib.request.urlopen(API + path, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001 - retry any network hiccup
            last = e
    raise RuntimeError(f"Sleeper request failed for {path}: {last}")


def fetch_live(cfg, frozen_through):
    """Return {'state': ..., 'seasons': {year: {league, users, rosters, weeks}}} for all unfrozen seasons."""
    state = get("/state/nfl")
    season_now = int(state.get("league_season") or state["season"])

    # newest league: try discovery by name (so a new season is picked up automatically), fall back to config
    start_id = cfg["league_id"]
    try:
        found = get(f"/user/{cfg['discovery_user_id']}/leagues/nfl/{season_now}")
        named = [l for l in found if l.get("name") == cfg["league_name"]]
        if named:
            start_id = named[0]["league_id"]
    except Exception as e:  # noqa: BLE001
        print(f"  (league discovery skipped: {e})", file=sys.stderr)

    seasons, lid = {}, start_id
    while lid and lid != "0":
        league = get(f"/league/{lid}")
        year = int(league["season"])
        if year <= frozen_through:
            break
        users = get(f"/league/{lid}/users")
        rosters = get(f"/league/{lid}/rosters")
        with ThreadPoolExecutor(6) as ex:
            weeks = list(ex.map(lambda w, lid=lid: get(f"/league/{lid}/matchups/{w}"), range(1, 19)))
        seasons[str(year)] = dict(league=league, users=users, rosters=rosters, weeks=weeks)
        lid = league.get("previous_league_id")
    return {"state": state, "seasons": seasons}


# --------------------------------------------------------------------------- season maths
def points(m):
    """Commissioner overrides (custom_points) win over Sleeper's own score, exactly as shown in the Sleeper app."""
    p = m.get("custom_points")
    if p is None:
        p = m.get("points")
    return None if p is None else round(float(p), 2)


def regular_weeks(league):
    start = int(league["settings"].get("playoff_week_start") or 0)
    return start - 1 if start > 1 else DEFAULT_REGULAR_WEEKS


def completed_weeks(league, state, year):
    total = regular_weeks(league)
    last = league["settings"].get("last_scored_leg")
    done = total if last is None else min(int(last), total)
    if int(state.get("league_season") or state["season"]) == year and state.get("season_type", "regular") == "regular":
        done = min(done, max(int(state["week"]) - 1, 0))  # the week in progress never counts
    return total, max(done, 0)


def build_live_season(raw, year, state, owners):
    league, rosters = raw["league"], raw["rosters"]
    total, done = completed_weeks(league, state, year)
    users = {u["user_id"]: u for u in raw["users"]}
    names = {}
    for r in rosters:
        uid = r.get("owner_id")
        if uid in owners:
            names[r["roster_id"]] = owners[uid]
        else:
            disp = users.get(uid, {}).get("display_name") or f"Team {r['roster_id']}"
            names[r["roster_id"]] = disp
            print(f"  WARNING: {disp!r} (user_id {uid}) is not in data/owners.json - showing the Sleeper name", file=sys.stderr)
    n = len(rosters)
    acc = {rid: dict(name=names[rid], w=0, l=0, pf=0.0, pa=0.0, fw=0, fl=0) for rid in names}
    played = 0
    for w in range(1, done + 1):
        wk = raw["weeks"][w - 1]
        if not wk or len(wk) < n or any(points(m) is None for m in wk):
            break
        played += 1
        pts = {m["roster_id"]: points(m) for m in wk}
        by_matchup = {}
        for m in wk:
            by_matchup.setdefault(m.get("matchup_id"), []).append(m["roster_id"])
        for rid, p in pts.items():
            beaten = sum(1 for other, q in pts.items() if other != rid and q < p)
            acc[rid]["fw"] += beaten
            acc[rid]["fl"] += (n - 1) - beaten
            acc[rid]["pf"] += p
        for mid, pair in by_matchup.items():
            if mid is None or len(pair) != 2:
                continue
            a, b = pair
            acc[a]["pa"] += pts[b]
            acc[b]["pa"] += pts[a]
            if pts[a] > pts[b]:
                acc[a]["w"] += 1
                acc[b]["l"] += 1
            elif pts[b] > pts[a]:
                acc[b]["w"] += 1
                acc[a]["l"] += 1
    rows = list(acc.values())
    for r in rows:
        r["pf"], r["pa"] = round(r["pf"], 2), round(r["pa"], 2)
    return dict(teams=n, weeks=played, weeks_total=total, order="rumbles", rows=rows)


# --------------------------------------------------------------------------- derived stats
def rank_desc(values):
    return [1 + sum(1 for o in values if o > v) for v in values]


def rank_asc(values):
    return [1 + sum(1 for o in values if o < v) for v in values]


def derive(rows, max_rumbles_per_row):
    """rows: dicts with w,l,pf,pa,fw,fl + 'max_rumbles'. Adds rumbles, ranks and percentages in place."""
    for r, mx in zip(rows, max_rumbles_per_row):
        r["rumbles"] = r["fw"] + 9 * r["w"]
        r["rumble_pct"] = r["rumbles"] / mx if mx else None
        r["h2h_pct"] = r["w"] / (r["w"] + r["l"]) if (r["w"] + r["l"]) else None
        r["field_pct"] = r["fw"] / (r["fw"] + r["fl"]) if (r["fw"] + r["fl"]) else None
        r["luck"] = (r["h2h_pct"] - r["field_pct"]) if r["h2h_pct"] is not None and r["field_pct"] is not None else None
    for key, vals in (
        ("rumble_rank", rank_desc([r["rumbles"] for r in rows])),
        ("pf_rank", rank_desc([r["pf"] for r in rows])),
        ("pa_rank", rank_asc([r["pa"] for r in rows])),
    ):
        for r, v in zip(rows, vals):
            r[key] = v
    return rows


def finish_season(year, s):
    n, weeks = s["teams"], s["weeks"]
    rows = [dict(r) for r in s["rows"]]
    # Max possible rumbles per week: (n-1) teams outscored + 9 bonus = n+8. A team's games = its completed weeks.
    mx = [round((r["fw"] + r["fl"]) / (n - 1)) * (n + 8) for r in rows]
    derive(rows, mx)
    if s["order"] == "rumbles":  # standings are decided by rumbles (PF breaks ties)
        rows.sort(key=lambda r: (-r["rumbles"], -r["pf"]))
    return dict(season=int(year), teams=n, weeks_played=weeks, weeks_total=s.get("weeks_total", weeks),
                order=s["order"], complete=weeks >= s.get("weeks_total", weeks), rows=rows), mx


def all_time(seasons):
    agg = {}
    for s in seasons:
        n = s["teams"]
        for r in s["rows"]:
            a = agg.setdefault(r["name"], dict(name=r["name"], w=0, l=0, pf=0.0, pa=0.0, fw=0, fl=0, mx=0, seasons=0))
            for k in ("w", "l", "fw", "fl"):
                a[k] += r[k]
            a["pf"] += r["pf"]
            a["pa"] += r["pa"]
            a["mx"] += round((r["fw"] + r["fl"]) / (n - 1)) * (n + 8)
            a["seasons"] += 1
    rows = list(agg.values())
    for r in rows:
        r["pf"], r["pa"] = round(r["pf"], 2), round(r["pa"], 2)
    derive(rows, [r["mx"] for r in rows])
    for r in rows:
        del r["mx"]
    rows.sort(key=lambda r: (-r["rumbles"], -r["pf"]))
    return rows


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", help="JSON file with saved Sleeper data ({'state':..., 'seasons':...}) instead of calling the API")
    ap.add_argument("--frozen-through", type=int, help="testing only: override which seasons count as frozen")
    ap.add_argument("--out", default=str(ROOT / "data" / "standings.json"))
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text())
    history = json.loads((ROOT / "data" / "history.json").read_text())
    owners = json.loads((ROOT / "data" / "owners.json").read_text())["owners"]
    frozen_through = args.frozen_through or history["frozen_through"]

    if args.offline:
        live = json.loads(Path(args.offline).read_text())
    else:
        live = fetch_live(cfg, frozen_through)

    seasons = {}
    for year, s in history["seasons"].items():
        if int(year) <= frozen_through:
            seasons[year] = s
    for year, raw in live["seasons"].items():
        if int(year) > frozen_through:
            seasons[year] = build_live_season(raw, int(year), live["state"], owners)

    finished = []
    for year in sorted(seasons, key=int):
        s = seasons[year]
        if s["weeks"] == 0:
            continue  # league exists but nothing has been played yet
        fs, _ = finish_season(year, s)
        finished.append(fs)

    out = dict(
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        league_name=cfg["league_name"],
        seasons=sorted(finished, key=lambda s: -s["season"]),
        all_time=dict(first_season=finished[0]["season"], last_season=finished[-1]["season"], rows=all_time(finished)),
    )
    target = Path(args.out)
    if target.exists():  # don't touch the file (and don't create a commit) if nothing but the timestamp changed
        old = json.loads(target.read_text())
        if {k: v for k, v in old.items() if k != "generated_at"} == {k: v for k, v in out.items() if k != "generated_at"}:
            print("no changes")
            return
    target.write_text(json.dumps(out, indent=1))
    print(f"wrote {args.out}: {len(finished)} seasons, {len(out['all_time']['rows'])} people all-time")


if __name__ == "__main__":
    main()
