from config import logger
import numpy as np
import base64

import cv2

from eva.utils.prompt import load_prompt


class Describer:
    """EVA's visual cortex — preprocesses images and delegates to a vision model."""

    def __init__(self, model_name: str):
        self.model = self._initialize_model(model_name)
        logger.debug(f"Describer: {model_name} is ready.")

    def _initialize_model(self, model_name: str):
        from .model_cloud import CloudVision
        return CloudVision(model_name)

    def _convert_base64(self, image_data: np.ndarray | str) -> str:
        if isinstance(image_data, str):
            return image_data
        _, buffer = cv2.imencode('.jpg', image_data)
        return base64.b64encode(buffer).decode('utf-8')

    async def describe(self, image_data: np.ndarray | str) -> str | None:
        try:
            image_base64 = self._convert_base64(image_data)
            prompt = load_prompt("vision")
            return await self.model.generate(prompt, image_base64)
        except Exception as e:
            logger.error(f"Describer: failed — {e}")
            return None

    async def analyze_screenshot(self, image_data: np.ndarray | str, query: str) -> str | None:
        try:
            image_base64 = self._convert_base64(image_data)
            return await self.model.generate(f"Describe the screenshot, {query}.", image_base64)
        except Exception as e:
            logger.error(f"Describer: screenshot failed — {e}")
            return None
