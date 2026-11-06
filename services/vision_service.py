"""
==============================================================================
PHASE 4: SCREEN VISION PIPELINE (MSS + GEMINI MULTIMODAL)
==============================================================================
Captures the primary monitor using the `mss` library, converts raw pixels to a
PIL Image, downscales, and encodes to a base64 JPEG string.
Integrates natively with Gemini 3.8 Flash (gemini-3.8-flash) for multimodal analysis.
"""

import io
import os
import time
import base64
from typing import Optional
from PIL import Image

import config

# Try importing mss first, fallback to PIL.ImageGrab if unavailable
try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

from PIL import ImageGrab

# Try importing google.genai
try:
    from google import genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


# ============================================================================
# PHASE 4.1 & 4.2: STANDALONE SCREEN CAPTURE FUNCTION (MSS -> PIL -> BASE64)
# ============================================================================
def capture_screen_b64(max_width: int = 1600, max_height: int = 1000) -> str:
    """
    Silently captures the primary display using the `mss` library,
    converts the raw BGRA pixel buffer into a PIL RGB Image,
    downscales if needed to preserve network bandwidth/tokens,
    and returns an encoded base64 JPEG string.
    """
    img: Optional[Image.Image] = None

    # Step 1: Attempt silent capture via mss
    if HAS_MSS:
        try:
            with mss.mss() as sct:
                # Primary monitor is sct.monitors[1] on multi-monitor setups, or [0] as fallback
                primary = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                sct_img = sct.grab(primary)
                # Convert raw pixels directly to PIL Image
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                print(f"[Vision Capture] Primary screen grabbed via MSS ({img.width}x{img.height}).")
        except Exception as e:
            print(f"[Vision Capture Warning - MSS]: {e}. Attempting PIL ImageGrab fallback...")

    # Step 2: Fallback to PIL ImageGrab if MSS was unavailable or blocked
    if img is None:
        try:
            img = ImageGrab.grab()
            print(f"[Vision Capture] Screen grabbed via PIL ImageGrab ({img.width}x{img.height}).")
        except Exception as e2:
            print(f"[Vision Capture Critical Error]: Failed to grab screen with ImageGrab: {e2}")
            return ""

    # Step 3: Downscale if image exceeds max dimensions (preserves aspect ratio)
    if img.width > max_width or img.height > max_height:
        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

    # Step 4: Encode to JPEG in-memory and convert to base64 string
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85, optimize=True)
    jpeg_bytes = buffer.getvalue()
    b64_string = base64.b64encode(jpeg_bytes).decode("utf-8")

    print(f"[Vision Capture] Successfully encoded image to base64 ({len(b64_string) // 1024} KB).")
    return b64_string


# ============================================================================
# PHASE 4.3 & 4.4: GEMINI 3.8 FLASH MULTIMODAL INTEGRATION
# ============================================================================
def analyze_screen_with_gemini(prompt: str, b64_img: Optional[str] = None) -> str:
    """
    Sends the user prompt and the base64 screen image to the `gemini-3.8-flash`
    multimodal model using the official Google GenAI SDK.
    """
    start_time = time.time()
    b64_data = b64_img or capture_screen_b64()

    if not b64_data:
        return (
            "Screen capture failed: unable to access desktop graphics context. "
            "Please ensure your screen is unlocked and permissions are granted."
        )

    api_key = config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "").strip()

    # Fallback to Groq Vision if GEMINI_API_KEY is not set
    if not api_key:
        if config.GROQ_API_KEY:
            try:
                from groq import Groq
                groq_client = Groq(api_key=config.GROQ_API_KEY)
                print("[Vision Pipeline] GEMINI_API_KEY not set. Using Groq Vision as fallback...")
                chat_completion = groq_client.chat.completions.create(
                    model="llama-3.2-11b-vision-preview",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}
                                }
                            ]
                        }
                    ],
                    max_tokens=1000
                )
                analysis = chat_completion.choices[0].message.content or ""
                print(f"[Vision Pipeline] Groq vision analysis completed in {time.time() - start_time:.2f}s.")
                return analysis.strip()
            except Exception as e:
                print(f"[Vision Groq Fallback Error]: {e}")

        return (
            "Screen captured successfully! However, GEMINI_API_KEY is not set in your .env file. "
            "Please add your free API key at https://aistudio.google.com/ to unlock Gemini 3.8 Flash vision."
        )

    if not HAS_GENAI:
        return "The google-genai package is required. Run 'pip install google-genai'."

    try:
        print(f"[Vision Pipeline] Invoking {config.GEMINI_MODEL} with multimodal image payload...")
        client = genai.Client(api_key=api_key)

        # Gemini 3.8 Flash natively accepts multimodal inputs via Interactions API
        interaction = client.interactions.create(
            model=config.GEMINI_MODEL,
            input=[
                {"type": "text", "text": prompt},
                {"type": "image", "data": b64_data, "mime_type": "image/jpeg"}
            ]
        )

        analysis = (interaction.output_text or "").strip()
        print(f"[Vision Pipeline] Gemini 3.8 Flash analysis completed in {time.time() - start_time:.2f}s.")
        return analysis

    except Exception as e:
        print(f"[Vision Error - Interactions API]: {e}. Attempting generate_content fallback...")
        try:
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=[
                    prompt,
                    {"mime_type": "image/jpeg", "data": base64.b64decode(b64_data)}
                ]
            )
            return (response.text or "").strip()
        except Exception as ex2:
            return f"Error analyzing screen via Gemini: {str(ex2)}"
