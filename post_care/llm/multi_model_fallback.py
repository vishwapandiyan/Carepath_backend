"""
Multi-Model Groq LLM Fallback System

Provides a robust fallback mechanism for LLM calls using only Groq models.
If one Groq model fails, automatically tries the next Groq model in the chain.

Supported Groq Models (Fallback Chain):
1. openai/gpt-oss-120b (Primary) - General purpose, general reasoning
2. meta-llama/llama-prompt-guard-2-22m (Fallback 1) - Safety/guard model
3. openai/gpt-oss-safeguard-20b (Fallback 2) - Safety model with reasoning
4. mixtral-8x7b-32768 (Fallback 3) - Fast, reliable backup

All models use the same Groq API key.

Configuration:
- Set GROQ_API_KEY environment variable (single API key for all models)
- Adjust fallback order in MODEL_CHAIN
- Each model tries with appropriate parameters for that model

Architecture:
    LLM Call Attempt
        ↓
    Try openai/gpt-oss-120b
        ↓ (fails)
    Try meta-llama/llama-prompt-guard-2-22m
        ↓ (fails)
    Try openai/gpt-oss-safeguard-20b (with streaming)
        ↓ (fails)
    Try mixtral-8x7b-32768
        ↓
    Return Response or Raise Error

Production Usage:
    response = call_llm_with_fallback(
        prompt="Analyze patient response: ...",
        system="You are a healthcare assistant..."
    )
"""

import logging
import json
import os
from typing import Optional, Dict, Any
from enum import Enum
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

logger = logging.getLogger(__name__)

# ============================================================================
# GROQ MODEL ENUM
# ============================================================================

class GroqModel(Enum):
    """Supported Groq LLM models"""
    GPT_OSS_120B = "openai/gpt-oss-120b"
    LLAMA_GUARD_2_22M = "meta-llama/llama-prompt-guard-2-22m"
    GPT_OSS_SAFEGUARD_20B = "openai/gpt-oss-safeguard-20b"
    MIXTRAL_8X7B = "mixtral-8x7b-32768"


# ============================================================================
# MODEL CONFIGURATION
# ============================================================================

MODEL_CHAIN = [
    GroqModel.GPT_OSS_120B,              # Primary (general purpose)
    GroqModel.LLAMA_GUARD_2_22M,         # Fallback 1 (safety)
    GroqModel.GPT_OSS_SAFEGUARD_20B,     # Fallback 2 (reasoning)
    GroqModel.MIXTRAL_8X7B,              # Fallback 3 (fast backup)
]

MODEL_NAMES = {
    GroqModel.GPT_OSS_120B: "openai/gpt-oss-120b",
    GroqModel.LLAMA_GUARD_2_22M: "meta-llama/llama-prompt-guard-2-22m",
    GroqModel.GPT_OSS_SAFEGUARD_20B: "openai/gpt-oss-safeguard-20b",
    GroqModel.MIXTRAL_8X7B: "mixtral-8x7b-32768",
}

# Model-specific configurations
MODEL_CONFIG = {
    GroqModel.GPT_OSS_120B: {
        "temperature": 0.7,
        "max_tokens": 1000,
        "streaming": False,
    },
    GroqModel.LLAMA_GUARD_2_22M: {
        "temperature": 1.0,
        "max_tokens": 1,
        "streaming": False,
    },
    GroqModel.GPT_OSS_SAFEGUARD_20B: {
        "temperature": 1.0,
        "max_tokens": 2048,
        "streaming": True,
        "reasoning_effort": "medium",
    },
    GroqModel.MIXTRAL_8X7B: {
        "temperature": 0.7,
        "max_tokens": 1000,
        "streaming": False,
    },
}

# ============================================================================
# GROQ API IMPLEMENTATIONS
# ============================================================================

def _call_groq_model(model: GroqModel, prompt: str, system: str) -> str:
    """
    Call a specific Groq model.
    
    Args:
        model: GroqModel enum value
        prompt: User prompt
        system: System message
    
    Returns:
        Response text from the model
    
    Raises:
        Exception: If Groq API call fails
    """
    try:
        from groq import Groq
        
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in environment")
        
        client = Groq(api_key=api_key)
        config = MODEL_CONFIG[model]
        
        logger.debug(f"Calling Groq model: {MODEL_NAMES[model]}")
        
        # Handle streaming models differently
        if config.get("streaming", False):
            return _call_groq_streaming(client, model, prompt, system, config)
        else:
            return _call_groq_non_streaming(client, model, prompt, system, config)
    
    except Exception as e:
        logger.error(f"Groq model {MODEL_NAMES[model]} call failed: {str(e)}")
        raise


