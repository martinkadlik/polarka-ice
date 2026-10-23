#!/usr/bin/env python3
"""Generates a static page with the "Přípravka" bookings from the Hala Polárka calendar into site/ (for GitHub Pages).
Run: python3 generate.py      Preview: python3 -m http.server -d site"""
import datetime as dt, hashlib, html as H, json, os, re, shutil, time, unicodedata, urllib.request
from zoneinfo import ZoneInfo

PRAGUE = ZoneInfo("Europe/Prague")
URL = "https://rezervace.halapolarka.cz/?p=LP"

def parse_calendar(src):
    days = []
    for row in re.findall(r"<tr>(<th class=\"date\".*?)</tr>", src, re.S):
        day = " ".join(re.sub(r"<[^>]+>", " ", re.search(r"<th class=\"date\".*?</th>", row, re.S).group(0)).split())
        events = [" ".join(e.split()) for e in re.findall(r'<div class="full2-div"[^>]*>([^<]+)</div>', row)]
        days.append((day, events))
    if not days:  # calendar format changed: better a failed run than an empty page
        raise ValueError("no days found in the calendar, did its format change?")
    return days

# the NHL API answers 403 to Python's default User-Agent, so we identify ourselves honestly
USER_AGENT = "polarka-ice (+https://github.com/martinkadlik/polarka-ice)"

def fetch(url, encoding, attempts=3):
    for n in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            return urllib.request.urlopen(request, timeout=15).read().decode(encoding)
        except OSError:  # network blip: retry, so a short outage does not fail the run (and send an alert e-mail)
            if n == attempts - 1:
                raise
            time.sleep(10)

def fetch_calendar():
    return parse_calendar(fetch(URL, "utf-8"))

def strip_accents(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))

# bookings named "1+2" and "1+2+3" (without the word Přípravka); 1+2 must not be part of e.g. 11+2 or 5+1+2
ONE_PLUS_TWO = re.compile(r"(?<![\d+])1\s*\+\s*2(?!\d)")

def matches(event):
    return "pripravka" in strip_accents(event) or ONE_PLUS_TWO.search(event)

# expected times per weekday (names as in the source calendar); a booking outside them
# (or on a day with none expected) gets a warning
EXPECTED = {"Sobota": {"07:30-08:30"}, "Pondělí": {"06:00-07:30", "17:00-18:00"}, "Středa": {"13:45-14:45"}}
TIME_RANGE = re.compile(r"(\d{1,2})[:.](\d{2})\s*-\s*(\d{1,2})[:.](\d{2})")
DATE = re.compile(r"(\d+)\.\s*(\d+)\.\s*(\d{4})")
TIME_IN_TITLE = re.compile(r"\s*\(?\s*" + TIME_RANGE.pattern + r"\s*\)?")  # the time (and its brackets) in an event name

def time_range(event):
    m = TIME_RANGE.search(event)
    return m and f"{int(m[1]):02}:{m[2]}-{int(m[3]):02}:{m[4]}"

def off_schedule(day, event):
    return time_range(event) not in EXPECTED.get(day.split()[0], ())

def missing(day, events):
    return sorted(EXPECTED.get(day.split()[0], set()) - {time_range(e) for e in events})

def title(event):
    return TIME_IN_TITLE.sub("", event).strip(" -–") or event

def select_days(days):
    """Days with Přípravka bookings, each checked against the expected times (off_schedule, missing)."""
    result = []
    for day, events in days:
        events = [e for e in events if matches(e)]
        absent = missing(day, events)
        if events or absent:
            m = DATE.search(day)
            if not m:
                raise ValueError(f"unknown date format: {day!r}")
            result.append(dict(day=day, date=dt.date(int(m[3]), int(m[2]), int(m[1])), missing=absent,
                               events=[(e, off_schedule(day, e)) for e in events]))
    return result

