import os
import sys
import subprocess
import webbrowser
import threading
import asyncio
import string
import uuid
import logging
import numpy as np
import pyaudio
import webview
from flask import Flask, render_template, request, jsonify

# Neural Voice, Offline Wake-Word, & Speech Recognition
import edge_tts
import pygame
import openwakeword.utils
from openwakeword.model import Model
import speech_recognition as sr

# --- ULTRA-FAST FREE AI: Groq API ---
from groq import Groq

import spotipy
from spotipy.oauth2 import SpotifyOAuth
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

# ==========================================
# 1. INITIALIZATION & SETUP
# ==========================================
# PASTE YOUR GROQ API KEY HERE
GROQ_KEY = os.getenv("GROQ_API_KEY") or "YOUR_API_KEY_HERE"

# Silence Werkzeug HTTP console logs to keep output clean
logging.getLogger('werkzeug').setLevel(logging.ERROR)

app = Flask(__name__, template_folder='.')
pygame.mixer.init()


    
# Initialize Groq Client
if GROQ_KEY and "YOUR_" not in GROQ_KEY:
    groq_client = Groq(api_key=GROQ_KEY)
    
    # --- STEP 2: PRINT AVAILABLE MODELS FOR DIAGNOSTICS ---
    try:
        models = groq_client.models.list()
        print("\n--- Available Groq Models for your API Key ---")
        for m in models.data:
            print(f" - {m.id}")
        print("----------------------------------------------\n")
    except Exception as e:
        print(f"[Key Check Error]: {e}")
    # ------------------------------------------------------

else:
    groq_client = None

window_instance = None

recognizer = sr.Recognizer()
recognizer.energy_threshold = 150  
recognizer.dynamic_energy_threshold = False

# Global HUD State tracking for Frontend Sync
hud_status = {
    "user_text": "Hands-free mode active...", 
    "leo_text": "Online and waiting.", 
    "state": "idle"
}

# ==========================================
# 2. HIGH-QUALITY NEURAL TTS
# ==========================================
def speak(text):
    """Generates TTS and blocks execution so the mic doesn't listen to its own audio."""
    async def _generate(filename):
        voice = "en-US-GuyNeural"
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(filename)

    unique_file = f"leo_speech_{uuid.uuid4().hex[:8]}.mp3"
    try:
        asyncio.run(_generate(unique_file))
        pygame.mixer.music.load(unique_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
        if os.path.exists(unique_file):
            os.remove(unique_file)
    except Exception as e:
        print(f"[TTS Error] {e}")

# ==========================================
# 3. SYSTEM CONTROLS & AI RESPONSES
# ==========================================
def open_application(app_name):
    app_name = app_name.translate(str.maketrans('', '', string.punctuation)).lower().strip()
    
    apps = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "cmd": "cmd.exe",
        "command prompt": "cmd.exe",
        "terminal": "wt.exe",
        "explorer": "explorer.exe",
        "chrome": "chrome.exe",
        "edge": "msedge.exe",
        "code": "code",
        "word": "winword.exe",
        "excel": "excel.exe",
        "powerpoint": "powerpnt.exe"
    }

    try:
        if app_name in apps:
            subprocess.Popen(apps[app_name], shell=True)
            return f"Opening {app_name}."
        else:
            os.system(f"start {app_name}")
            return f"Launching {app_name}."
    except Exception as e:
        return f"Failed to open {app_name}: {str(e)}"

def locate_file(file_name, search_path="C:\\Users"):
    matches = []
    file_name = file_name.translate(str.maketrans('', '', string.punctuation)).lower().strip()
    for root, dirs, files in os.walk(search_path):
        for f in files:
            if file_name in f.lower():
                matches.append(os.path.join(root, f))
                if len(matches) >= 3: break
        if len(matches) >= 3: break
            
    if matches:
        first_match = matches[0]
        subprocess.Popen(f'explorer /select,"{first_match}"')
        return f"Located {file_name}. Opening folder."
    return f"Could not find any file named '{file_name}'."

