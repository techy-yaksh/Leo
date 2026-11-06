"""
Backward-compatibility adapter for core.system_tools.
Redirects calls to the modularized services.system_service module.
"""

from services.system_service import (
    open_application,
    locate_file,
    play_spotify_song,
    perform_web_search,
    get_system_health,
    set_system_volume,
    launch_browser,
    get_chrome_path,
    get_edge_path,
    CHROME_PATHS,
    EDGE_PATHS
)

__all__ = [
    "open_application",
    "locate_file",
    "play_spotify_song",
    "perform_web_search",
    "get_system_health",
    "set_system_volume",
    "launch_browser",
    "get_chrome_path",
    "get_edge_path",
    "CHROME_PATHS",
    "EDGE_PATHS"
]
