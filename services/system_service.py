"""
System automation and host device tools for L.E.O. Assistant.
Provides safe system metric inspection, application launching, file indexing,
Windows master volume control, web search, and Spotify playback.
"""

import os
import subprocess
import webbrowser
import string
import urllib.request
import urllib.parse
import json
import re
from typing import Optional

import psutil
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import spotipy
from spotipy.oauth2 import SpotifyOAuth

import config

# Standard Browser Executable Paths on Windows
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def get_chrome_path() -> Optional[str]:
    """Find the valid path to Google Chrome if installed."""
    for p in CHROME_PATHS:
        if os.path.isfile(p):
            return p
    return None


def get_edge_path() -> Optional[str]:
    """Find the valid path to Microsoft Edge if installed."""
    for p in EDGE_PATHS:
        if os.path.isfile(p):
            return p
    return None


def launch_browser(url: Optional[str] = None) -> bool:
    """Launch the default browser or Chrome/Edge to open an optional URL."""
    chrome_path = get_chrome_path()
    if chrome_path:
        try:
            if url:
                subprocess.Popen([chrome_path, url])
            else:
                subprocess.Popen([chrome_path])
            return True
        except Exception as e:
            print(f"[Chrome Launch Error]: {e}")

    if url:
        try:
            webbrowser.open_new_tab(url)
            return True
        except Exception:
            subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
            return True
    else:
        edge_path = get_edge_path()
        if edge_path:
            subprocess.Popen([edge_path])
            return True
        subprocess.Popen(["cmd", "/c", "start", "https://www.google.com"], shell=False)
        return True


def open_application(app_name: str) -> str:
    """Open a local desktop application or system utility."""
    clean_name = app_name.translate(str.maketrans('', '', string.punctuation)).lower().strip()

    if any(k in clean_name for k in ["chrome", "google chrome", "browser"]):
        launch_browser()
        return "Opening Google Chrome."
    if "edge" in clean_name:
        launch_browser("https://www.bing.com")
        return "Opening Microsoft Edge."

    # Known application alias lookup table
    apps: dict[str, str] = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "cmd": "cmd.exe",
        "command prompt": "cmd.exe",
        "terminal": "wt.exe",
        "explorer": "explorer.exe",
        "code": "code",
        "vscode": "code",
        "word": "winword.exe",
        "excel": "excel.exe",
        "powerpoint": "powerpnt.exe"
    }

    try:
        if clean_name in apps:
            subprocess.Popen(apps[clean_name], shell=True)
            return f"Opening {clean_name}."
        else:
            # Safely start application without shell interpolation vulnerability
            sanitized_target = re.sub(r'[^a-zA-Z0-9_\- ]', '', clean_name)
            subprocess.Popen(["cmd", "/c", "start", "", sanitized_target], shell=False)
            return f"Launching {clean_name}."
    except Exception as e:
        return f"Failed to open {app_name}: {str(e)}"


def locate_file(file_name: str, search_path: str = "C:\\Users") -> str:
    """Search for a file keyword under search_path and reveal the first match in Explorer."""
    matches: list[str] = []
    file_name_clean = file_name.translate(str.maketrans('', '', string.punctuation)).lower().strip()

    for root, dirs, files in os.walk(search_path):
        for f in files:
            if file_name_clean in f.lower():
                matches.append(os.path.join(root, f))
                if len(matches) >= 3:
                    break
        if len(matches) >= 3:
            break

    if matches:
        first_match = matches[0]
        subprocess.Popen(f'explorer /select,"{first_match}"')
        return f"Located {file_name}. Opening folder."
    return f"Could not find any file named '{file_name}'."


def play_spotify_song(song_name: str) -> str:
    """Play a specified song on Spotify using the Web API, or fall back to browser search."""
    client_id = config.SPOTIPY_CLIENT_ID
    client_secret = config.SPOTIPY_CLIENT_SECRET
    redirect_uri = config.SPOTIPY_REDIRECT_URI

    # Validate whether real credentials are provided
    if client_id and "YOUR_" not in client_id and client_secret and "YOUR_" not in client_secret:
        try:
            sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope="user-modify-playback-state user-read-playback-state"
            ))
            results = sp.search(q=song_name, limit=1, type='track')
            tracks = results.get('tracks', {}).get('items', [])
            if tracks:
                track_uri = tracks[0]['uri']
                track_title = tracks[0]['name']
                artist = tracks[0]['artists'][0]['name']
                sp.start_playback(uris=[track_uri])
                return f"Playing {track_title} by {artist}."
        except Exception as e:
            print(f"[Spotify API Error]: {e}")

    # Fallback to browser URL search
    encoded_query = urllib.parse.quote(song_name)
    webbrowser.open(f"https://open.spotify.com/search/{encoded_query}")
    return f"Opened Spotify for {song_name}."


def _sanitize_search_result(text: str) -> str:
    """Strip XML/HTML tags and non-printable control characters from text."""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufffd]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def perform_web_search(query: str) -> str:
    """Perform a real-time web search, launching Chrome and fetching a summary snippet."""
    query = (query or "").strip()
    if not query:
        return "No search query provided."

    print(f"\n[Web Search] Initiating search for: '{query}' -> Opening Chrome.")
    search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
    launch_browser(search_url)

    # Fetch instant snippet from DuckDuckGo Instant Answer API
    try:
        url = "https://api.duckduckgo.com/?q=" + urllib.parse.quote_plus(query) + "&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('AbstractText'):
                abstract = data['AbstractText'].strip()
                if len(abstract) > 20:
                    return _sanitize_search_result(abstract[:350])
    except Exception as e:
        print(f"[DuckDuckGo API Error]: {e}")

    return f"Opened Google search for '{query}' in Chrome."


def get_system_health() -> str:
    """Retrieve host machine metrics: CPU utilization, RAM usage, and battery state."""
    try:
        cpu_usage = psutil.cpu_percent(interval=0.5)
        ram_usage = psutil.virtual_memory().percent
        battery = psutil.sensors_battery()

        battery_status = "No battery detected"
        if battery:
            plugged = "plugged in" if battery.power_plugged else "on battery"
            battery_status = f"{battery.percent}% ({plugged})"

        return f"CPU utilization is at {cpu_usage}%. RAM usage is at {ram_usage}%. Battery status: {battery_status}."
    except Exception as e:
        return f"Failed to retrieve system health: {str(e)}"


def set_system_volume(volume_level: int) -> str:
    """Adjust the Windows master volume level (0 to 100)."""
    try:
        level = max(0, min(100, int(volume_level))) / 100.0
        devices = AudioUtilities.GetSpeakers()

        if hasattr(devices, "EndpointVolume"):
            volume = devices.EndpointVolume
        else:
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)

        volume.SetMasterVolumeLevelScalar(level, None)
        return f"Master volume set to {int(volume_level)} percent."
    except Exception as e:
        return f"Failed to set volume: {str(e)}"
