from setup.session_setup import session
from datetime import datetime as dt
from datetime import timezone as tz


ESPN_SCOREBOARD_URL = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard'

# ESPN/Akamai often reject requests that look like a generic scraper.
ESPN_HEADERS = {
    'User-Agent': 'rpi-led-sports-scoreboard/nfl (https://github.com/gidger/rpi-led-sports-scoreboard)',
    'Accept': 'application/json',
    'Referer': 'https://www.espn.com/nfl/scoreboard'
}

# Regular season and postseason only. ESPN season.type: 1=preseason, 2=regular, 3=postseason.
INCLUDED_SEASON_TYPES = {2, 3}


def get_games(date):
    """ Loads NFL game data for the provided date from the ESPN scoreboard API.

    Args:
        date (date): Date that game data should be pulled for.

    Returns:
        list: List of dicts of game data.
    """

    scoreboard_json = _fetch_scoreboard(params={'dates': date.strftime('%Y%m%d')})
    return parse_games(scoreboard_json)


def get_week_games():
    """ Loads NFL game data for the current ESPN week (Thu-Mon slate).

    Returns:
        list: List of dicts of game data.
    """

    return parse_games(_fetch_scoreboard())


def get_next_game(team):
    """ Loads next game details for the supplied NFL team.
    If the team is currently playing, will return details of the current game.

    Args:
        team (str): Team abbreviation to pull next game details for (ESPN style, e.g. 'KC', 'GB', 'WSH').

    Returns:
        dict: Dict of next game details, or None if no upcoming game is found.
    """

    team = team.upper()
    cur_datetime = dt.today().astimezone()
    cur_date = cur_datetime.date()

    current_scoreboard = _fetch_scoreboard()
    week = current_scoreboard.get('week', {}).get('number', 1)
    season = current_scoreboard.get('season', {})
    season_type = season.get('type', 2)
    season_year = season.get('year', cur_date.year)

    for week_offset in range(0, 8):
        if week_offset == 0:
            scoreboard_json = current_scoreboard
        else:
            scoreboard_json = _fetch_scoreboard(params={
                'week': week + week_offset,
                'seasontype': season_type,
                'dates': str(season_year)
            })

        for game in parse_games(scoreboard_json):
            if team not in (game['home_abrv'], game['away_abrv']):
                continue

            # Skip games that have already finished.
            if game['status_code'] == 3 or game['is_postponed']:
                continue

            return {
                'home_or_away': 'home' if game['home_abrv'] == team else 'away',
                'opponent_abrv': game['away_abrv'] if game['home_abrv'] == team else game['home_abrv'],
                'start_datetime_utc': game['start_datetime_utc'],
                'start_datetime_local': game['start_datetime_local'],
                'is_today': True if game['start_datetime_local'].date() == cur_date or game['start_datetime_local'] < cur_datetime else False,
                'has_started': game['has_started']
            }

    return None


def parse_games(scoreboard_json):
    """ Converts an ESPN scoreboard JSON payload into the game dicts used by game scenes.

    Args:
        scoreboard_json (dict): Parsed JSON from the ESPN NFL scoreboard endpoint.

    Returns:
        list: List of dicts of game data.
    """

    games = []

    for event in scoreboard_json.get('events', []):
        season_type = event.get('season', {}).get('type')
        if season_type not in INCLUDED_SEASON_TYPES:
            continue

        competition = event['competitions'][0]
        home = _competitor(competition, 'home')
        away = _competitor(competition, 'away')
        if not home or not away:
            continue

        status = competition.get('status') or event.get('status') or {}
        status_type = status.get('type', {})
        status_name = status_type.get('name', '')
        status_state = status_type.get('state', '')
        status_code = _status_code(status_state, status_name)
        is_postponed = status_name in ('STATUS_POSTPONED', 'STATUS_CANCELED', 'STATUS_CANCELLED')
        is_halftime = status_name == 'STATUS_HALFTIME' or 'Halftime' in (status_type.get('shortDetail') or '')

        start_datetime_utc = dt.strptime(event['date'], '%Y-%m-%dT%H:%MZ').replace(tzinfo=tz.utc)
        period_num = status.get('period') or 0
        situation = competition.get('situation') or {}

        games.append({
            'game_id': event['id'],
            'home_abrv': home['team']['abbreviation'],
            'away_abrv': away['team']['abbreviation'],
            'home_score': _score(home.get('score')),
            'away_score': _score(away.get('score')),
            'start_datetime_utc': start_datetime_utc,
            'start_datetime_local': start_datetime_utc.astimezone(tz=None),
            'status': status_type.get('description') or status_name,
            'status_code': status_code,  # 1=Scheduled, 2=In Progress, 3=Final.
            'has_started': status_code >= 2 and not is_postponed,
            'period_num': period_num,
            'period_type': 'OT' if period_num > 4 else 'Std',
            'period_time_remaining': _format_clock(status.get('displayClock')),
            'is_halftime': is_halftime,
            'is_postponed': is_postponed,
            'start_time_tbd': not competition.get('timeValid', True),
            # Stored for a later down-and-distance view; unused in V1 display.
            'down': situation.get('down'),
            'distance': situation.get('distance'),
            'home_team_scored': False,
            'away_team_scored': False,
            'scoring_team': None
        })

    games = sorted(games, key=lambda x: x['game_id'])
    return games


def _fetch_scoreboard(params=None):
    """ Fetches ESPN NFL scoreboard JSON.

    Args:
        params (dict, optional): Query string parameters.

    Returns:
        dict: Scoreboard JSON.
    """

    response = session.get(url=ESPN_SCOREBOARD_URL, headers=ESPN_HEADERS, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def _competitor(competition, home_or_away):
    """ Finds the home or away competitor dict in an ESPN competition.

    Args:
        competition (dict): ESPN competition object.
        home_or_away (str): 'home' or 'away'.

    Returns:
        dict: Competitor dict, or None if missing.
    """

    for competitor in competition.get('competitors', []):
        if competitor.get('homeAway') == home_or_away:
            return competitor
    return None


def _status_code(status_state, status_name):
    """ Maps ESPN status to the 1/2/3 codes used by basketball game scenes.

    Args:
        status_state (str): ESPN status.type.state (pre/in/post).
        status_name (str): ESPN status.type.name.

    Returns:
        int: 1=Scheduled, 2=In Progress, 3=Final.
    """

    if status_name in ('STATUS_POSTPONED', 'STATUS_CANCELED', 'STATUS_CANCELLED'):
        return 3
    if status_state == 'pre':
        return 1
    if status_state == 'in':
        return 2
    return 3


def _score(value):
    """ Converts an ESPN score value to an int.

    Args:
        value: Score as returned by ESPN (str, int, or None).

    Returns:
        int: Score, defaulting to 0 when missing.
    """

    if value in (None, ''):
        return 0
    return int(value)


def _format_clock(display_clock):
    """ Pads ESPN displayClock values to MM:SS so existing time drawing code works.

    Args:
        display_clock (str): Clock string from ESPN, e.g. '8:42' or '15:00'.

    Returns:
        str: Zero-padded MM:SS clock, or None if missing.
    """

    if not display_clock or ':' not in display_clock:
        return None

    minutes, seconds = display_clock.split(':', 1)
    try:
        return f'{int(minutes):02d}:{seconds.zfill(2)}'
    except ValueError:
        return None
