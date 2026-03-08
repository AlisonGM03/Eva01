"""
Base interface for all EVA actions (physical or digital presence).
"""

from abc import ABC, abstractmethod

class BaseAction(ABC):
    """
    Standard interface for all actions that EVA can perform.
    Actions register to the ActionBuffer and handle their own lifecycle.
    """

    @abstractmethod
    def register(self, buffer: "ActionBuffer") -> None: #type: ignore
        """Register listeners to the ActionBuffer."""
        pass

    async def start(self) -> None:
        """Optional: Start any background tasks needed by the action."""
        pass

    async def stop(self) -> None:
        """Optional: Cleanup resources, cancel tasks, release models."""
        pass
