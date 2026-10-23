# polarka-ice

A small static page that lists the youth-practice ("Přípravka") bookings from the
[Hala Polárka reservation calendar](https://rezervace.halapolarka.cz/?p=LP) and checks them against the expected schedule.
It shows a warning for a booking at an unexpected time and for an expected booking that is missing.
A second page (`zapasy.html`) lists the upcoming matches of HC Frýdek-Místek from
[hokej.hcf-m.cz](https://hokej.hcf-m.cz/zapasy.asp?sezona=2027), and a third page (`nhl.html`) lists the NHL games of the
coming week (all teams, in Prague time) from the public NHL web API.
The page text is in Czech; the code is in English.

## How it works

`generate.py` downloads the calendar, picks the bookings named "Přípravka", "1+2" or "1+2+3", compares them with the
expected times and writes `site/index.html` and `site/calendar.ics`. It also reads the club's matches table (which is in
windows-1250) and the NHL schedule and writes `site/zapasy.html` and `site/nhl.html`; if one of those sources is down, its page
shows a notice and the bookings are still updated. A GitHub Actions workflow
(`.github/workflows/pages.yml`) runs it every 15 minutes and publishes `site/` with GitHub Pages.
If the calendar cannot be fetched or its format changes, the run fails and the last good page stays online.

## NHL team logos

`logos/nhl/` holds the light and dark SVG logo of every NHL team, so the page does not load images from other servers.
`update_logos.py` downloads the missing ones (run it when a team is added or moved; delete a file first to replace it).
A team without a logo is shown without one and `generate.py` prints a warning.

## Run it locally

```bash
python3 test_generate.py                   # tests, no network needed
python3 generate.py                        # writes site/
python3 -m http.server -d site             # preview at http://localhost:8000
```

Python 3.9+ with the standard library only. The expected times are in `EXPECTED` in `generate.py`.

## Notes

- The NHL team logos belong to the NHL and its teams (trademarks). They only identify the teams on the NHL page and are not
  covered by any license of this repository.
- The club logo (`logo.png`, `apple-touch-icon.png`) belongs to HC Frýdek-Místek. It is only a decoration of the page
  and is not covered by any license of this repository.
- The booking data comes from the Hala Polárka reservation system and the matches from the club website.
- The NHL data comes from `api-web.nhle.com`, a public but unofficial and undocumented API that may change or limit requests.
  It answers 403 to Python's default User-Agent, so `generate.py` sends its own.
- The season in the matches URL is chosen by month (a new season from July, `matches_url` in `generate.py`).
