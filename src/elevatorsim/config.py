# src/elevatorsim/config.py
"""Central configuration provider, seedable RNG, and Gemini model factory."""

import os
import random
from dotenv import load_dotenv
from strands.models.gemini import GeminiModel
from strands.models.ollama import OllamaModel

# Load environment variables from .env
load_dotenv()

# Default Configurations
DEFAULT_SEED = int(os.getenv("DEFAULT_SEED", "42"))
DEFAULT_MODEL_ID = os.getenv("DEFAULT_MODEL_ID", "gemini-3.5-flash")
DEFAULT_THINKING_LEVEL = os.getenv("DEFAULT_THINKING_LEVEL", "minimal")

# Provider Configurations
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL_ID = os.getenv("OLLAMA_MODEL_ID", "gemma4:e4b")

# Central Seedable RNG for Sim Reproducibility
RNG = random.Random(DEFAULT_SEED)

def seed_rng(seed: int) -> None:
    """
    Re-seed the central random number generator to guarantee reproducibility.

    Args:
        seed: Seed integer
    """
    global RNG
    RNG.seed(seed)
    # Also seed the standard random module just in case dependencies use it
    random.seed(seed)


def get_llm_provider() -> str:
    """Retrieve the current LLM provider name (gemma, gemini, or mock)."""
    return os.getenv("LLM_PROVIDER", "gemini").lower()


def get_gemini_api_key() -> str | None:
    """Retrieve the Gemini API key from environment."""
    key = os.getenv("GEMINI_API_KEY")
    if not key or key.strip() in ("", "your_google_ai_studio_api_key_here"):
        return None
    return key


def get_gemini_model() -> GeminiModel:
    """
    Factory to construct the GeminiModel wrapper.
    Removes temperature/top_p (deprecated) and configures thinking_level.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not configured in environment or .env file. "
            "Please check .env.example for instructions."
          )

    # Note: no temperature/top_p/top_k are passed here (deprecated for 3.5-flash)
    return GeminiModel(
        client_args={
            "api_key": api_key,
        },
        model_id=DEFAULT_MODEL_ID,
        params={
            "thinking_config": {
                "thinking_level": DEFAULT_THINKING_LEVEL,
            }
        }
    )


def get_model(temperature: float = 0.0) -> GeminiModel | OllamaModel | None:
    """
    Factory to construct the appropriate model wrapper (Gemini or Ollama/Gemma).
    """
    provider = get_llm_provider()
    if provider == "gemma":
        return OllamaModel(
            host=OLLAMA_HOST,
            model_id=OLLAMA_MODEL_ID,
            temperature=temperature,
            options={"seed": DEFAULT_SEED},
            additional_args={"think": False}  # Gemma 4 reasons by default and intermittently swallows structured output
        )
    elif provider == "gemini":
        return get_gemini_model()
    else:
        # For mock or other providers
        return None

