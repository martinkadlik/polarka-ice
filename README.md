# polarka-ice

A small static page that lists the youth-practice ("Přípravka") bookings from the
[Hala Polárka reservation calendar](https://rezervace.halapolarka.cz/?p=LP) and checks them against the expected schedule.
It shows a warning for a booking at an unexpected time and for an expected booking that is missing.
A second page (`zapasy.html`) lists the upcoming matches of HC Frýdek-Místek from
[hokej.hcf-m.cz](https://hokej.hcf-m.cz/zapasy.asp?sezona=2027).
The page text is in Czech; the code is in English.

## How it works

`generate.py` downloads the calendar, picks the bookings named "Přípravka", "1+2" or "1+2+3", compares them with the
expected times and writes `site/index.html` and `site/calendar.ics`. It also reads the club's matches table (which is in
windows-1250) and writes `site/zapasy.html`; if that site is down, the matches page shows a notice and the bookings are still updated. A GitHub Actions workflow
(`.github/workflows/pages.yml`) runs it every 15 minutes and publishes `site/` with GitHub Pages.
If the calendar cannot be fetched or its format changes, the run fails and the last good page stays online.

## Run it locally

```bash
python3 test_generate.py                   # tests, no network needed
python3 generate.py                        # writes site/
python3 -m http.server -d site             # preview at http://localhost:8000
```

Python 3.9+ with the standard library only. The expected times are in `EXPECTED` in `generate.py`.

## Notes

- The club logo (`logo.png`, `apple-touch-icon.png`) belongs to HC Frýdek-Místek. It is only a decoration of the page
  and is not covered by any license of this repository.
- The booking data comes from the Hala Polárka reservation system and the matches from the club website.
- The season in the matches URL is chosen by month (a new season from July, `matches_url` in `generate.py`).
