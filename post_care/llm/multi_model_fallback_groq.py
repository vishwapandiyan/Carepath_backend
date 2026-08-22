"""
Multi-Model LLM Fallback System with Groq Models + External Fallbacks

Provides a robust fallback mechanism for LLM calls. If one provider/model fails,
automatically tries the next one in the fallback chain.

Groq Models (Primary):
1. openai/gpt-oss-120b - Main model (general purpose)
2. openai/gpt-oss-safeguard-20b - Safety & reasoning
3. meta-llama/llama-prompt-guard-2-22m - Prompt safety
4. mixtral-8x7b-32768 - Fast backup

External Providers (Secondary Fallbacks):
5. OpenAI (gpt-4, gpt-3.5-turbo) - Powerful, reliable
6. Anthropic Claude (claude-3-sonnet) - Good at reasoning
7. Ollama (local) - No API key needed, runs locally

Configuration:
- Set environment variables: GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY
- Ollama doesn't need API key (local execution)
- Adjust fallback order in MODEL_CHAIN

Architecture:
    LLM Call Attempt
        ↓
    Try Groq Model 1 (openai/gpt-oss-120b)
        ↓ (fails)
    Try Groq Model 2 (openai/gpt-oss-safeguard-20b)
        ↓ (fails)
    Try Groq Model 3 (meta-llama/llama-prompt-guard-2-22m)
        ↓ (fails)
    Try Groq Model 4 (mixtral-8x7b-32768)
        ↓ (fails)
    Try OpenAI
        ↓ (fails)
    Try Anthropic Claude
        ↓ (fails)
    Try Ollama (local)
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
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)

# ============================================================================
# LLM PROVIDER & MODEL ENUM
# ============================================================================

class LLMProvider(Enum):
    """Supported LLM providers"""
    GROQ_OSS_120B = "groq_oss_120b"
    GROQ_SAFEGUARD_20B = "groq_safeguard_20b"
    GROQ_LLAMA_GUARD = "groq_llama_guard"
    GROQ_MIXTRAL = "groq_mixtral"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


# ============================================================================
# MODEL CONFIGURATION
# ============================================================================

MODEL_CHAIN = [
    # Groq Models (Primary - all use Groq API key)
    LLMProvider.GROQ_OSS_120B,              # Main (general purpose, fastest)
    LLMProvider.GROQ_SAFEGUARD_20B,         # Safety & reasoning
    LLMProvider.GROQ_LLAMA_GUARD,           # Prompt safety
    LLMProvider.GROQ_MIXTRAL,               # Fast backup
    
    # External Providers (Secondary - fallback if all Groq fail)
    LLMProvider.OPENAI,                     # Powerful, reliable
    LLMProvider.ANTHROPIC,                  # Good reasoning
    LLMProvider.OLLAMA,                     # Local, always available
]

MODEL_NAMES = {
    LLMProvider.GROQ_OSS_120B: "openai/gpt-oss-120b",
    LLMProvider.GROQ_SAFEGUARD_20B: "openai/gpt-oss-safeguard-20b",
    LLMProvider.GROQ_LLAMA_GUARD: "meta-llama/llama-prompt-guard-2-22m",
    LLMProvider.GROQ_MIXTRAL: "mixtral-8x7b-32768",
    LLMProvider.OPENAI: "gpt-4",
    LLMProvider.ANTHROPIC: "claude-3-sonnet-20240229",
    LLMProvider.OLLAMA: "llama2",
}

# Model-specific configurations
MODEL_CONFIG = {
    LLMProvider.GROQ_OSS_120B: {
        "temperature": 0.3,
        "max_tokens": 1024,
        "top_p": 1,
        "stream": False,
    },
    LLMProvider.GROQ_SAFEGUARD_20B: {
        "temperature": 1,
        "max_tokens": 2048,
        "top_p": 1,
        "reasoning_effort": "medium",
        "stream": False,
    },
    LLMProvider.GROQ_LLAMA_GUARD: {
        "temperature": 1,
        "max_tokens": 1,
        "top_p": 1,
        "stream": False,
    },
    LLMProvider.GROQ_MIXTRAL: {
        "temperature": 0.5,
        "max_tokens": 1024,
        "top_p": 1,
        "stream": False,
    },
    LLMProvider.OPENAI: {
        "temperature": 0.3,
        "max_tokens": 1024,
        "top_p": 1,
    },
    LLMProvider.ANTHROPIC: {
        "temperature": 0.3,
        "max_tokens": 1024,
    },
    LLMProvider.OLLAMA: {
        "temperature": 0.3,
    },
}

# ============================================================================
# PROVIDER-SPECIFIC IMPLEMENTATIONS
# ============================================================================

def _call_groq_oss_120b(prompt: str, system: str) -> str:
    """Call Groq openai/gpt-oss-120b model."""
    try:
        from groq import Groq
        
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in environment")
        
        client = Groq(api_key=api_key)
        config = MODEL_CONFIG[LLMProvider.GROQ_OSS_120B]
        
        message = client.chat.completions.create(
            model=MODEL_NAMES[LLMProvider.GROQ_OSS_120B],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            temperature=config["temperature"],
            max_tokens=config["max_tokens"],
            top_p=config["top_p"],
            stream=config["stream"],
        )
        
        return message.choices[0].message.content
    
    except Exception as e:
        logger.error(f"Groq OSS-120B call failed: {str(e)}")
        raise


def _call_groq_safeguard_20b(prompt: str, system: str) -> str:
    """Call Groq openai/gpt-oss-safeguard-20b model."""
    try:
        from groq import Groq
        
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in environment")
        
        client = Groq(api_key=api_key)
        config = MODEL_CONFIG[LLMProvider.GROQ_SAFEGUARD_20B]
        
        message = client.chat.completions.create(
            model=MODEL_NAMES[LLMProvider.GROQ_SAFEGUARD_20B],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            temperature=config["temperature"],
            max_tokens=config["max_tokens"],
            top_p=config["top_p"],
            reasoning_effort=config.get("reasoning_effort", "medium"),
            stream=config["stream"],
        )
        
        return message.choices[0].message.content
    
    except Exception as e:
        logger.error(f"Groq Safeguard-20B call failed: {str(e)}")
        raise


def _call_groq_llama_guard(prompt: str, system: str) -> str:
    """Call Groq meta-llama/llama-prompt-guard-2-22m model."""
    try:
        from groq import Groq
        
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in environment")
        
        client = Groq(api_key=api_key)
        config = MODEL_CONFIG[LLMProvider.GROQ_LLAMA_GUARD]
        
        message = client.chat.completions.create(
            model=MODEL_NAMES[LLMProvider.GROQ_LLAMA_GUARD],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            temperature=config["temperature"],
            max_tokens=config["max_tokens"],
            top_p=config["top_p"],
            stream=config["stream"],
        )
        
        return message.choices[0].message.content
    
    except Exception as e:
        logger.error(f"Groq Llama Guard call failed: {str(e)}")
        raise


def _call_groq_mixtral(prompt: str, system: str) -> str:
    """Call Groq mixtral-8x7b-32768 model."""
    try:
        from groq import Groq
        
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in environment")
        
        client = Groq(api_key=api_key)
        config = MODEL_CONFIG[LLMProvider.GROQ_MIXTRAL]
        
        message = client.chat.completions.create(
            model=MODEL_NAMES[LLMProvider.GROQ_MIXTRAL],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            temperature=config["temperature"],
            max_tokens=config["max_tokens"],
            top_p=config["top_p"],
            stream=config["stream"],
        )
        
        return message.choices[0].message.content
    
    except Exception as e:
        logger.error(f"Groq Mixtral call failed: {str(e)}")
        raise


def _call_openai(prompt: str, system: str) -> str:
    """Call OpenAI LLM (external fallback)."""
    try:
        import openai
        
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set in environment")
        
        client = openai.OpenAI(api_key=api_key)
        config = MODEL_CONFIG[LLMProvider.OPENAI]
        
        message = client.chat.completions.create(
            model=MODEL_NAMES[LLMProvider.OPENAI],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            temperature=config["temperature"],
            max_tokens=config["max_tokens"],
            top_p=config["top_p"],
        )
        
        return message.choices[0].message.content
    
    except Exception as e:
        logger.error(f"OpenAI call failed: {str(e)}")
        raise


def _call_anthropic(prompt: str, system: str) -> str:
    """Call Anthropic Claude LLM (external fallback)."""
    try:
        import anthropic
        
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment")
        
        client = anthropic.Anthropic(api_key=api_key)
        config = MODEL_CONFIG[LLMProvider.ANTHROPIC]
        
        message = client.messages.create(
            model=MODEL_NAMES[LLMProvider.ANTHROPIC],
            max_tokens=config["max_tokens"],
            temperature=config["temperature"],
            system=system,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        return message.content[0].text
    
    except Exception as e:
        logger.error(f"Anthropic call failed: {str(e)}")
        raise


def _call_ollama(prompt: str, system: str) -> str:
    """Call Ollama local LLM (external fallback)."""
    try:
        import requests
        
        # Ollama runs locally on http://localhost:11434
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": MODEL_NAMES[LLMProvider.OLLAMA],
                "prompt": f"{system}\n\n{prompt}",
                "stream": False
            },
            timeout=60
        )
        
        if response.status_code != 200:
            raise ValueError(f"Ollama API returned {response.status_code}")
        
        return response.json().get("response", "")
    
    except Exception as e:
        logger.error(f"Ollama call failed: {str(e)}")
        raise


# ============================================================================
# PROVIDER DISPATCHER
# ============================================================================

def _call_provider(provider: LLMProvider, prompt: str, system: str) -> str:
    """Dispatch LLM call to the appropriate provider."""
    logger.info(f"Attempting LLM call with {provider.value}")
    
    if provider == LLMProvider.GROQ_OSS_120B:
        return _call_groq_oss_120b(prompt, system)
    elif provider == LLMProvider.GROQ_SAFEGUARD_20B:
        return _call_groq_safeguard_20b(prompt, system)
    elif provider == LLMProvider.GROQ_LLAMA_GUARD:
        return _call_groq_llama_guard(prompt, system)
    elif provider == LLMProvider.GROQ_MIXTRAL:
        return _call_groq_mixtral(prompt, system)
    elif provider == LLMProvider.OPENAI:
        return _call_openai(prompt, system)
    elif provider == LLMProvider.ANTHROPIC:
        return _call_anthropic(prompt, system)
    elif provider == LLMProvider.OLLAMA:
        return _call_ollama(prompt, system)
    else:
        raise ValueError(f"Unknown provider: {provider}")


# ============================================================================
# MAIN FALLBACK FUNCTION
# ============================================================================

def call_llm_with_fallback(
    prompt: str,
    system: str = "You are a healthcare assistant. Analyze the patient response and provide structured output.",
    fallback_chain: Optional[List[LLMProvider]] = None
) -> str:
    """
    Call LLM with automatic fallback to next model/provider on failure.
    
    Tries models in this order:
    1. Groq openai/gpt-oss-120b (primary)
    2. Groq openai/gpt-oss-safeguard-20b (fallback 1)
    3. Groq meta-llama/llama-prompt-guard-2-22m (fallback 2)
    4. Groq mixtral-8x7b-32768 (fallback 3)
    5. OpenAI gpt-4 (fallback 4)
    6. Anthropic Claude (fallback 5)
    7. Ollama local (fallback 6)
    
    Args:
        prompt: The user prompt/patient response
        system: System message for the LLM
        fallback_chain: List of providers to try (defaults to MODEL_CHAIN)
    
    Returns:
        Response from first successful LLM provider
    
    Raises:
        RuntimeError: If all providers fail
    
    Example:
        response = call_llm_with_fallback(
            prompt="My wound is more swollen today.",
            system="You are a healthcare assistant..."
        )
    """
    if fallback_chain is None:
        fallback_chain = MODEL_CHAIN
    
    last_error = None
    
    logger.info(f"Starting LLM call with fallback chain ({len(fallback_chain)} attempts available)")
    
    for attempt, provider in enumerate(fallback_chain, 1):
        try:
            logger.info(f"[{attempt}/{len(fallback_chain)}] Trying: {provider.value} ({MODEL_NAMES[provider]})")
            response = _call_provider(provider, prompt, system)
            logger.info(f"✅ LLM call succeeded with {provider.value}")
            return response
        
        except Exception as e:
            logger.warning(f"❌ [{attempt}/{len(fallback_chain)}] {provider.value} failed: {str(e)}")
            last_error = e
            continue
    
    # All providers failed
    error_msg = f"All {len(fallback_chain)} LLM providers failed. Last error: {str(last_error)}"
    logger.error(error_msg)
    raise RuntimeError(error_msg)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_available_providers() -> list:
    """
    Get list of available LLM providers (have API keys configured).
    
    Returns:
        List of available LLMProvider enums
    """
    available = []
    
    # Groq models all use same API key
    if os.environ.get("GROQ_API_KEY"):
        available.extend([
            LLMProvider.GROQ_OSS_120B,
            LLMProvider.GROQ_SAFEGUARD_20B,
            LLMProvider.GROQ_LLAMA_GUARD,
            LLMProvider.GROQ_MIXTRAL,
        ])
    
    if os.environ.get("OPENAI_API_KEY"):
        available.append(LLMProvider.OPENAI)
    
    if os.environ.get("ANTHROPIC_API_KEY"):
        available.append(LLMProvider.ANTHROPIC)
    
    # Ollama doesn't need API key, check if it's running
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            available.append(LLMProvider.OLLAMA)
    except:
        pass
    
    return available


def log_provider_status() -> None:
    """Log status of all LLM providers."""
    logger.info("="*100)
    logger.info("LLM PROVIDER STATUS - MULTI-MODEL FALLBACK SYSTEM")
    logger.info("="*100)
    
    available = get_available_providers()
    
    for provider in MODEL_CHAIN:
        status = "✅ Available" if provider in available else "❌ Not Available"
        logger.info(f"  {provider.value:25} {status:20} Model: {MODEL_NAMES[provider]}")
    
    logger.info("="*100)
    logger.info(f"Fallback Chain Order: {' → '.join([p.value for p in MODEL_CHAIN])}")
    logger.info(f"Total Providers: {len(available)}/{len(MODEL_CHAIN)} available")
    logger.info("="*100)


# ============================================================================
# INITIALIZATION
# ============================================================================

# Log provider status on import
log_provider_status()

