from config import logger
from typing import Optional

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage


class CloudVision:
    """Unified cloud vision model via LangChain — supports any provider (openai, groq, ollama, etc.)."""

    def __init__(self, model_name: str, temperature: float = 0.1):
        self.model = init_chat_model(model_name, temperature=temperature)

    async def generate(self, prompt: str, image: str) -> Optional[str]:
        """Send a prompt + base64 image to the vision model. Returns description text."""
        message = HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
        ])
        response = await self.model.ainvoke([message])
        return response.content