SPOTIPY_CLIENT_ID = 'YOUR_SPOTIFY_CLIENT_ID'
SPOTIPY_CLIENT_SECRET = 'YOUR_SPOTIFY_CLIENT_SECRET'
SPOTIPY_REDIRECT_URI = 'http://127.0.0.1:8888/callback'

def play_spotify_song(song_name):
    if SPOTIPY_CLIENT_ID != 'YOUR_SPOTIFY_CLIENT_ID':
        try:
            sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET,
                redirect_uri=SPOTIPY_REDIRECT_URI, scope="user-modify-playback-state user-read-playback-state"
            ))
            results = sp.search(q=song_name, limit=1, type='track')
            tracks = results.get('tracks', {}).get('items', [])
            if tracks:
                track_uri = tracks[0]['uri']
                track_title, artist = tracks[0]['name'], tracks[0]['artists'][0]['name']
                sp.start_playback(uris=[track_uri])
                return f"Playing {track_title} by {artist}."
        except Exception:
            pass
    webbrowser.open(f"https://open.spotify.com/search/{song_name}")
    return f"Opened Spotify for {song_name}."

def perform_web_search(query):
    try:
        results = DDGS().text(query, max_results=2)
        if results:
            summary = " ".join([r.get('body', '') for r in results if r.get('body')])
            return summary[:300] if summary else "No summary available."
        return "No search results found."
    except Exception as e:
        return f"Search error: {str(e)}"

def ask_ai(user_input):
    """Generates direct conversational responses using Groq LPU speed."""
    if not groq_client:
        return "I am online. Paste your free Groq API key in leo_backend.py to start chatting."
    try:
        response = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": "You are Leo, a reliable, witty, and grounded AI system assistant. Keep responses direct, friendly, concise, and conversational (under 2-3 sentences)."
                },
                {"role": "user", "content": user_input}
            ],
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[AI Error]: {e}")
        return f"AI error: {str(e)}"

# ==========================================
# 4. COMMAND LOGIC & FLASK ENDPOINTS
# ==========================================
def execute_intent(user_text):
    global hud_status
    if not user_text: 
        hud_status["state"] = "idle"
        return ""
    
    clean_text = user_text.translate(str.maketrans('', '', string.punctuation)).lower().strip()
    print(f"\n[Command Received]: {clean_text}")
    
    hud_status["user_text"] = user_text
    hud_status["leo_text"] = "Thinking..."
    hud_status["state"] = "active"

    if "sleep" in clean_text or "go to sleep" in clean_text:
        response_text = "Entering standby mode."
        speak(response_text)
        if window_instance: window_instance.hide()
        hud_status["leo_text"] = response_text
        hud_status["state"] = "idle"
        return response_text

    if "exit" in clean_text or "quit" in clean_text:
        response_text = "Powering down system. Goodbye."
        speak(response_text)
        threading.Timer(1.5, lambda: os._exit(0)).start()
        hud_status["leo_text"] = response_text
        hud_status["state"] = "idle"
        return response_text

    if clean_text.startswith("open "):
        target = clean_text.replace("open ", "", 1).strip()
        response_text = open_application(target)
    elif "find file" in clean_text or "locate file" in clean_text:
        target = clean_text.replace("find file", "").replace("locate file", "").strip()
        response_text = locate_file(target)
    elif "play" in clean_text and "spotify" in clean_text:
        target = clean_text.replace("play", "").replace("on spotify", "").replace("spotify", "").strip()
        response_text = play_spotify_song(target)
    elif clean_text.startswith("search for ") or clean_text.startswith("google "):
        target = clean_text.replace("search for ", "").replace("google ", "").strip()
        response_text = perform_web_search(target)
    else:
        response_text = ask_ai(user_text)

    hud_status["leo_text"] = response_text
    hud_status["state"] = "idle"
    speak(response_text)
    return response_text

