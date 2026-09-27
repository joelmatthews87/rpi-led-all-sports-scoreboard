from .games_scene import GamesScene
from setup.matrix_setup import matrix
import data.mlb_data
from utils import data_utils, date_utils

from datetime import datetime as dt
from time import sleep


class MLBGamesScene(GamesScene):
    """ Game scene for the MLB. Contains functionality to pull data from MLB API, parse, and build+display specific images based on the result.
    This class extends the general Scene and GameScene classes. An object of this class type is created when the scoreboard is started.
    """

    def __init__(self):
        """ Defines the league as MLB. Used to identify the correct files when adding logos to images.
        First runs init from the generic GameScene class.
        """
        
        super().__init__()
        self.LEAGUE = 'MLB'


    def display_scene(self):
        """ Displays the scene on the matrix.
        Includes logic on which image to build, when to display, etc.
        """

        # Refresh config and load to settings key.
        self.settings = data_utils.read_yaml('config.yaml')['scene_settings'][self.LEAGUE.lower()]['games']
        self.alt_logos = data_utils.read_yaml('config.yaml')['alt_logos'][self.LEAGUE.lower()] if data_utils.read_yaml('config.yaml')['alt_logos'][self.LEAGUE.lower()] else {} # Note the teams with an alternative logo per config.yaml.

        # Determine which days should be displayed. Will generate a list with one or two elements. Two means rollover time and yesterdays games should be displayed.
        dates_to_display = date_utils.determine_dates_to_display_games(self.settings['rollover']['rollover_start_time_local'], self.settings['rollover']['rollover_end_time_local'])
        display_yesterday = True if len(dates_to_display) == 2 else False # Will have to display yesterdays games if dates_to_display has 2 elements.

        # If in rollover time, and the data for previous day hasn't been saved / is from a different date than needed, then pull it.
        # This will ensure we don't need to pull the previous day data (that doesn't change) every loop.
        if display_yesterday:
            if (hasattr(self, 'data_previous_day') and self.data_previous_day['saved_date'] != dates_to_display[0]) or not hasattr(self, 'data_previous_day'):
                self.data_previous_day = {
                    'saved_date': dates_to_display[0], # Note the previous date.
                    'games': data.mlb_data.get_games(dates_to_display[0]) # Get data for previous date.
                }
        
        # Get current day game data. Save this for future reference.
        self.data = {
            'games_previous_pull': self.data['games'] if hasattr(self, 'data') else None, # If this is the first time this is run, we'd expect self.data to not exist.
            'games': data.mlb_data.get_games(dates_to_display[-1]), # Get data for current day. Current day will always be the last element of dates_to_display.
        }

        # If there are games to display from yesterday (and setting is enabled), build and display splash image (if enabled), then images for those games.
        if display_yesterday and self.settings['rollover']['show_completed_games_until_rollover_end_time']:
            if self.settings['splash']['display_splash']:
                self.display_splash_image(len(self.data_previous_day['games']), date=dates_to_display[0])
            self.display_game_images(self.data_previous_day['games'], date=dates_to_display[0])

        # For the current day's games, note if any runs were scored since the last data pull.
        if self.data['games_previous_pull']: # Only applicable if there's a previous copy to compare to.
            for game in self.data['games']:
                if game['status'] not in ['Preview']: # Not applicable if the game hasn't started yet.
                    # Match games between data pulls.
                    matched_game = next(filter(lambda x: x['game_id'] == game['game_id'], self.data['games_previous_pull']))

                    if matched_game['status'] not in ['Preview']: # Not applicable if the game hasn't started yet in the previous pull.
                        # Determine if either team scored and set keys accordingly.
                        game['away_team_scored'] = True if game['away_score'] > matched_game['away_score'] else False
                        game['home_team_scored'] = True if game['home_score'] > matched_game['home_score'] else False
                        
                        if game['away_team_scored'] and game['home_team_scored']:
                            game['scoring_team'] = 'both'
                        elif game['away_team_scored']:
                            game['scoring_team'] = 'away'
                        elif game['home_team_scored']:
                            game['scoring_team'] = 'home'
                    
        # Display splash (if enabled) for current day.
        if self.settings['splash']['display_splash']:
            self.display_splash_image(len(self.data['games']), date=dates_to_display[-1])
        
        # Display game image(s) for current day.
        self.display_game_images(self.data['games'], date=dates_to_display[-1])


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
                # If the game has yet to begin, build the game not started image (or TBD image if the start time is to be determined).
                if game['status'] in ['Preview']:
                    if game['start_time_tbd'] or 'Delayed' in game['detailed_status']:
                        self.build_game_tbd_image(game)
                    else:
                        self.build_game_not_started_image(game)

                # If the game is postponed or cancelled, build the postponed image. Need to check for these first as the API also says these games are 'Final', and a cancelled game has no inning.
                elif game['detailed_status'] in ['Postponed', 'Cancelled', 'Canceled']:
                    self.build_game_postponed_image(game)

                # If the game is over, build the final score image.
                elif game['status'] in ['Final']:
                    self.build_game_complete_image(game)

                # Otherwise, the game is in progress. Build the game in progress screen.
                elif game['status'] in ['Live', 'Delayed']: # TODO: Confirm that a game is delayed once it's started due to weather or other factors. Adjust logic as needed if there are any differences in the API results for a delayed game vs a live game.
                    self.build_game_in_progress_image(game)
                else:
                    print(f"Unexpected game status encountered from API: {game['status']}.")

                # Transition the image in on the matrix.
                self.transition_image(direction='in')

                # If a run was scored, do score fade animation (if enabled).
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


    def build_game_in_progress_image(self, game):
        """ Builds image for when the game is in progress.
        Includes team logos, score, period, and time remaining.

        Args:
            game (dict): Dictionary with all details of a specific game.
        """

        # First, add the team logos to the left and right images.
        self.add_team_logos_to_image(game)

        # Add the inning to the centre image.
        self.add_playing_period_to_image(game) # This exists in parent class, but is overridden here due to baseball using innings.

        # Add the current score to the centre image, noting if either team scored since previous data pull.
        self.add_score_to_image(game, overriding_team=game['scoring_team'], colour_override=self.COLOURS['red'])

        if self.settings['display_outs_and_bases']:
            # Add outs identifier to the centre image.
            self.add_outs_to_image(game)

            # Add runners on base identifier to the centre image.
            self.add_runners_on_base_to_image(game)


    def add_playing_period_to_image(self, game):
        """ Adds current inning to the centre image.
        This exists within the specific league class due to huge differences in playing periods between sports (periods, quarters, innings, etc.).

        Args:
            game (dict): Dictionary with all details of a specific game.
        """

        # A game can be live in name only, with no inning yet. Nothing sensible to draw.
        if not game['inning_num']:
            return

        # Determine the offset for the inning details based on the inning number. If extra innings, will need to adjust to fit the extra digit.
        col_offset = 6 if game['inning_num'] <= 9 else 3

        # If in the top or start of inning, up arrow.
        if game['inning_state'] in ['Top', 'Start']:
            self.draw['centre'].line(((col_offset, 1), (col_offset, 6)), fill=self.COLOURS['white'])
            self.draw['centre'].line(((col_offset, 1), (col_offset-2, 3)), fill=self.COLOURS['white'])
            self.draw['centre'].line(((col_offset, 1), (col_offset+2, 3)), fill=self.COLOURS['white'])

        # If in bottom, down arrow.
        elif game['inning_state'] == 'Bottom':
            self.draw['centre'].line(((col_offset, 7), (col_offset, 2)), fill=self.COLOURS['white'])
            self.draw['centre'].line(((col_offset, 7), (col_offset-2, 5)), fill=self.COLOURS['white'])
            self.draw['centre'].line(((col_offset, 7), (col_offset+2, 5)), fill=self.COLOURS['white'])

        # If at the end of the inning, add an 'E'.
        elif game['inning_state'] == 'End':
            self.draw['centre'].text((col_offset-1, -1), 'E', font=self.FONTS['med'], fill=self.COLOURS['white'])

        # Middle of inning, horizontal line.
        elif game['inning_state'] == 'Middle':
            self.draw['centre'].line(((col_offset-2, 4), (col_offset+2, 4)), fill=self.COLOURS['white'])
        
        # Add inning number.
        self.draw['centre'].text((col_offset+5, -1), str(game['inning_num']), font=self.FONTS['med'], fill=self.COLOURS['white'])


    def add_final_playing_period_to_image(self, game):
        """ Adds final inning to the centre image if game ended in extra innings.

        Args:
            game (dict): Dictionary with all details of a specific game.
        """

        # If the game ended in extra innings, add the final inning number to the image.
        # A cancelled game can be marked Final with no inning at all.
        if game['inning_num'] and game['inning_num'] > 9:
            # We'll assume no games go longer than 99 innings... so only one layout needed.
            self.draw['centre'].text((4, 8), str(game['inning_num']), font=self.FONTS['med'], fill=self.COLOURS['white'])


    def add_outs_to_image(self, game):
        """ Adds number of outs to the image for in progress games.

        Args:
            game (dict): Dictionary with all details of a specific game.
        """

        # Draw grey boxes representing potential outs.
        self.draw['centre'].rectangle(((2, 10), (4, 11)), fill=self.COLOURS['grey_light'])
        self.draw['centre'].rectangle(((2, 13), (4, 14)), fill=self.COLOURS['grey_light'])
        self.draw['centre'].rectangle(((2, 16), (4, 17)), fill=self.COLOURS['grey_light'])

        # Colour in boxes based on number of outs.
        if game['outs'] >= 1:
            self.draw['centre'].rectangle(((2, 10), (4, 11)), fill=self.COLOURS['yellow'])
        if game['outs'] >= 2:
            self.draw['centre'].rectangle(((2, 13), (4, 14)), fill=self.COLOURS['yellow'])
        if game['outs'] == 3:
            self.draw['centre'].rectangle(((2, 16), (4, 17)), fill=self.COLOURS['yellow'])


    def add_runners_on_base_to_image(self, game):
        """ Adds runners on base to the image for in progress games.

        Args:
            game (dict): Dictionary with all details of a specific game.
        """
        
        # Draw a square rotated 45 degrees to represent each base. Each made up of four lines.
        # 1st base.
        self.draw['centre'].line(((15, 13), (17, 15)), fill=self.COLOURS['grey_light'])
        self.draw['centre'].line(((17, 15), (15, 17)), fill=self.COLOURS['grey_light'])
        self.draw['centre'].line(((15, 17), (13, 15)), fill=self.COLOURS['grey_light'])
        self.draw['centre'].line(((13, 15), (15, 13)), fill=self.COLOURS['grey_light'])
        # 2nd base.
        self.draw['centre'].line(((12, 10), (14, 12)), fill=self.COLOURS['grey_light'])
        self.draw['centre'].line(((14, 12), (12, 14)), fill=self.COLOURS['grey_light'])
        self.draw['centre'].line(((12, 14), (10, 12)), fill=self.COLOURS['grey_light'])
        self.draw['centre'].line(((10, 12), (12, 10)), fill=self.COLOURS['grey_light'])
        # 3rd base.
        self.draw['centre'].line(((9, 13), (11, 15)), fill=self.COLOURS['grey_light'])
        self.draw['centre'].line(((11, 15), (9, 17)), fill=self.COLOURS['grey_light'])
        self.draw['centre'].line(((9, 17), (7, 15)), fill=self.COLOURS['grey_light'])
        self.draw['centre'].line(((7, 15), (9, 13)), fill=self.COLOURS['grey_light'])

        # Colour in based on if there's a runner on the base.
        if game['runner_on_first']:
            self.draw['centre'].line(((15, 14), (15, 16)), fill=self.COLOURS['yellow'])
            self.draw['centre'].line(((14, 15), (16, 15)), fill=self.COLOURS['yellow'])
        if game['runner_on_second']:
            self.draw['centre'].line(((12, 11), (12, 13)), fill=self.COLOURS['yellow'])
            self.draw['centre'].line(((11, 12), (13, 12)), fill=self.COLOURS['yellow'])
        if game['runner_on_third']:
            self.draw['centre'].line(((9, 14), (9, 16)), fill=self.COLOURS['yellow'])
            self.draw['centre'].line(((8, 15), (10, 15)), fill=self.COLOURS['yellow'])
