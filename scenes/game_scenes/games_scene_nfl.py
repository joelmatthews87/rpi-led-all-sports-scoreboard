from .games_scene import GamesScene
import data.nfl_data
from utils import data_utils, date_utils

from datetime import datetime as dt
from time import sleep


class NFLGamesScene(GamesScene):
    """ Game scene for the NFL. Contains functionality to pull data from ESPN, parse, and build+display specific images based on the result.
    This class extends the general Scene and GameScene classes. An object of this class type is created when the scoreboard is started.
    """

    def __init__(self):
        """ Defines the league as NFL. Used to identify the correct files when adding logos to images.
        First runs init from the generic GameScene class.
        """

        super().__init__()
        self.LEAGUE = 'NFL'


    def display_scene(self):
        """ Displays the scene on the matrix.
        Includes logic on which image to build, when to display, etc.
        """

        # Refresh config and load to settings key.
        self.settings = data_utils.read_yaml('config.yaml')['scene_settings'][self.LEAGUE.lower()]['games']
        self.alt_logos = data_utils.read_yaml('config.yaml')['alt_logos'][self.LEAGUE.lower()] if data_utils.read_yaml('config.yaml')['alt_logos'][self.LEAGUE.lower()] else {} # Note the teams with an alternative logo per config.yaml.

        # NFL slates run Thursday through Monday. Optionally show the current ESPN week
        # instead of only the local calendar day's games (which is empty most weekdays).
        if self.settings.get('show_full_week', True):
            self.data = {
                'games_previous_pull': self.data['games'] if hasattr(self, 'data') else None,
                'games': data.nfl_data.get_week_games(),
            }
            week_date = dt.today().astimezone().date()
            self._mark_score_changes()
            if self.settings['splash']['display_splash']:
                self.display_splash_image(len(self.data['games']), date=week_date)
            self.display_game_images(self.data['games'], date=week_date)
            return

        # Determine which days should be displayed. Will generate a list with one or two elements. Two means rollover time and yesterdays games should be displayed.
        dates_to_display = date_utils.determine_dates_to_display_games(self.settings['rollover']['rollover_start_time_local'], self.settings['rollover']['rollover_end_time_local'])
        display_yesterday = True if len(dates_to_display) == 2 else False # Will have to display yesterdays games if dates_to_display has 2 elements.

        # If in rollover time, and the data for previous day hasn't been saved / is from a different date than needed, then pull it.
        # This will ensure we don't need to pull the previous day data (that doesn't change) every loop.
        if display_yesterday:
            if (hasattr(self, 'data_previous_day') and self.data_previous_day['saved_date'] != dates_to_display[0]) or not hasattr(self, 'data_previous_day'):
                self.data_previous_day = {
                    'saved_date': dates_to_display[0], # Note the previous date.
                    'games': data.nfl_data.get_games(dates_to_display[0]) # Get data for previous date.
                }

        # Get current day game data. Save this for future reference.
        self.data = {
            'games_previous_pull': self.data['games'] if hasattr(self, 'data') else None, # If this is the first time this is run, we'd expect self.data to not exist.
            'games': data.nfl_data.get_games(dates_to_display[-1]), # Get data for current day. Current day will always be the last element of dates_to_display.
        }

        # If there are games to display from yesterday (and setting is enabled), build and display splash image (if enabled), then images for those games.
        if display_yesterday and self.settings['rollover']['show_completed_games_until_rollover_end_time']:
            if self.settings['splash']['display_splash']:
                self.display_splash_image(len(self.data_previous_day['games']), date=dates_to_display[0])
            self.display_game_images(self.data_previous_day['games'], date=dates_to_display[0])

        self._mark_score_changes()

        # Display splash (if enabled) for current day.
        if self.settings['splash']['display_splash']:
            self.display_splash_image(len(self.data['games']), date=dates_to_display[-1])

        # Display game image(s) for current day.
        self.display_game_images(self.data['games'], date=dates_to_display[-1])


    def _mark_score_changes(self):
        """ Flags teams that increased their score since the previous data pull. """

        if self.data['games_previous_pull']: # Only applicable if there's a previous copy to compare to.
            for game in self.data['games']:
                if game['status_code'] != 1: # Not applicable if the game hasn't started yet.
                    # Match games between data pulls.
                    matched_game = next(filter(lambda x: x['game_id'] == game['game_id'], self.data['games_previous_pull']), None)

                    if matched_game and matched_game['status_code'] != 1: # Not applicable if the game hasn't started yet in the previous pull.
                        # Determine if either team scored and set keys accordingly.
                        game['away_team_scored'] = True if game['away_score'] > matched_game['away_score'] else False
                        game['home_team_scored'] = True if game['home_score'] > matched_game['home_score'] else False

                        if game['away_team_scored'] and game['home_team_scored']:
                            game['scoring_team'] = 'both'
                        elif game['away_team_scored']:
                            game['scoring_team'] = 'away'
                        elif game['home_team_scored']:
                            game['scoring_team'] = 'home'


    def display_splash_image(self, num_games, date):
        """ Builds and displays splash screen for games on date.

        Args:
            num_games (int): Num of games happening on date.
            date (date): Date of games.
        """

        # Build splash image, transition in, pause, transition out.
        self.build_splash_image(num_games, date)
        self.transition_image(direction='in', image_already_combined=True)
        sleep(self.settings['splash']['splash_display_duration'])
        self.transition_image(direction='out', image_already_combined=True)


    def display_game_images(self, games, date=None):
        """ Builds and displays images on the matrix for each game in games.

        Args:
            games (list): List of game dicts. Each element has all details for a single game.
            date (date, optional): Date of games. Only used to build 'no games' image when there's... well, no games on that data. Defaults to None.
        """

        # If there's any games to display, loop through them and build the appropriate images.
        if games:
            for game in games:
                # If the game has been postponed or canceled, build the postponed image.
                if game['is_postponed']:
                    self.build_game_postponed_image(game)

                # If the game has yet to begin, build the game not started image (or TBD image if the start time is to be determined).
                elif game['status_code'] == 1:
                    if game['start_time_tbd']:
                        self.build_game_tbd_image(game)
                    else:
                        self.build_game_not_started_image(game)

                # If the game is over, build the final score image.
                elif game['status_code'] == 3:
                    self.build_game_complete_image(game)

                # Otherwise, the game is in progress. Build the game in progress screen.
                elif game['status_code'] == 2:
                    self.build_game_in_progress_image(game)
                else:
                    print(f"Unexpected gameState encountered from API: {game['status']}.")

                # Transition the image in on the matrix.
                self.transition_image(direction='in')

                # If a score changed, do score fade animation (if enabled).
                if self.settings['score_alerting']['score_coloured'] and self.settings['score_alerting']['score_fade_animation']:
                    if game['scoring_team']:
                        self.fade_score_change(game)

                # Hold image for calculated duration and transition out.
                sleep(self.settings['game_display_duration'])
                self.transition_image(direction='out')

        # If there's no games to display, and splash is disabled, build and display the no games image.
        elif not self.settings['splash']['display_splash']:
            self.build_no_games_image(date)
            self.transition_image(direction='in', image_already_combined=True)
            sleep(self.settings['game_display_duration'])
            self.transition_image(direction='out', image_already_combined=True)


    def build_game_not_started_image(self, game):
        """ Builds image for when the game has yet to start.

        Overrides the generic version, which always labels an upcoming game 'Today'. With
        show_full_week enabled the scene displays the whole Thu-Mon slate, so a game later in
        the week gets its weekday (e.g. 'Sun') instead.

        Args:
            game (dict): Dictionary with all details of a specific game.
        """

        # Games actually happening today keep the standard 'Today' treatment.
        if game['start_datetime_local'].date() == dt.today().astimezone().date():
            super().build_game_not_started_image(game)
            return

        # First, add the team logos to the left and right images.
        self.add_team_logos_to_image(game)

        # Add the three letter weekday, centred, in place of 'Today'.
        weekday = game['start_datetime_local'].strftime('%a')
        self.draw['centre'].text((1, -1), weekday, font=self.FONTS['med'], fill=self.COLOURS['white'])

        # Add '@' to the centre image.
        self.draw['centre'].text((5, 7), '@', font=self.FONTS['lrg'], fill=self.COLOURS['white'])

        # Add the start time to the centre image.
        self.add_time_to_image(game)


    def add_playing_period_to_image(self, game):
        """ Adds current playing period to the centre image.
        This exists within the specific league class due to huge differences in playing periods between sports (periods, quarters, innings, etc.).

        Args:
            game (dict): Dictionary with all details of a specific game.
        """

        # If halftime, add "Half" to the image.
        if game['is_halftime']:
            self.draw['centre'].text((0, -1), 'H', font=self.FONTS['med'], fill=self.COLOURS['white'])
            self.draw['centre'].text((6, -1), 'a', font=self.FONTS['med'], fill=self.COLOURS['white'])
            self.draw['centre'].text((11, -1), 'l', font=self.FONTS['med'], fill=self.COLOURS['white'])
            self.draw['centre'].text((15, -1), 'f', font=self.FONTS['med'], fill=self.COLOURS['white'])

        # If the first qtr, add "1st" to the image.
        elif game['period_num'] == 1:
            self.draw['centre'].text((4, -1), '1', font=self.FONTS['med'], fill=self.COLOURS['white'])
            self.draw['centre'].text((8, -1), 's', font=self.FONTS['sm'], fill=self.COLOURS['white'])
            self.draw['centre'].text((12, -1), 't', font=self.FONTS['sm'], fill=self.COLOURS['white'])

        # If the second qtr, add "2nd" to the image.
        elif game['period_num'] == 2:
            self.draw['centre'].text((3, -1), '2', font=self.FONTS['med'], fill=self.COLOURS['white'])
            self.draw['centre'].text((9, -1), 'n', font=self.FONTS['sm'], fill=self.COLOURS['white'])
            self.draw['centre'].text((13, -1), 'd', font=self.FONTS['sm'], fill=self.COLOURS['white'])

        # If the third qtr, add "3rd" to the image.
        elif game['period_num'] == 3:
            self.draw['centre'].text((3, -1), '3', font=self.FONTS['med'], fill=self.COLOURS['white'])
            self.draw['centre'].text((9, -1), 'r', font=self.FONTS['sm'], fill=self.COLOURS['white'])
            self.draw['centre'].text((13, -1), 'd', font=self.FONTS['sm'], fill=self.COLOURS['white'])

        # If the fourth qtr, add "4th" to the image.
        elif game['period_num'] == 4:
            self.draw['centre'].text((3, -1), '4', font=self.FONTS['med'], fill=self.COLOURS['white'])
            self.draw['centre'].text((8, -1), 't', font=self.FONTS['sm'], fill=self.COLOURS['white'])
            self.draw['centre'].text((13, -1), 'h', font=self.FONTS['sm'], fill=self.COLOURS['white'])

        # If in single OT, add that to the image.
        elif game['period_num'] == 5:
            self.draw['centre'].text((4, -1), game['period_type'], font=self.FONTS['med'], fill=self.COLOURS['white'])

        # Otherwise, we're in 2OT, or later. Calculate the number of OT periods and add that to the image.
        elif game['period_num'] > 5:
            per = f'{game["period_num"] - 4}{game["period_type"]}'
            self.draw['centre'].text((1, -1), per, font=self.FONTS['med'], fill=self.COLOURS['white'])


    def add_final_playing_period_to_image(self, game):
        """ Adds final playing period to the centre image if game ended in OT or xOT.

        Args:
            game (dict): Dictionary with all details of a specific game.
        """

        # If game ended in the first OT, add that to the centre image.
        if game['period_num'] == 5:
            self.draw['centre'].text((4, 8), game['period_type'], font=self.FONTS['med'], fill=self.COLOURS['white'])

        # Or if in 2OT or later. Calculate the number of OT periods and add that to the centre image.
        elif game['period_num'] > 5:
            per = f'{game["period_num"] - 4}{game["period_type"]}'
            self.draw['centre'].text((1, 8), per, font=self.FONTS['med'], fill=self.COLOURS['white'])


    def should_display_time_remaining_in_playing_period(self, game):
        """ Determines if the time remaining in the playing period should be added to the centre image.

        Args:
            game (dict): Dictionary with all details of a specific game.

        Returns:
            Bool: if the time remaining in the playing period should be added to the centre image (True) or not (False).
        """

        if game['is_halftime'] or not game['period_time_remaining']:
            return False
        else:
            return True