@app.route('/process_command', methods=['POST'])
def process_command():
    data = request.json or {}
    user_text = data.get('command', '').lower().strip()
    return jsonify({"response": execute_intent(user_text)})

@app.route('/get_hud_status', methods=['GET'])
def get_hud_status():
    return jsonify(hud_status)

@app.route('/')
def index():
    return render_template('leo_frontend.html')

# ==========================================
# 5. OFFLINE WAKE-WORD & MULTI-TURN LISTENER
# ==========================================
def listen_for_whisper():
    global hud_status
    with sr.Microphone() as source:
        sys.stdout.write("\n[L.E.O] Listening for command...\n")
        
        # Keep the state active, but don't overwrite user_text unless new audio comes in
        recognizer.adjust_for_ambient_noise(source, duration=0.3)
        
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
            command = recognizer.recognize_google(audio).lower()
            return command
        except sr.WaitTimeoutError:
            # Silent timeout: stay quiet so the previous answer remains displayed
            return ""
        except sr.UnknownValueError:
            # Couldn't transcribe (silence/background noise): don't show error text
            return ""
        except Exception as e:
            print(f"[Mic Error] {e}")
            return ""

def wake_word_listener():
    global window_instance, hud_status
    try:
        openwakeword.utils.download_models()
        model_name = "leo.onnx" if os.path.exists("leo.onnx") else "hey_jarvis"
        oww_model = Model(wakeword_models=[model_name], inference_framework="onnx")
        
        FORMAT, CHANNELS, RATE, CHUNK = pyaudio.paInt16, 1, 16000, 1280
        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
        
        print(f"\n[L.E.O] Active (Listening for: '{model_name}')...")
        spinner, frame_count = ['|', '/', '-', '\\'], 0

        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            audio_frame = np.frombuffer(data, dtype=np.int16)
            
            frame_count += 1
            if frame_count % 5 == 0:
                symbol = spinner[(frame_count // 5) % len(spinner)]
                sys.stdout.write(f"\r[Listening {symbol}] Mic active...")
                sys.stdout.flush()

            prediction = oww_model.predict(audio_frame)
            
            for m_name, score in prediction.items():
                if score > 0.3:
                    sys.stdout.write(f"\n\n[Triggered] Wake word detected!\n")
                    sys.stdout.flush()
                    
                    if window_instance:
                        window_instance.show()
                        window_instance.restore()
                    
                    stream.stop_stream()
                    speak("Online.")
                    
                    # Continuous conversation state
                    consecutive_silence_count = 0
                    
                    while True:
                        command = listen_for_whisper()
                        
                        if command:
                            consecutive_silence_count = 0
                            clean_cmd = command.lower().strip()
                            
                            if any(term in clean_cmd for term in ["sleep", "go to sleep", "nevermind", "that's all", "bye"]):
                                execute_intent(command)
                                break
                                
                            execute_intent(command)
                        else:
                            consecutive_silence_count += 1
                            # Exit to standby only after 3 consecutive silent timeout cycles (~15s)
                            if consecutive_silence_count >= 3:
                                hud_status["leo_text"] = "Going back to standby."
                                hud_status["state"] = "idle"
                                speak("Going to standby.")
                                break
                    
                    oww_model.reset()
                    stream.start_stream()
                    print("\n[L.E.O] Returned to standby...")

    except Exception as e:
        print(f"\n[Wake-word Error] {e}")
# ==========================================
# 6. APPLICATION ENTRY POINT
# ==========================================
def run_flask():
    app.run(port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=wake_word_listener, daemon=True).start()

    window_instance = webview.create_window(
        title="L.E.O. System Interface",
        url="http://127.0.0.1:5000",
        width=480, height=640,
        resizable=False, frameless=False,
        easy_drag=True, hidden=True
    )
    webview.start()