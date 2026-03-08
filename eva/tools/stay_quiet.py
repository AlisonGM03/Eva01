"""EVA's silence tool — a conscious choice not to speak."""

from langchain_core.tools import tool
from config import logger


@tool
async def stay_quiet(reason: str) -> str:
    """Choose not to speak. I use this when I want to be silent."""
    logger.debug(f"Eva stays quiet: {reason}")
    return "ok"

stay_quiet.passive = True
