"""
EVA's mind.

Three concurrent components sharing two buffers:
    Senses  →  SenseBuffer  →  Brain  →  ActionBuffer  →  Actions
"""

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from config import logger, eva_configuration
from config.config import Config
from eva.core.graph import build_graph
from eva.senses import SenseBuffer, AudioSense, CameraSense
from eva.actions import ActionBuffer, VoiceActor
from eva.senses.audio.transcriber import Transcriber
from eva.senses.vision.describer import Describer
from eva.senses.vision.identifier import Identifier
from eva.actions.voice.speaker import Speaker
from eva.core.people import PeopleDB

DB_PATH = "data/database/eva_graph.db"


def _init_audio(config: Config) -> AudioSense:
    """Load transcriber and create AudioSense (blocking)."""
    transcriber = Transcriber(config.STT_MODEL, config.LANGUAGE)
    return AudioSense(transcriber, keyboard=True)


def _init_vision(config: Config) -> CameraSense | None:
    """Open camera and load vision + face recognition models (blocking). Returns None if unavailable."""
    try:
        describer = Describer(config.VISION_MODEL)
        people_db = PeopleDB()
        identifier = Identifier(people_db)
        return CameraSense(describer, identifier=identifier, source=config.CAMERA_URL)

    except Exception as e:
        logger.warning(f"Vision unavailable — {e}")
        return None


async def weave(config: Config, checkpointer=None):
    """Wire up senses, brain, and actions. Return shared buffers and components."""

    logger.debug("Weaving EVA's core components...")
    loop = asyncio.get_running_loop()

    # Shared buffers
    action_buffer = ActionBuffer()
    sense_buffer = SenseBuffer()
    sense_buffer.attach_loop(loop)

    # Senses — init ears and eyes in parallel (both have blocking I/O)
    camera_sense, audio_sense = await asyncio.gather(
        asyncio.to_thread(_init_vision, config),
        asyncio.to_thread(_init_audio, config),
    )

    audio_sense.start(sense_buffer)
    if camera_sense:
        camera_sense.start(sense_buffer)

    # Brain — LangGraph with conversation memory
    graph = build_graph(config.CHAT_MODEL, action_buffer, checkpointer=checkpointer)

    # Actions
    speaker = Speaker(config.TTS_MODEL, config.LANGUAGE)
    voice_actor = VoiceActor(action_buffer, speaker)

    return sense_buffer, action_buffer, audio_sense, camera_sense, voice_actor, graph


async def breathe(sense_buffer: SenseBuffer, graph) -> None:
    """The conscious loop — EVA's mind."""

    config = {"configurable": {"thread_id": "eva-main"}}

    while True:
        entry = await sense_buffer.get()
        logger.debug(f"EVA: sensed [{entry.type}] — {entry.content[:60]}")

        try:
            sense = ("I hear: " if entry.type == "audio" else "I see: ") + entry.content
            human = f"<CONTEXT>\n{sense}\n</CONTEXT>"

            await graph.ainvoke({"messages": [HumanMessage(content=human)]}, config=config)

        except Exception as e:
            logger.error(f"EVA: brain error — {e}")

        await asyncio.sleep(0.1)


async def wake() -> None:
    """Launch EVA — senses, mind, and voice running concurrently."""
    load_dotenv()
    config: Config = eva_configuration

    # Ensure DB directory exists
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    logger.debug("EVA is waking up...")

    async with AsyncSqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        sense_buffer, action_buffer, audio_sense, camera_sense, voice_actor, graph = await weave(config, checkpointer)

        try:
            await asyncio.gather(
                breathe(sense_buffer, graph),
                voice_actor.start_loop(),
            )
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            audio_sense.stop()
            if camera_sense:
                await camera_sense.stop()
            await voice_actor.stop()
            logger.debug("EVA is falling asleep... Bye!")


if __name__ == "__main__":
    asyncio.run(wake())
