"""EVA's window to the internet — searches the web via Perplexity Sonar."""

import re
from config import logger
from langchain_core.tools import tool
from langchain_perplexity import ChatPerplexity

_llm: ChatPerplexity | None = None


@tool
async def web_search(query: str) -> str:
    """Search the web with a query. I use this when I need to look something up."""
    global _llm
    if _llm is None:
        _llm = ChatPerplexity(temperature=0.1, timeout=30)

    try:
        response = await _llm.ainvoke(query)
        return str(response.content)
    
    except Exception as e:
        logger.error(f"web search error: {e}")
        raise e