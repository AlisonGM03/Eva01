from pathlib import Path
from typing import Dict, Any

import yaml

CONFIG_FILE = Path(__file__).with_name("eva.yaml")
REQUIRED_KEYS = {
    "DEVICE",
    "LANGUAGE",
    "BASE_URL",
    "CHAT_MODEL",
    "VISION_MODEL",
    "STT_MODEL",
    "TTS_MODEL",
    "SUMMARIZE_MODEL",
}

def _load_yaml_config(config_file: Path = CONFIG_FILE) -> Dict[str, Any]:
    if not config_file.is_file():
        raise FileNotFoundError(
            f"EVA config file not found at '{config_file}'. "
            "Create backend/app/config/eva.yaml before starting EVA."
        )

    with config_file.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    if not isinstance(raw, dict):
        raise ValueError(f"EVA config at '{config_file}' must be a YAML mapping/object.")

    system = raw.get("system", {})
    models = raw.get("models", {})

    config = {
        "DEVICE": system.get("device"),
        "LANGUAGE": system.get("language"),
        "BASE_URL": system.get("base_url"),
        "CHAT_MODEL": models.get("chat"),
        "VISION_MODEL": models.get("vision"),
        "STT_MODEL": models.get("stt"),
        "TTS_MODEL": models.get("tts"),
        "SUMMARIZE_MODEL": models.get("summarize"),
    }
    
    missing = [k for k, v in config.items() if v is None]
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"EVA config is missing required keys: {missing_text}")

    return config


eva_configuration = _load_yaml_config()
