import asyncio
import json
import secrets
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import WebSocket

from config import logger
from eva.client.data_manager import DataManager
from eva.utils.tts import Speaker


HTML_DIR = Path(__file__).parent / "html"


class MobileClient:
    """
    Client interface for the React frontend, communicating over WebSocket.
    
    Lifecycle:
        1. `initialize_modules()` — called at startup to attach the TTS model.
        2. `attach_session()` — called per-connection to bind the live WebSocket
           and DataManager for that session.
    """

    def __init__(self):
        self.session_id: Optional[str] = None
        self.websocket: Optional[WebSocket] = None
        self.data_manager: Optional[DataManager] = None
        self.speaker: Optional[Speaker] = None

    def initialize_modules(self, tts_model: Speaker) -> None:
        """Store the TTS model. STT and vision are owned by DataManager in server.py."""
        self.speaker = tts_model

    def attach_session(self, websocket: WebSocket, data_manager: DataManager) -> None:
        """Bind the active WebSocket and DataManager for the current session."""
        self.websocket = websocket
        self.data_manager = data_manager

    # ── Core send / receive ─────────────────────────────────────────────────

    async def _send(self, payload: str) -> None:
        await self.websocket.send_text(payload)

    async def send(self, data: Dict) -> None:
        """Generate TTS audio and push the response packet to the frontend."""
        if not data or "speech" not in data:
            logger.warning(f"send() called with invalid data: {data}")
            return

        speech_text = data["speech"]
        audio_path = self.speaker.get_audio(speech_text)

        payload = json.dumps([{
            "session_id": self.session_id,
            "type": "audio",
            "content": audio_path,
            "text": speech_text,
        }])
        await self._send(payload)

    async def send_over(self) -> None:
        """Signal to the frontend that the current response package is complete."""
        payload = json.dumps({
            "type": "over",
            "content": self._new_session_id(),
        })
        await self._send(payload)

    async def receive(self) -> Dict:
        """Wait for the next fully processed user turn from DataManager."""
        while True:
            user_input = self.data_manager.get_first_data()
            if user_input:
                break
            await asyncio.sleep(0.2)

        self.session_id = user_input.get("session_id")
        message, language = user_input.get("user_message", (None, None))

        return {
            "user_message": message,
            "observation": user_input.get("observation", "<|same|>"),
            "language": language,
        }

    async def start(self) -> Dict:
        """Wait for the first message from the frontend to begin the session."""
        while True:
            user_input = self.data_manager.get_first_data()
            if user_input and user_input.get("observation"):
                break
            await asyncio.sleep(0.2)

        self.session_id = user_input.get("session_id")
        return {"observation": user_input["observation"]}

    async def speak(self, response: str, wait: bool = True) -> None:
        """ Speak a single response to the client """
        await self.send({"speech": response, "wait": wait})

    async def deactivate(self) -> None:
        """ Deactivate the client. """
        pass

    # ── Media helpers ───────────────────────────────────────────────────────

    async def stream_music(self, mp3_url: str, cover_url: str, title: str) -> Dict:
        """Push a music player page and stream URL to the frontend."""
        try:
            page = self._render_html("music", image_url=cover_url, music_title=title)
            payload = json.dumps([
                {"session_id": self.session_id, "type": "mp3", "content": mp3_url},
                {"type": "html", "content": page},
            ])
            await self._send(payload)
            return {"user_message": f"Media Player:: The song '{title}' is playing."}
        except Exception as e:
            logger.error(f"Failed to stream music: {e}")
            return {}

    async def launch_youtube(self, video_id: str, title: str) -> Dict:
        """Push a YouTube player page to the frontend."""
        try:
            page = self._render_html("youtube", video_id=video_id, video_title=title)
            payload = json.dumps({
                "session_id": self.session_id,
                "type": "html",
                "content": page,
            })
            await self._send(payload)
            return {"observation": "The video player is launched."}
        except Exception as e:
            logger.error(f"Failed to launch YouTube: {e}")
            return {}

    async def launch_epad(self, html: str) -> Dict:
        """Push a custom HTML page to the frontend epad."""
        try:
            page = self._render_html("blank", full_html=html)
            payload = json.dumps({
                "session_id": self.session_id,
                "type": "html",
                "content": page,
            })
            await self._send(payload)
            return {"observation": "The epad is launched."}
        except Exception as e:
            logger.error(f"Failed to launch epad: {e}")
            return {}

    # ── Internal utilities ──────────────────────────────────────────────────

    def _render_html(self, template: str, **kwargs) -> str:
        """Load an HTML template and substitute placeholder tags."""
        html_path = HTML_DIR / f"{template}.html"
        try:
            html = html_path.read_text().strip()
        except FileNotFoundError:
            raise FileNotFoundError(f"HTML template not found: {html_path}")
        for key, value in kwargs.items():
            html = html.replace(f"<{key}>", value)
        return html

    def _new_session_id(self) -> str:
        return secrets.token_urlsafe(16)

    def __repr__(self) -> str:
        return "MobileClient"
