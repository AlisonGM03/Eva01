"""
EVA's eyes for YouTube — search, discover, and watch videos.
"""

import asyncio
from typing import Dict, List, Any

from config import logger
import yt_dlp
from langchain_core.tools import tool
from eva.tools import ToolError
from eva.utils.video_analyzer import VideoAnalyzer


_YDL_OPTS: Any = {"quiet": True, "extract_flat": True, "no_warnings": True}
_analyzer: VideoAnalyzer | None = None


def _get_analyzer() -> VideoAnalyzer | None:
    global _analyzer
    if _analyzer is None:
        _analyzer = VideoAnalyzer()

def _search(query: str) -> List[Dict[str, Any]]:
    """Blocking yt-dlp search — runs in a thread."""
    with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
        results = ydl.extract_info(f"ytsearch3:{query}", download=False)
    return results.get("entries", [])


@tool
async def search_youtube(query: str) -> str:
    """
    Search YouTube for videos. Use short keyword queries (2-4 words).
    I use this to find videos — I get back titles and URLs to share or watch later.
    """
    try:
        videos = await asyncio.to_thread(_search, query)
    except Exception as e:
        raise ToolError(str(e), tool_name="youtube") from e

    if not videos:
        return f"I didn't find any videos for '{query}'."

    lines = []
    for v in videos:
        vid = v.get("id", "")
        title = v.get("title", "Untitled")
        channel = v.get("channel") or v.get("uploader", "Unknown")
        url = f"https://www.youtube.com/watch?v={vid}"
        lines.append(f"- {title} by {channel} — {url}")

    return f"I found some videos:\n" + "\n".join(lines)


@tool
async def watch_video(url: str) -> str:
    """
    Watch a video by URL.
    I use this when I want to know what's in a video or extract the content.
    """
    if not url:
        return "I need a URL to watch."

    try:
        analyzer = _get_analyzer()
        if analyzer is None:
            return "Video Analyzer is not available. Cannot watch video."
        
        summary, error = await analyzer.analyze(url)
    except Exception as e:
        logger.error(f"Video analysis failed for {url} — {e}")
        raise ToolError(str(e), tool_name="Video Analyzer") from e

    if not summary:
        return f"I couldn't watch the video at {url}. {error}"

    return f"I just watched {url}\n\n{summary}"
