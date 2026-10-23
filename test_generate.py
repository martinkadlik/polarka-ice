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
print("OK")
