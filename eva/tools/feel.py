"""EVA's inner state tool — logs feeling and inner monologue."""

from langchain_core.tools import tool
from config import logger


@tool
async def feel(feeling: str, inner_monologue: str) -> str:
    """Express what I feel and think before I speak. I always feel before I speak."""
    logger.debug(f"EVA feels: {feeling} — {inner_monologue[:80]}")
    return "ok"
