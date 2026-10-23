"""Run: python3 test_generate.py  (no network; the calendar is replaced by sample data)"""
import generate as G

# parsing the calendar HTML (structure as on rezervace.halapolarka.cz)
src = ('<tr><th class="date" colspan="4"><strong>Sobota</strong><br /><nobr>24. 10. 2026</nobr></th>'
       '<td class="full"><div class="full2-div" style="x">Přípravka (07:30-08:30) </div></td>'
       '<td class="full"><div class="full2-div" style="x"></div></td></tr>')
assert G.parse_calendar(src) == [("Sobota 24. 10. 2026", ["Přípravka (07:30-08:30)"])]
try:
    G.parse_calendar("<html>other format</html>"); raise SystemExit("should have failed")
except ValueError:
    pass
# which bookings are picked
assert all(G.matches(e) for e in ["Přípravka (07:30-08:30)", "pripravka", "1+2 (14:00-15:15)", "1+2+3 (06:00-07:30)", "1 + 2"])
assert not any(G.matches(e) for e in ["11+2", "5+1+2", "1+23", "Muži A"])
# schedule check
assert not G.off_schedule("Sobota 24. 10. 2026", "Přípravka (07:30-08:30)")
assert G.off_schedule("Středa 28. 10. 2026", "1+2 (14:00-15:15)")      # wrong time
assert G.off_schedule("Úterý 27. 10. 2026", "1+2 (13:45-14:45)")       # a day with nothing expected
assert G.off_schedule("Sobota 24. 10. 2026", "Přípravka")              # no time at all
assert G.missing("Pondělí 26. 10. 2026", ["1+2+3 (06:00-07:30)"]) == ["17:00-18:00"]
# page and export on sample data (25 Oct twice, as in the real calendar)
days = G.select_days([("Sobota 24. 10. 2026", ["Přípravka (07:30-08:30)"]), ("Středa 28. 10. 2026", ["1+2 (14:00-15:15)"]),
                      ("Neděle 25. 10. 2026", ["Přípravka (23:00-00:15)"]), ("Neděle 25. 10. 2026", ["Přípravka (23:00-00:15)"])])
html = G.render_page(days).decode()
assert "Poslední aktualizace" in html and "Chybí rezervace" in html and 'data-date="2026-10-24"' in html
ics = G.build_ics(days).decode()
assert ics.count("BEGIN:VEVENT") == 3                                  # the duplicate Sunday is merged
assert "DTSTART:20261025T230000" in ics and "DTEND:20261026T001500" in ics  # past midnight
assert "V nejbližších dnech" in G.render_page([]).decode()
# a changed date format fails with a clear error
try:
    G.select_days([("Sobota", ["Přípravka (07:30-08:30)"])]); raise SystemExit("should have failed")
except ValueError:
    pass
# the page script looks these elements up by name, so the HTML must contain them
for name in ("id=theme", "id=refresh", "id=stale", "data-filter=only", "data-filter=all", 'class="day'):
    assert name in html, name
# a short network outage is retried, a long one still fails
class Reply:
    def read(self):
        return src.encode()
calls = []
def flaky(url, timeout):
    calls.append(url)
    if len(calls) < 3:
        raise OSError("network down")
    return Reply()
G.urllib.request.urlopen, G.time.sleep = flaky, lambda s: None
assert G.fetch_calendar() == G.parse_calendar(src) and len(calls) == 3
def down(url, timeout):
    raise OSError("network down")
G.urllib.request.urlopen = down
try:
    G.fetch_calendar(); raise SystemExit("should have failed")
except OSError:
    pass

# --- matches page (the club site is windows-1250, rows are in the table with "doma"/"venku" classes)
import datetime as dt
def row(cls, rnd, date, stadium, home, away, last, onclick=""):
    return (f'<tr{onclick} class="{cls}"><td>{rnd}</td><td>{date}</td><td>{stadium}</td>'
            f'<td>&nbsp;{home}</td><td class="bold">&nbsp;{away}</td><td>&nbsp;{last}</td></tr>')
