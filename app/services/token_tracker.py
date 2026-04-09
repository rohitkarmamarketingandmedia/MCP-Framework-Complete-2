# app/services/token_tracker.py
"""
Token usage & cost tracking service using LiteLLM for pricing data.

Usage:
    from app.services.token_tracker import track_usage

    # After any Anthropic API call that returns usage info:
    track_usage(
        model='claude-sonnet-4-6',
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        feature='blog_generation',
        client_id='abc123',           # optional
        duration_ms=1500,             # optional
    )
"""
import logging
import time
from functools import wraps
from typing import Optional

logger = logging.getLogger(__name__)

# LiteLLM model name mapping: our config names -> LiteLLM's expected format
# LiteLLM uses 'anthropic/' prefix for Claude models
_MODEL_MAP = {
    'claude-sonnet-4-6': 'anthropic/claude-sonnet-4-6',
    'claude-haiku-4-5-20251001': 'anthropic/claude-haiku-4-5-20251001',
    'claude-opus-4-6': 'anthropic/claude-opus-4-6',
}


def _litellm_model(model: str) -> str:
    """Map our model name to LiteLLM's expected format."""
    return _MODEL_MAP.get(model, f'anthropic/{model}')


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Compute the USD cost of an API call using LiteLLM's pricing database.
    Falls back to manual pricing if LiteLLM is unavailable.
    """
    try:
        from litellm import cost_per_token
        litellm_model = _litellm_model(model)
        prompt_cost, completion_cost = cost_per_token(
            model=litellm_model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
        return float(prompt_cost + completion_cost)
    except Exception as e:
        logger.debug(f"LiteLLM cost_per_token failed ({e}), using fallback pricing")
        return _fallback_cost(model, input_tokens, output_tokens)


def _fallback_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Fallback pricing per 1M tokens (USD) when LiteLLM is unavailable."""
    # Prices as of April 2026 — update if Anthropic changes pricing
    PRICING = {
        'claude-sonnet-4-6':          {'input': 3.00,  'output': 15.00},
        'claude-haiku-4-5-20251001':  {'input': 0.80,  'output': 4.00},
        'claude-opus-4-6':            {'input': 15.00, 'output': 75.00},
    }
    prices = PRICING.get(model, PRICING['claude-sonnet-4-6'])
    return (input_tokens * prices['input'] / 1_000_000) + (output_tokens * prices['output'] / 1_000_000)


def track_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    feature: str,
    client_id: Optional[str] = None,
    duration_ms: Optional[int] = None,
    request_id: Optional[str] = None,
) -> None:
    """
    Log a single AI API call's token usage and cost to the database.
    Silently catches all errors so it never breaks the calling code.
    """
    try:
        from app.database import db
        from app.models.db_models import DBTokenUsage

        total = input_tokens + output_tokens
        cost = compute_cost(model, input_tokens, output_tokens)

        record = DBTokenUsage(
            client_id=client_id,
            feature=feature,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
            cost_usd=cost,
            request_id=request_id,
            duration_ms=duration_ms,
        )
        db.session.add(record)
        db.session.commit()

        logger.debug(
            f"Token usage logged: {feature} | {model} | "
            f"in={input_tokens} out={output_tokens} | ${cost:.6f}"
        )
    except Exception as e:
        logger.error(f"Failed to log token usage: {e}")
        try:
            from app.database import db
            db.session.rollback()
        except Exception:
            pass


def tracked_anthropic_call(feature: str, client_id: Optional[str] = None):
    """
    Decorator for functions that return an Anthropic response object.
    Automatically logs usage after the call completes.

    Usage:
        @tracked_anthropic_call('blog_generation', client_id='abc')
        def generate_blog(...):
            return client.messages.create(...)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            response = func(*args, **kwargs)
            elapsed_ms = int((time.time() - start) * 1000)

            try:
                if hasattr(response, 'usage') and response.usage:
                    track_usage(
                        model=response.model or 'unknown',
                        input_tokens=response.usage.input_tokens,
                        output_tokens=response.usage.output_tokens,
                        feature=feature,
                        client_id=client_id,
                        duration_ms=elapsed_ms,
                        request_id=getattr(response, 'id', None),
                    )
            except Exception as e:
                logger.error(f"tracked_anthropic_call decorator error: {e}")

            return response
        return wrapper
    return decorator
