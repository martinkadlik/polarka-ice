#!/usr/bin/env python3
"""Downloads the NHL team logos (a light and a dark SVG per team) into logos/nhl/.
Run it again when a team is added or moved, or when a logo changes (delete the old file first)."""
import json, os, re, sys
from generate import fetch

STANDINGS_URL = "https://api-web.nhle.com/v1/standings/now"
LOGO_URL = "https://assets.nhle.com/logos/nhl/svg/{}_{}.svg"
# the files are served from our own origin, so anything but a plain image (scripts, handlers, external references) is refused
UNSAFE = re.compile(r'<script|<foreignObject|\son\w+\s*=|href\s*=\s*["\']?https?:', re.I)

def main():
    teams = sorted(t["teamAbbrev"]["default"] for t in json.loads(fetch(STANDINGS_URL, "utf-8"))["standings"])
    os.makedirs("logos/nhl", exist_ok=True)
    downloaded = 0
    for abbr in teams:
        for variant in ("light", "dark"):
            path = f"logos/nhl/{abbr}_{variant}.svg"
            if os.path.exists(path):
                continue
            svg = fetch(LOGO_URL.format(abbr, variant), "utf-8")
            if not svg.lstrip().startswith("<svg") or UNSAFE.search(svg):
                sys.exit(f"{abbr}_{variant}: not a plain SVG image, not saved")
            open(path, "w", encoding="utf-8").write(svg)
            downloaded += 1
    print(f"{len(teams)} teams, {downloaded} files downloaded")

if __name__ == "__main__":
    main()