def _call_groq_non_streaming(client, model: GroqModel, prompt: str, system: str, config: Dict) -> str:
    """Call Groq model with non-streaming response."""
    message = client.chat.completions.create(
        model=MODEL_NAMES[model],
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        temperature=config.get("temperature", 0.7),
        max_tokens=config.get("max_tokens", 1000),
        top_p=1,
        stream=False,
    )
    
    return message.choices[0].message.content


def _call_groq_streaming(client, model: GroqModel, prompt: str, system: str, config: Dict) -> str:
    """Call Groq model with streaming response."""
    completion = client.chat.completions.create(
        model=MODEL_NAMES[model],
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        temperature=config.get("temperature", 0.7),
        max_tokens=config.get("max_tokens", 2048),
        top_p=1,
        reasoning_effort=config.get("reasoning_effort", "medium"),
        stream=True,
    )
    
    # Collect all streamed chunks
    response_text = ""
    for chunk in completion:
        if chunk.choices[0].delta.content:
            response_text += chunk.choices[0].delta.content
    
    return response_text


# ============================================================================
# MODEL DISPATCHER
# ============================================================================

def _call_model(model: GroqModel, prompt: str, system: str) -> str:
    """Dispatch LLM call to the appropriate Groq model."""
    logger.info(f"Attempting LLM call with {MODEL_NAMES[model]}")
    return _call_groq_model(model, prompt, system)


# ============================================================================
# MAIN FALLBACK FUNCTION
# ============================================================================

def call_llm_with_fallback(
    prompt: str,
    system: str = "You are a healthcare assistant. Analyze the patient response and provide structured output.",
    fallback_chain: Optional[list] = None
) -> str:
    """
    Call Groq LLM with automatic fallback to next model on failure.
    
    Uses multiple Groq models in fallback chain:
    1. openai/gpt-oss-120b (primary, general purpose)
    2. meta-llama/llama-prompt-guard-2-22m (fallback 1, safety)
    3. openai/gpt-oss-safeguard-20b (fallback 2, reasoning)
    4. mixtral-8x7b-32768 (fallback 3, fast backup)
    
    Args:
        prompt: The user prompt/patient response
        system: System message for the LLM
        fallback_chain: List of models to try (defaults to MODEL_CHAIN)
    
    Returns:
        Response from first successful Groq model
    
    Raises:
        RuntimeError: If all Groq models fail
    
    Example:
        response = call_llm_with_fallback(
            prompt="My wound is more swollen today.",
            system="You are a healthcare assistant..."
        )
    """
    if fallback_chain is None:
        fallback_chain = MODEL_CHAIN
    
    last_error = None
    
    for model in fallback_chain:
        try:
            logger.info(f"Trying Groq model: {MODEL_NAMES[model]}")
            response = _call_model(model, prompt, system)
            logger.info(f"✅ LLM call succeeded with {MODEL_NAMES[model]}")
            return response
        
        except Exception as e:
            logger.warning(f"❌ {MODEL_NAMES[model]} failed: {str(e)}")
            last_error = e
            continue
    
    # All models failed
    error_msg = f"All Groq models failed. Last error: {str(last_error)}"
    logger.error(error_msg)
    raise RuntimeError(error_msg)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_available_models() -> list:
    """
    Get list of available Groq models (API key configured).
    
    Returns:
        List of available GroqModel enums
    """
    available = []
    
    if os.environ.get("GROQ_API_KEY"):
        # All Groq models are available if API key is set
        available = list(MODEL_CHAIN)
    
    return available


def log_model_status() -> None:
    """Log status of all Groq models."""
    logger.info("="*80)
    logger.info("GROQ LLM MODEL STATUS")
    logger.info("="*80)
    
    api_key = os.environ.get("GROQ_API_KEY")
    
    if api_key:
        logger.info("✅ GROQ_API_KEY is configured")
        logger.info("")
        for model in MODEL_CHAIN:
            config = MODEL_CONFIG[model]
            logger.info(f"{MODEL_NAMES[model]}")
            logger.info(f"  ├─ Temperature: {config.get('temperature')}")
            logger.info(f"  ├─ Max Tokens: {config.get('max_tokens')}")
            logger.info(f"  └─ Streaming: {config.get('streaming', False)}")
    else:
        logger.warning("❌ GROQ_API_KEY is NOT configured")
    
    logger.info("="*80)
    logger.info(f"Fallback Chain:")
    for i, model in enumerate(MODEL_CHAIN, 1):
        logger.info(f"  {i}. {MODEL_NAMES[model]}")
    logger.info("="*80)


# ============================================================================
# INITIALIZATION
# ============================================================================

# Log model status on import
log_model_status()