rows = [
    row("doma", "2.", "so 12.9.2026", "Hala Polárka", "Frýdek-Místek", "Zlín", '<a href="x"><b>3:2<span>p</span></b></a>', ' onclick="x"'),  # played
    row("doma", "16.", "ne 25.10.2026", "", "Frýdek-Místek", "Třebíč", "17:00"),
    row("venku", "15.", "po 26.10.2026", "", "Zlín", "Frýdek-Místek", "17:30"),
    row("doma", "13.", "st 28.10.2026", "", "Frýdek-Místek", "Kolín", "9:00"),                    # a round out of order, one-digit hour
    row("venku", "18.", "so 31.10.2026", "", "Havířov", "Frýdek-Místek", "17:00"),
    row("doma", "19.", "ne 1.11.2026", "", "Frýdek-Místek", "Sokolov", "17:00"),
    row("doma", "20.", "st 4.11.2026", "", "Frýdek-Místek", "Tábor", "17:00"),
]
table = "<table><thead><tr><th>kolo</th><th>datum</th></tr></thead>" + "".join(rows) + "</table>"
raw = table.encode("cp1250")                                  # as the club site sends it
parsed = G.parse_matches(raw.decode("cp1250"))
assert len(parsed) == 6 and all(m["date"] >= dt.date(2026, 10, 25) for m in parsed)   # the played match is ignored
first = parsed[0]
assert (first["time"], first["round"], first["side"], first["opponent"]) == ("17:00", "16", "doma", "Třebíč")
away = parsed[1]
assert (away["side"], away["home"], away["opponent"]) == ("venku", "Zlín", "Zlín")
assert parsed[2]["time"] == "09:00"
assert G.parse_matches("<table><thead><tr><th>kolo</th></tr></thead></table>") == []       # a season with no matches yet
try:
    G.parse_matches("<html>other format</html>"); raise SystemExit("should have failed")
except ValueError:
    pass
today = dt.date(2026, 10, 26)
up = G.upcoming(parsed, today)
assert [m["date"].day for m in up] == [26, 28, 31, 1, 4] and up[0]["opponent"] == "Zlín"   # sorted by date, past ones dropped
assert G.matches_url(dt.datetime(2026, 10, 1)).endswith("sezona=2027") and G.matches_url(dt.datetime(2027, 3, 1)).endswith("sezona=2027")
assert G.matches_url(dt.datetime(2027, 7, 1)).endswith("sezona=2028")
# downloading decodes windows-1250 (a UTF-8 decode would garble "Třebíč")
class ClubReply:
    def read(self):
        return raw
G.urllib.request.urlopen = lambda url, timeout: ClubReply()
assert G.fetch_matches(dt.datetime(2026, 10, 1))[0]["opponent"] == "Třebíč"
# rendering
page = G.render_matches(G.upcoming(parsed, dt.date(2026, 10, 25))).decode()
assert page.count('class="later"') == 1 and "Zobrazit vše (6)" in page      # 5 shown, the 6th hidden
assert 'data-date="2026-10-25"' in page and "Neděle 25. 10." in page and "<strong>Frýdek-Místek</strong>" in page and "<strong>Třebíč</strong>" not in page and "Třebíč" in page
assert "Doma" in page and "Venku" in page and 'href="index.html"' in page and 'aria-current=page>Zápasy' in page
assert "sezona=2027" in page and "Poslední aktualizace" in page
assert "Zobrazit vše" not in G.render_matches(up[:5]).decode()
assert "Žádné nadcházející zápasy" in G.render_matches([]).decode()
assert "nepodařilo načíst" in G.render_matches(None).decode()
assert 'aria-current=page>Rezervace' in G.render_page(days).decode() and "zapasy.html" in G.render_page(days).decode()

# --- NHL page (JSON from api-web.nhle.com, times in UTC)
import json
def team(place, name, abbrev=""):
    return {"placeName": {"default": place}, "commonName": {"default": name}, "abbrev": abbrev}
def game(utc, state="FUT"):
    return {"startTimeUTC": utc, "gameState": state, "homeTeam": team("Boston", "Bruins", "BOS"),
            "awayTeam": team("Toronto", "Maple Leafs", "TOR"), "venue": {"default": "TD Garden"}}
