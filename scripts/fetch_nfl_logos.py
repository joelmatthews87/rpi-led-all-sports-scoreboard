#!/usr/bin/env python3
"""One-time download of NFL team and league logos into the gidger assets folders.

Downloads ESPN's 500x500 transparent PNGs (the same source ChuckBuilds/LEDMatrix
caches at runtime) and writes them as TEAM.png files under assets/images/NFL/.
Re-run this script if a team rebrands or a logo looks wrong on the matrix.
"""

from pathlib import Path

import requests
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
TEAMS_DIR = REPO_ROOT / 'assets' / 'images' / 'NFL' / 'teams'
LEAGUE_DIR = REPO_ROOT / 'assets' / 'images' / 'NFL' / 'league'

# ESPN abbreviations used by the NFL scoreboard API and as logo filenames.
NFL_TEAM_ABBREVIATIONS = [
    'ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE',
    'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC',
    'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG',
    'NYJ', 'PHI', 'PIT', 'SEA', 'SF', 'TB', 'TEN', 'WSH',
]

TEAM_LOGO_URL = 'https://a.espncdn.com/i/teamlogos/nfl/500/{abbr}.png'
LEAGUE_LOGO_URL = 'https://a.espncdn.com/i/teamlogos/leagues/500/nfl.png'

HEADERS = {
    'User-Agent': 'rpi-led-sports-scoreboard/nfl (https://github.com/gidger/rpi-led-sports-scoreboard)',
    'Referer': 'https://www.espn.com/nfl/scoreboard'
}


def download_png(url, dest_path):
    """Download an image, verify it, and save as a PNG.

    Args:
        url (str): Image URL.
        dest_path (Path): Destination file path.
    """

    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(response.content)

    image = Image.open(dest_path)
    image.load()
    if image.mode != 'RGBA':
        image = image.convert('RGBA')

    # Keep assets small and consistent. ESPN usually serves 500x500; a few teams
    # (currently NYJ) return a much larger scoreboard sheet at the same URL.
    max_size = (500, 500)
    if image.width > max_size[0] or image.height > max_size[1]:
        image.thumbnail(max_size, Image.Resampling.LANCZOS)

    image = prepare_logo_for_matrix(image)
    image.save(dest_path)

    print(f'Saved {dest_path.relative_to(REPO_ROOT)} ({image.size[0]}x{image.size[1]} {image.mode})')


def prepare_logo_for_matrix(image):
    """Premultiply alpha onto black so gidger's RGB crop/paste does not show white fringes.

    Args:
        image (Image): Source logo.

    Returns:
        Image: RGBA logo safe to display on a black LED matrix.
    """

    image = image.convert('RGBA')
    prepared = []
    for red, green, blue, alpha in image.getdata():
        if alpha == 0:
            prepared.append((0, 0, 0, 0))
        else:
            prepared.append((
                int(round(red * alpha / 255)),
                int(round(green * alpha / 255)),
                int(round(blue * alpha / 255)),
                alpha
            ))
    image.putdata(prepared)
    return image


def main():
    TEAMS_DIR.mkdir(parents=True, exist_ok=True)
    LEAGUE_DIR.mkdir(parents=True, exist_ok=True)

    download_png(LEAGUE_LOGO_URL, LEAGUE_DIR / 'NFL.png')

    failures = []
    for abbr in NFL_TEAM_ABBREVIATIONS:
        url = TEAM_LOGO_URL.format(abbr=abbr.lower())
        dest = TEAMS_DIR / f'{abbr}.png'
        try:
            download_png(url, dest)
        except Exception as error:
            failures.append((abbr, error))
            print(f'Failed {abbr}: {error}')

    if failures:
        raise SystemExit(f'Finished with {len(failures)} failure(s).')

    print(f'Downloaded {len(NFL_TEAM_ABBREVIATIONS)} team logos and the NFL league logo.')


if __name__ == '__main__':
    main()
