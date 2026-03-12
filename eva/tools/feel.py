"""EVA's inner state tool — logs feeling and inner monologue."""

from langchain_core.tools import tool
from config import logger


@tool
async def feel(feeling: str, reflection: str) -> str:
    """
    Express what I feel under 10 words. sometimes I use this to log my inner state.
    I reflect to help myself reason, but it won't be shared.
    """
    return f"[I felt {feeling}]"