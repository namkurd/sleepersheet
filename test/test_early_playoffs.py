"""Lifetime's playoff games must reconcile with the Head-to-Head tool's playoff records for 2011 onward
(2010's single final is not part of Lifetime), and the 2011-2012 champions / runners-up must be the known ones.

    python3 test/test_early_playoffs.py [path/to/playoff_baseline.tsv]

Without an argument it reads ../Sleeper-Head-to-Head/playoff_baseline.tsv, then the file on GitHub.
"""
import collections
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://raw.githubusercontent.com/namkurd/Sleeper-Head-to-Head/main/playoff_baseline.tsv"
FIRST = 2011


def baseline(src):
    if src and os.path.exists(src):
        text = open(src, encoding="utf-8").read()
    elif os.path.exists(os.path.join(ROOT, "..", "Sleeper-Head-to-Head", "playoff_baseline.tsv")):
        text = open(os.path.join(ROOT, "..", "Sleeper-Head-to-Head", "playoff_baseline.tsv"), encoding="utf-8").read()
    else:
        text = urllib.request.urlopen(URL, timeout=30).read().decode()
    rows = []
    for line in text.splitlines()[1:]:
        c = line.split("\t")
        if len(c) >= 4 and int(c[0]) >= FIRST:
            name = lambda n: "Haan" if n == "Rohaan" else n   # same person
            rows.append((int(c[0]), int(c[1]), name(c[2]), name(c[3])))
    return rows


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    standings = json.load(open(os.path.join(ROOT, "data", "standings.json")))
    ours = sorted((g["season"], g["week"], g["winner"], g["loser"]) for g in standings["playoff_games"] if g["season"] >= FIRST)
    theirs = sorted(baseline(src))
    bad = 0

    def check(name, got, want):
        nonlocal bad
        ok = got == want
        bad += not ok
        print("PASS" if ok else "FAIL", name, "" if ok else "-> %s (want %s)" % (got, want))

    check("same playoff games as Head-to-Head, 2011 on (%d)" % len(theirs), ours, theirs)
    rec = lambda games: {m: (sum(1 for g in games if g[2] == m), sum(1 for g in games if g[3] == m)) for m in {x for g in games for x in g[2:]}}
    check("same playoff W-L for every manager", rec(ours), rec(theirs))
    early = [g for g in ours if g[0] <= 2012]
    final = {y: max((g for g in early if g[0] == y), key=lambda g: g[1]) for y in (2011, 2012)}
    check("2011 final: Ryan over Alex", final[2011][2:], ("Ryan", "Alex"))
    check("2012 final: Ankit over Steven", final[2012][2:], ("Ankit", "Steven"))
    stubs = {s["season"]: s for s in standings["seasons"] if s.get("playoff_only")}
    check("2011 and 2012 are playoffs-only seasons with no regular-season rows", sorted(stubs), [2011, 2012])
    check("their rows are empty", [len(s["rows"]) for s in stubs.values()], [0, 0])
    check("all-time regular season still starts in 2013", standings["all_time"]["first_season"], 2013)
    sys.exit(1 if bad else 0)


main()
