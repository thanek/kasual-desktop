"""Every wait in the harness, in seconds — the knobs a slower machine turns.

Generous by design: a scenario that fails because Steam was still updating shaders
teaches nothing, and these runs are watched by a human anyway.
"""

HOME_VIEW       = 20.0    # KD's device scan finding the pad, then the Home view
WINDOW_SOURCE   = 5.0     # the compositor accepting the hook and sending the first stack
TILE_FOCUS      = 3.0     # one pad press moving the focus
APP_START       = 30.0    # a bundled app coming up, and its own test API answering
STEAM_UI        = 120.0   # Steam starting up, up to its Big Picture page
STEAM_INTRO     = 8.0     # Big Picture's intro animation, which swallows a press
STEAM_PAGE      = 20.0    # a page of Steam's UI animating in, and settling its focus
LAUNCHER        = 180.0   # Steam starting up, then the splash / launcher
GAME_LAUNCH     = 90.0    # a warm Steam turning a launch into the game's first window; none by now means the request was dropped
GAME_FULLSCREEN = 300.0   # shader compilation lives here
GAME_EXIT       = 60.0    # a game shutting its engine down after KD asked its window to close
CEDE            = 15.0    # KD getting off the screen
HOME_MENU       = 10.0    # the Home hold opening the menu over the game
STILL_ON_SCREEN = 4.0     # the game watched for leaving the screen under the menu
EXIT            = 30.0    # a process, or KD, going away on the way out
