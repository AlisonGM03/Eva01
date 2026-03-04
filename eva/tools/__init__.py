"""
EVA's tools — auto-discovered from this package.

Convention for tool files:
    - @tool decorated function  →  collected directly
    - make_* factory function   →  called with action_buffer, result collected
"""

import importlib
import os

from langchain_core.tools import BaseTool

from config import logger
from eva.actions.action_buffer import ActionBuffer


def load_tools(action_buffer: ActionBuffer) -> list[BaseTool]:
    """Scan this folder, import each module, collect tools."""

    tools = []
    pkg_dir = os.path.dirname(__file__)

    for filename in sorted(os.listdir(pkg_dir)):
        if not filename.endswith(".py") or filename == "__init__.py":
            continue

        module_name = filename[:-3]
        try:
            module = importlib.import_module(f".{module_name}", package=__package__)
        except Exception as e:
            logger.warning(f"Tools: skipped {module_name} — {e}")
            continue

        for attr_name in dir(module):
            obj = getattr(module, attr_name)

            # Ready-to-use @tool instances
            if isinstance(obj, BaseTool):
                tools.append(obj)
                logger.debug(f"Tools: loaded {obj.name}")

            # Factories: make_*(...) → BaseTool
            elif callable(obj) and attr_name.startswith("make_"):
                try:
                    tool = obj(action_buffer)
                    tools.append(tool)
                    logger.debug(f"Tools: loaded {tool.name} (factory)")
                except Exception as e:
                    logger.warning(f"Tools: factory {attr_name} failed — {e}")

    return tools
