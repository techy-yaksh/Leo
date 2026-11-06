"""
==============================================================================
AI AGENT SERVICE // GROQ LPU + GEMINI 3.8 FLASH MULTIMODAL VISION
==============================================================================
Orchestrates dual-API AI capabilities:
- Groq LPU (openai/gpt-oss-120b) with real-time token streaming and function calling.
- Google Gemini 3.8 Flash (gemini-3.8-flash) for multimodal screen analysis.
"""

import json
from typing import Any, Callable, Generator
from groq import Groq

import config
from services.system_service import (
    open_application,
    locate_file,
    play_spotify_song,
    perform_web_search,
    get_system_health,
    set_system_volume,
)
from services.vision_service import capture_screen_b64, analyze_screen_with_gemini

# Initialize Groq client securely from central config
groq_client: Groq | None = None
if config.GROQ_API_KEY and "your_" not in config.GROQ_API_KEY.lower():
    try:
        groq_client = Groq(api_key=config.GROQ_API_KEY)
    except Exception as e:
        print(f"[Groq Init Error]: {e}")
        groq_client = None

conversation_history: list[dict[str, Any]] = []


def tool_analyze_screen(custom_prompt: str = "Analyze what is visible on my screen.") -> str:
    """Tool wrapper: captures screen and invokes Gemini 3.8 Flash."""
    b64_img = capture_screen_b64()
    return analyze_screen_with_gemini(custom_prompt, b64_img=b64_img)


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "analyze_screen",
            "description": "Capture the primary computer monitor and analyze screen contents using Gemini 3.8 Flash.",
            "parameters": {
                "type": "object",
                "properties": {
                    "custom_prompt": {
                        "type": "string",
                        "description": "Specific query regarding what to inspect on the user's screen."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_health",
            "description": "Get current system metrics including CPU percentage, RAM usage, and battery status.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_system_volume",
            "description": "Adjust the system master volume level.",
            "parameters": {
                "type": "object",
                "properties": {
                    "volume_level": {
                        "type": "integer",
                        "description": "Target volume percentage 0 to 100."
                    }
                },
                "required": ["volume_level"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open a local desktop application (e.g., notepad, calculator, chrome, terminal, code).",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "The name of the application to open."
                    }
                },
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "locate_file",
            "description": "Locate a file on the host machine and reveal it in File Explorer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_name": {
                        "type": "string",
                        "description": "The target filename or keyword."
                    }
                },
                "required": ["file_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_spotify_song",
            "description": "Play a track on Spotify or search for it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "song_name": {
                        "type": "string",
                        "description": "Name of the song or artist."
                    }
                },
                "required": ["song_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "perform_web_search",
            "description": "Perform a real-time web search for current information or specific queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query keywords."
                    }
                },
                "required": ["query"]
            }
        }
    }
]

TOOL_MAP: dict[str, Callable[..., str]] = {
    "analyze_screen": tool_analyze_screen,
    "open_application": open_application,
    "locate_file": locate_file,
    "play_spotify_song": play_spotify_song,
    "perform_web_search": perform_web_search,
    "get_system_health": get_system_health,
    "set_system_volume": set_system_volume
}


def process_agent_command_stream(user_input: str) -> Generator[dict[str, Any], None, None]:
    """
    Stream tokens in real-time from Groq LPU, or route to Gemini 3.8 Flash multimodal vision.
    Yields events:
      {"type": "status", "data": "..."}
      {"type": "token", "data": "..."}
      {"type": "tool_start", "data": "..."}
      {"type": "final", "data": "..."}
    """
    global conversation_history, groq_client

    if not user_input:
        return

    # ========================================================================
    # PHASE 4.3 & 4.4: SCREEN VISION TRIGGER DETECTION & GEMINI INVOCATION
    # ========================================================================
    lower_input = user_input.lower().strip()
    vision_triggers = [
        "what is on my screen", "what's on my screen", "look at this",
        "look at my screen", "what do you see", "read my screen",
        "analyze my screen", "analyze screen", "see my screen", "on my screen"
    ]

    if any(trigger in lower_input for trigger in vision_triggers):
        print(f"\n[Vision Pipeline Triggered] User query matched screen vision trigger: '{user_input}'")
        yield {"type": "status", "data": "Capturing primary display via MSS..."}

        # Step 1: Capture primary screen as base64 JPEG
        b64_image = capture_screen_b64()

        yield {"type": "status", "data": f"Analyzing screen frame with {config.GEMINI_MODEL}..."}

        # Step 2: Append base64 image data to Gemini multimodal payload
        analysis_result = analyze_screen_with_gemini(user_input, b64_img=b64_image)

        # Record in conversational memory
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": analysis_result})

        yield {"type": "token", "data": analysis_result}
        yield {"type": "final", "data": analysis_result}
        return

    # Standard Conversational & System Tool Path via Groq
    if not groq_client:
        msg = "I am online. Please set a valid GROQ_API_KEY in your .env file."
        yield {"type": "token", "data": msg}
        yield {"type": "final", "data": msg}
        return

    conversation_history.append({"role": "user", "content": user_input})
    system_prompt = {
        "role": "system",
        "content": (
            "You are L.E.O., an intelligent, cutting-edge cybernetic desktop orchestrator. "
            "Maintain conversational context from previous turns. Route user commands to appropriate "
            "functions when requested, or provide direct, comprehensive, and engaging conversational answers. "
            "Never truncate or prematurely cut off your explanations."
        )
    }
    messages_to_send = [system_prompt] + conversation_history[-config.MAX_CONVERSATION_HISTORY:]

    try:
        # Step 1: Detect if a system tool needs execution
        initial_response = groq_client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=messages_to_send,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=config.GROQ_MAX_TOKENS
        )
        response_message = initial_response.choices[0].message

        # Execute mapped tools if requested by model
        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                yield {"type": "tool_start", "data": f"Executing system tool: {func_name}..."}

                if func_name in TOOL_MAP:
                    tool_result = TOOL_MAP[func_name](**func_args)
                    conversation_history.append({"role": "assistant", "content": tool_result})
                    yield {"type": "token", "data": tool_result}
                    yield {"type": "final", "data": tool_result}
                    return

        # Step 2: Stream response tokens with zero latency
        stream_response = groq_client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=messages_to_send,
            stream=True,
            max_tokens=config.GROQ_MAX_TOKENS
        )

        full_content: list[str] = []
        for chunk in stream_response:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                full_content.append(delta)
                yield {"type": "token", "data": delta}

        complete_text = "".join(full_content).strip()
        conversation_history.append({"role": "assistant", "content": complete_text})
        yield {"type": "final", "data": complete_text}

    except Exception as e:
        err_msg = f"System error: {str(e)}"
        print(f"[Agent Execution Error]: {e}")
        yield {"type": "token", "data": err_msg}
        yield {"type": "final", "data": err_msg}


def process_agent_command(user_input: str) -> str:
    """Synchronous convenience wrapper over the streaming generator."""
    final_text = ""
    for event in process_agent_command_stream(user_input):
        if event["type"] == "final":
            final_text = event["data"]
    return final_text