MATCHES_URL = "https://hokej.hcf-m.cz/zapasy.asp?sezona={}"
START_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")
WEEKDAYS = ["Pondělí", "Úterý", "Středa", "Čtvrtek", "Pátek", "Sobota", "Neděle"]

def matches_url(now):
    # shortcut: the season is chosen by month (a new one from July), so the club site must have it by then
    return MATCHES_URL.format(now.year + (now.month >= 7))

def clean_cell(cell):
    return " ".join(H.unescape(re.sub(r"<[^>]+>", " ", cell)).replace("\xa0", " ").split())

def parse_matches(src):
    """Upcoming matches from the club table: they end with a start time instead of a result."""
    if not re.search(r"<th>\s*kolo\s*</th>", src):
        raise ValueError("matches table not found, did the page format change?")
    result = []
    for side, row in re.findall(r'<tr[^>]*class="(doma|venku)"[^>]*>(.*?)</tr>', src, re.S):
        cells = [clean_cell(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 6 or not START_TIME.match(cells[-1]):
            continue  # a played match (it ends with a result)
        date, start = DATE.search(cells[1]), START_TIME.match(cells[-1])
        if not date:
            raise ValueError(f"unknown date format: {cells[1]!r}")
        result.append(dict(date=dt.date(int(date[3]), int(date[2]), int(date[1])), time=f"{int(start[1]):02}:{start[2]}",
                           round=cells[0].rstrip("."), note=f'{cells[0].rstrip(".")}. kolo', home=cells[3], away=cells[4], side=side,
                           opponent=cells[4] if side == "doma" else cells[3]))
    return result

def fetch_matches(now):
    return parse_matches(fetch(matches_url(now), "cp1250"))

def upcoming(matches, today):
    return sorted((m for m in matches if m["date"] >= today), key=lambda m: (m["date"], m["time"]))

NHL_URL = "https://api-web.nhle.com/v1/schedule/now"  # redirects to the dated URL and returns a week of games
NHL_DAYS = 7  # the window ends 6 days after today: the last Prague day of one API week would be incomplete

def parse_nhl(src, now):
    """Upcoming NHL games of the coming days in Prague time, in the same shape as parse_matches."""
    week = json.loads(src).get("gameWeek")
    if not week:
        raise ValueError("no gameWeek in the NHL schedule, did the format change?")
    last = now.date() + dt.timedelta(days=NHL_DAYS - 1)
    name = lambda team: f'{team["placeName"]["default"]} {team["commonName"]["default"]}'
    result = []
    for day in week:
        for g in day["games"]:
            if g["gameState"] not in ("FUT", "PRE"):  # not started yet
                continue
            start = dt.datetime.fromisoformat(g["startTimeUTC"].replace("Z", "+00:00")).astimezone(PRAGUE)
            if start >= now and start.date() <= last:
                result.append(dict(date=start.date(), time=f"{start:%H:%M}", home=name(g["homeTeam"]), away=name(g["awayTeam"]),
                                   side=None, note=g.get("venue", {}).get("default", "")))
    return sorted(result, key=lambda m: (m["date"], m["time"]))

def fetch_nhl(now):
    return parse_nhl(fetch(NHL_URL, "utf-8"), now)

def day_card(d):
    esc = H.escape
    rows, all_ok = [], not d["missing"]
    for event, off in d["events"]:
        t = time_range(event)
        all_ok &= not off
        rows.append(f'<li class="{"warn" if off else "ok"}"><time>{t or "—"}</time>'
                    f'<span>{esc(title(event))}</span><i>{"⚠️" if off else "🏒"}</i></li>')
    for t in d["missing"]:
        rows.append(f'<li class="missing"><time>{t}</time><span>Chybí rezervace</span><i>⚠️</i></li>')
    heading = re.sub(r"\s*\d{4}$", "", d["day"])
    return (f'<section class="day{" all-ok" if all_ok else ""}" data-date="{d["date"].isoformat()}">'
            f'<h2><span>{esc(heading)}</span></h2><ul>{"".join(rows)}</ul></section>')

def summary(days):
    bad = [d for d in days if d["missing"] or any(off for _, off in d["events"])]
    if not bad:
        return '<p class="summary good">🏒 Vše podle plánu</p>'
    count = sum(len(d["missing"]) + sum(off for _, off in d["events"]) for d in bad)
    names = ", ".join(dict.fromkeys(d["day"].split()[0] for d in bad))
    return f'<p class="summary bad">⚠️ {count} upozornění: {H.escape(names)}</p>'

SVG = '<svg width=22 height=22 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round aria-hidden=true class="{}">{}</svg>'
ICON_SUN = SVG.format("sun", '<circle cx=12 cy=12 r=4 /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>')
ICON_MOON = SVG.format("moon", '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>')
ICON_REFRESH = SVG.format("", '<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/>')

LIGHT = "--bg:#f4f4f7;--card:rgba(255,255,255,.88);--tx:#1b1b1f;--mut:#6b6b76;--red:#c8102e;--ok:#1e8e3e;--warn:#b45309;--warn-bg:#fff1d6;--bad:#b3261e;--bad-bg:#fde4e2;--line:#e2e2e9;--wm:.07"
DARK = "--bg:#111114;--card:rgba(28,28,33,.88);--tx:#eee;--mut:#9a9aa6;--red:#ff5a6e;--ok:#4cc16a;--warn:#ffb54d;--warn-bg:#3a2a0e;--bad:#ff8a80;--bad-bg:#3d1519;--line:#2c2c33;--wm:.04"
# theme: follows the system until the user toggles it; then data-theme on <html>
CSS = ":root{" + LIGHT + "}@media(prefers-color-scheme:dark){:root:not([data-theme=light]){" + DARK + "}}:root[data-theme=dark]{" + DARK + ";color-scheme:dark}:root[data-theme=light]{color-scheme:light}" + """
#theme .sun,:root[data-theme=dark] #theme .moon{display:none}:root[data-theme=dark] #theme .sun{display:block}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]) #theme .moon{display:none}:root:not([data-theme=light]) #theme .sun{display:block}}
#refresh svg,#theme svg{display:block;margin:auto}
*{box-sizing:border-box}
html{background:var(--bg)}
body{margin:0;min-height:100vh;min-height:100dvh;background:var(--bg);color:var(--tx);font:15px/1.4 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;overflow-wrap:anywhere}
body::before{content:"";position:fixed;inset:0;z-index:-1;opacity:var(--wm);background:url(logo.png) center/min(80vw,420px) no-repeat}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line)}
.bar{max-width:640px;margin:0 auto;padding:10px 16px;display:flex;align-items:center;gap:8px}
.bar img{width:48px;height:48px}.bar div{flex:1;min-width:0}
h1{margin:0;font-size:1.2em;line-height:1.1;font-weight:700}footer{margin-top:20px;text-align:center;color:var(--mut);font-size:.8em}
#refresh,#theme{min-width:44px;min-height:44px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--red);cursor:pointer}
main{max-width:640px;margin:0 auto;padding:12px 16px calc(32px + env(safe-area-inset-bottom))}
.summary{margin:4px 0 12px;padding:12px 14px;border-radius:12px;font-weight:600}
.good{background:var(--card);color:var(--ok);border:1px solid var(--ok)}.bad{background:var(--warn-bg);color:var(--warn)}
.filter{display:flex;gap:8px;margin-bottom:12px}
.filter button{flex:1;min-height:44px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--tx);font:inherit;cursor:pointer}
.filter button[aria-pressed=true]{background:var(--red);border-color:var(--red);color:#fff}
.day{background:var(--card);border:1px solid var(--line);border-radius:14px;margin-bottom:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.day.today{border-left:5px solid var(--red)}
h2{display:flex;justify-content:space-between;align-items:center;margin:0;padding:8px 14px;font-size:1.1em;color:var(--red);border-bottom:1px solid var(--line)}
h2 b{font-size:.7em;background:var(--red);color:#fff;border-radius:99px;padding:1px 10px;letter-spacing:.03em;text-transform:uppercase}
ul{list-style:none;margin:0;padding:0}
li{display:flex;align-items:center;gap:12px;padding:8px 14px;min-height:44px}li+li{border-top:1px solid var(--line)}
li time{font-size:1.05em;font-weight:700;min-width:6em;font-variant-numeric:tabular-nums}li>span{flex:1}.team{white-space:nowrap}li i{font-style:normal;color:var(--ok)}
li.warn{background:var(--warn-bg)}li.warn time{color:var(--warn)}
li.missing{background:var(--bad-bg);color:var(--bad)}li.missing time{color:var(--bad)}li.missing span{font-weight:600}
body.only .day.all-ok,body.only li.ok{display:none}
.actions{display:flex;flex-direction:column;align-items:center;gap:10px;margin-top:20px}
.btn{display:block;width:100%;max-width:360px;padding:12px;text-align:center;border:1px solid var(--red);border-radius:12px;color:var(--red);text-decoration:none;font-weight:600;background:var(--card)}
.error{padding:14px;border-radius:12px;background:var(--bad-bg);color:var(--bad)}
.tabs{display:flex;gap:16px;margin-bottom:12px;border-bottom:1px solid var(--line);overflow-x:auto;overflow-y:hidden}
.tabs a{white-space:nowrap;padding:8px 4px;color:var(--mut);text-decoration:none;font-weight:600;border-bottom:3px solid transparent}
.tabs a[aria-current=page]{color:var(--red);border-bottom-color:var(--red)}
li span small{display:block;color:var(--mut)}
.chip{font-style:normal;font-size:.75em;font-weight:700;padding:2px 10px;border-radius:99px;border:1px solid var(--line)}
.chip.doma{background:var(--red);border-color:var(--red);color:#fff}
.btn{font:inherit;font-weight:600;cursor:pointer}
body:not(.all-matches) .later{display:none}
"""

JS = """
const body=document.body,buttons=[...document.querySelectorAll('[data-filter]')];
const setFilter=only=>{body.classList.toggle('only',only);buttons.forEach(b=>b.setAttribute('aria-pressed',(b.dataset.filter=='only')==only));history.replaceState(null,'',only?'#only':location.pathname+location.search)};
buttons.forEach(b=>b.onclick=()=>setFilter(b.dataset.filter=='only'));setFilter(location.hash=='#only');
document.getElementById('refresh').onclick=()=>location.reload();
const themeBtn=document.getElementById('theme'),root=document.documentElement;
const isDark=()=>root.dataset.theme?root.dataset.theme=='dark':matchMedia('(prefers-color-scheme:dark)').matches;
themeBtn.onclick=()=>{root.dataset.theme=isDark()?'light':'dark';try{localStorage.theme=root.dataset.theme}catch(e){}};
const checkStale=()=>{const h=(Date.now()-new Date(document.querySelector('footer time').dateTime))/36e5;
if(h>3){const s=document.getElementById('stale');s.textContent='⚠️ Údaje nemusí být aktuální, poslední aktualizace před '+Math.floor(h)+' h.';s.hidden=false}};checkStale();
// the page can be up to an hour old, so "today"/"tomorrow" is worked out here, not at build time
const today=new Date().toLocaleDateString('sv',{timeZone:'Europe/Prague'});  // YYYY-MM-DD
document.querySelectorAll('.day').forEach(d=>{const diff=Math.round((new Date(d.dataset.date)-new Date(today))/864e5);
if(diff==0)d.classList.add('today');const label={0:'Dnes',1:'Zítra'}[diff];if(label)d.querySelector('h2').insertAdjacentHTML('beforeend','<b>'+label+'</b>')});
const more=document.getElementById('more');
if(more)more.onclick=()=>{body.classList.add('all-matches');more.parentElement.remove()};
let startY=null;  // pull down at the top of the page = reload (a home-screen shortcut has no address bar)
addEventListener('touchstart',e=>{startY=scrollY==0?e.touches[0].clientY:null},{passive:true});
addEventListener('touchend',e=>{if(startY!==null&&e.changedTouches[0].clientY-startY>90)location.reload()});
"""

def shell(title, heading, active, content, now):
    tabs = "".join(f'<a href="{href}"{" aria-current=page" if key == active else ""}>{label}</a>'
                   for key, href, label in (("bookings", "index.html", "Rezervace"), ("matches", "zapasy.html", "Zápasy A-tým"), ("nhl", "nhl.html", "Zápasy NHL")))
    return f"""<!doctype html><html lang=cs><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{title}</title><meta name=color-scheme content="light dark">
<meta name=theme-color content="#f4f4f7" media="(prefers-color-scheme: light)"><meta name=theme-color content="#111114" media="(prefers-color-scheme: dark)">
<meta name=apple-mobile-web-app-capable content=yes><meta name=mobile-web-app-capable content=yes>
<link rel=icon href=logo.png><link rel=apple-touch-icon href=apple-touch-icon.png>
<script>try{{if(localStorage.theme)document.documentElement.dataset.theme=localStorage.theme}}catch(e){{}}</script>
<style>{CSS}</style>
<header><div class=bar><img src=logo.png alt="HC Frýdek-Místek"><div><h1>{heading}</h1></div><button id=theme aria-label="Přepnout světlý/tmavý režim">{ICON_SUN}{ICON_MOON}</button><button id=refresh aria-label="Obnovit">{ICON_REFRESH}</button></div></header>
<main><nav class=tabs>{tabs}</nav><p class="summary bad" id=stale hidden></p>{content}
<footer>Poslední aktualizace: <time datetime="{now.isoformat(timespec="seconds")}">{now.day}. {now.month}. {now.year} {now:%H:%M}</time></footer></main>
<script>{JS}</script>""".encode()

def render_page(days):
    now = dt.datetime.now(PRAGUE)
    if days:
        content = (summary(days) + '<div class="filter"><button data-filter=all>Vše</button><button data-filter=only>Jen upozornění</button></div>'
                   + "".join(day_card(d) for d in days))
    else:
        content = '<p class="error">V nejbližších dnech nejsou žádné rezervace Přípravky.</p>'
    content += f"""<div class=actions>
<a class=btn href="{URL}" target=_blank rel=noopener>Otevřít celý kalendář ↗</a>
<a class=btn href="calendar.ics">Přidat do kalendáře (.ics)</a></div>"""
    return shell("Události - Hala Polárka", "Hala Polárka - Přípravka", "bookings", content, now)

SHOWN_MATCHES = 5  # the rest is hidden behind "Zobrazit vše"

def match_cards(matches):
    esc = H.escape
    by_date = {}
    for n, m in enumerate(matches):
        by_date.setdefault(m["date"], []).append((n, m))
    cards = []
    for date, items in by_date.items():
        rows = []
        for n, m in items:
            teams = " - ".join(f'<span class=team>{esc(t) if m["side"] is None or t == m["opponent"] else f"<strong>{esc(t)}</strong>"}</span>'
                               for t in (m["home"], m["away"]))
            chip = f'<em class="chip {m["side"]}">{"Doma" if m["side"] == "doma" else "Venku"}</em>' if m["side"] else ""
            note = "<small>" + esc(m["note"]) + "</small>" if m["note"] else ""
            rows.append(f'<li class="{"later" if n >= SHOWN_MATCHES else ""}"><time>{m["time"]}</time>'
                        f'<span>{teams}{note}</span>{chip}</li>')
        heading = f"{WEEKDAYS[date.weekday()]} {date.day}. {date.month}."
        cards.append(f'<section class="day{" later" if items[0][0] >= SHOWN_MATCHES else ""}" data-date="{date.isoformat()}">'
                     f'<h2><span>{heading}</span></h2><ul>{"".join(rows)}</ul></section>')
    return "".join(cards)

def render_match_page(active, title, heading, matches, source_url, source_label, empty_text):
    """matches: the upcoming matches, or None when their source could not be read."""
    now = dt.datetime.now(PRAGUE)
    if matches is None:
        content = '<p class="error">Zápasy se teď nepodařilo načíst, zkuste to později.</p>'
    elif not matches:
        content = f'<p class="error">{empty_text}</p>'
    else:
        content = match_cards(matches)
        if len(matches) > SHOWN_MATCHES:
            content += f'<div class=actions><button id=more class=btn>Zobrazit vše ({len(matches)})</button></div>'
    content += f'<div class=actions><a class=btn href="{source_url}" target=_blank rel=noopener>{source_label} ↗</a></div>'
    return shell(title, heading, active, content, now)

def render_matches(matches):
    return render_match_page("matches", "Zápasy - HC Frýdek-Místek", "HC Frýdek-Místek - zápasy", matches,
                             matches_url(dt.datetime.now(PRAGUE)), "Celý rozpis zápasů", "Žádné nadcházející zápasy.")

def render_nhl(matches):
    return render_match_page("nhl", "Zápasy NHL", "NHL - zápasy", matches, "https://www.nhl.com/schedule",
                             "Celý rozpis NHL", "V nejbližších dnech nejsou žádné zápasy NHL.")

def build_ics(days):
    esc = lambda t: re.sub(r"([\\,;])", r"\\\1", t)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines, seen = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Hala Polarka//CS", "CALSCALE:GREGORIAN"], set()
    for d in days:
        for event, _ in d["events"]:
            t = time_range(event)
            if not t:
                continue
            start, end = (dt.datetime.combine(d["date"], dt.time.fromisoformat(x)) for x in t.split("-"))
            if end <= start:  # e.g. 23:00-00:15 ends the next day
                end += dt.timedelta(days=1)
            uid = hashlib.md5(f"{start}{event}".encode()).hexdigest() + "@polarka"
            if uid in seen:  # 25 Oct 2026 appears twice in the calendar (clock change)
                continue
            seen.add(uid)
            lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}", f"DTSTART:{start:%Y%m%dT%H%M%S}",
                      f"DTEND:{end:%Y%m%dT%H%M%S}", f"SUMMARY:{esc(title(event))}",
                      "LOCATION:Hala Polárka", "END:VEVENT"]  # shortcut: floating times (no time zone), fine for a Czech-only audience
    return ("\r\n".join(lines + ["END:VCALENDAR"]) + "\r\n").encode()

def main():
    now = dt.datetime.now(PRAGUE)
    days = select_days(fetch_calendar())  # raises if the calendar is unavailable, so an error page is never deployed
    def optional(label, load):  # a problem on a matches source must not block the bookings page
        try:
            return load()
        except (OSError, ValueError, KeyError) as e:
            print(f"::warning::{label} not updated: {e}")
            return None
    matches = optional("matches", lambda: upcoming(fetch_matches(now), now.date()))
    nhl = optional("NHL games", lambda: fetch_nhl(now))
    os.makedirs("site", exist_ok=True)
    open("site/index.html", "wb").write(render_page(days))
    open("site/zapasy.html", "wb").write(render_matches(matches))
    open("site/nhl.html", "wb").write(render_nhl(nhl))
    open("site/calendar.ics", "wb").write(build_ics(days))
    for f in ("logo.png", "apple-touch-icon.png"):
        shutil.copy(f, "site")

if __name__ == "__main__":
    main()