now = dt.datetime(2026, 10, 23, 20, 50, tzinfo=G.PRAGUE)
nhl_games = [
    game("2026-10-29T22:00:00Z"),                # 23:00 on the 29th, the last day of the window
    game("2026-10-23T18:00:00Z"),                # 20:00 today: already before "now"
    game("2026-10-24T00:00:00Z"),                # 02:00 on the 24th (summer time)
    game("2026-10-26T00:00:00Z"),                # 01:00 on the 26th (winter time since 25 Oct)
    game("2026-10-24T01:00:00Z", "LIVE"),        # started
    game("2026-10-24T02:00:00Z", "FINAL"),       # played
    game("2026-10-25T23:30:00Z"),                # 00:30 on the 26th
    game("2026-10-30T00:00:00Z"),                # 01:00 on the 30th: outside the 7 days
]
src_nhl = json.dumps({"gameWeek": [{"date": "2026-10-23", "games": nhl_games}]})
nhl = G.parse_nhl(src_nhl, now)
assert [(m["date"].day, m["time"]) for m in nhl] == [(24, "02:00"), (26, "00:30"), (26, "01:00"), (29, "23:00")]
assert (nhl[0]["home"], nhl[0]["away"], nhl[0]["side"], nhl[0]["note"]) == ("Boston Bruins", "Toronto Maple Leafs", None, "")   # no venue shown
for bad in ("{}", '{"gameWeek": []}'):
    try:
        G.parse_nhl(bad, now); raise SystemExit("should have failed")
    except ValueError:
        pass
requested = []
class NhlReply:
    def read(self):
        return src_nhl.encode()
G.urllib.request.urlopen = lambda request, timeout: requested.append((request.full_url, request.get_header("User-agent"))) or NhlReply()
assert G.fetch_nhl(now) == nhl and requested == [(G.NHL_URL, G.USER_AGENT)]   # sends our own User-Agent
page = G.render_nhl(nhl + nhl[:2]).decode()
assert "Zobrazit vše (6)" in page and "TD Garden" not in page and "<small>" not in page    # the venue is not shown
assert "Boston Bruins" in page and 'data-date="2026-10-24"' in page
assert "<strong>" not in page and 'class="chip' not in page      # no "our team" on this page
assert all(f'href="{p}"' in page for p in ("index.html", "zapasy.html", "nhl.html")) and "aria-current=page>Zápasy NHL" in page
assert "nhl.com/schedule" in page and "Poslední aktualizace" in page
assert "nejsou žádné zápasy NHL" in G.render_nhl([]).decode() and "nepodařilo načíst" in G.render_nhl(None).decode()
assert all('href="nhl.html"' in p for p in (G.render_page(days).decode(), G.render_matches([]).decode()))

# --- team logos (files in logos/nhl, filled by update_logos.py)
import glob, os, re
assert (nhl[0]["home_abbr"], nhl[0]["away_abbr"]) == ("BOS", "TOR")
page = G.render_nhl(nhl).decode()
assert 'src="logos/nhl/BOS_light.svg"' in page and 'src="logos/nhl/BOS_dark.svg"' in page and "loading=lazy" in page
assert page.count('<img class="logo ') == 16          # 4 games x 2 teams x (light + dark)
assert "Boston Bruins" in page and "Toronto Maple Leafs" in page and 'class="logos"' in page
assert G.logo_html("XXX") == "" and G.logo_html("") == "" and G.logo_html("../x") == ""     # unknown team or odd value: no logo
assert '<img class="logo ' not in G.render_nhl([dict(nhl[0], home_abbr="XXX", away_abbr="")]).decode()   # no crash, no broken image
assert '<img class="logo ' not in G.render_matches(up).decode() + G.render_page(days).decode()           # only the NHL page has logos
files = sorted(glob.glob("logos/nhl/*.svg"))
assert len(files) >= 64, len(files)
for path in files:
    svg = open(path, encoding="utf-8").read()
    assert svg.lstrip().startswith("<svg") and not re.search(r'<script|<foreignObject|\son\w+\s*=|href\s*=\s*["\']?https?:', svg, re.I), path
    other = path.replace("_light.svg", "_dark.svg") if path.endswith("_light.svg") else path.replace("_dark.svg", "_light.svg")
    assert os.path.exists(other), other                # both colour variants exist for every team
print("OK")
