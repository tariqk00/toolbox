"""
Cost-optimized LLM routing and budget governance gateway.
Implements Issue #149.
"""
import os
import yaml
import logging
import time
import random
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

from toolbox.lib import log_manager, quota_manager
from toolbox.lib.providers.groq import GroqProvider
from toolbox.lib.providers.ollama import OllamaProvider
from toolbox.lib.providers.gemini import GeminiProvider
from toolbox.lib.providers.base import ProviderSkip, RateLimitError

logger = logging.getLogger("toolbox.llm_gateway")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'llm_routing.yaml')
LLM_LOG_PATH = os.path.join(BASE_DIR, 'logs', 'llm_routing.jsonl')

class LLMGateway:
    def __init__(self):
        self.config = self._load_config()
        self._init_secrets()

    def _load_config(self) -> Dict:
        if not os.path.exists(CONFIG_PATH):
            raise FileNotFoundError(f"LLM routing config missing at {CONFIG_PATH}")
        with open(CONFIG_PATH, 'r') as f:
            return yaml.safe_load(f)

    def _init_secrets(self):
        # Load keys from secrets.env
        from dotenv import load_dotenv
        load_dotenv(os.path.join(BASE_DIR, 'config', 'secrets.env'))
        
        # Gemini keys
        self.gemini_free_key = self._load_secret('gemini_ai_studio_secret', 'GEMINI_FREE_API_KEY')
        self.gemini_paid_key = self._load_secret('gemini_secret', 'GEMINI_API_KEY')

    def _load_secret(self, filename: str, env_var: str) -> Optional[str]:
        val = os.getenv(env_var)
        if val: return val
        path = os.path.join(BASE_DIR, 'config', filename)
        if os.path.exists(path):
            with open(path) as f:
                return f.read().strip()
        return None

    def _get_provider_instance(self, provider_cfg: Dict[str, str]):
        name = provider_cfg['name']
        model = provider_cfg['model']
        
        if name == 'ollama':
            return OllamaProvider(model_name=model)
        elif name == 'groq':
            return GroqProvider(model_name=model)
        elif name == 'gemini-free':
            if not self.gemini_free_key:
                raise ValueError("Gemini Free key missing (config/gemini_ai_studio_secret)")
            return GeminiProvider(model_name=model, api_key=self.gemini_free_key)
        elif name == 'gemini-paid':
            if not self.gemini_paid_key:
                raise ValueError("Gemini Paid key missing (config/gemini_secret)")
            return GeminiProvider(model_name=model, api_key=self.gemini_paid_key)
        else:
            raise ValueError(f"Unknown provider: {name}")

    def call(self, task_type: str, prompt: str, content_bytes: bytes = b'', mime_type: str = 'text/plain', **kwargs) -> Dict[str, Any]:
        """
        Unified entry point for LLM calls with routing and budget enforcement.
        """
        # 1. Routing logic
        # Estimate tokens (rough: 4 chars per token)
        prompt_tokens = len(prompt) // 4
        
        # Check for long-context override
        long_context_threshold = self.config.get('thresholds', {}).get('long_context_tokens', 200000)
        if prompt_tokens > long_context_threshold:
            route = 'long-context'
        else:
            route = self.config.get('routes', {}).get(task_type)
            if not route:
                msg = f"Unknown task_type '{task_type}' and no default route defined."
                logger.error(msg)
                raise ValueError(msg)
            
        tier_name = route
        tier = self.config.get('tiers', {}).get(tier_name)
        if not tier:
            msg = f"Route '{route}' maps to undefined tier '{tier_name}'."
            logger.error(msg)
            raise ValueError(msg)

        # 2. Budget Enforcement (Daily)
        daily_usd_limit = self.config.get('budgets', {}).get('daily_usd', 2.0)
        current_usd = quota_manager.get_total_usd_used()
        if current_usd >= daily_usd_limit:
            msg = f"Daily LLM budget exceeded: ${current_usd:.4f} >= ${daily_usd_limit:.4f}"
            logger.error(msg)
            self._log_routing(task_type, tier_name, {}, prompt_tokens, 0, "blocked", msg)
            raise RuntimeError(msg)

        # 3. Context / Token Caps (Enforce Hard Truncation)
        token_cap = self.config.get('token_caps', {}).get(tier_name, 4000)
        if prompt_tokens > token_cap:
            logger.warning(f"Prompt tokens ({prompt_tokens}) exceed cap for tier {tier_name} ({token_cap}). Truncating.")
            prompt = prompt[:token_cap * 4]
            prompt_tokens = token_cap

        per_task_usd_limit = self.config.get('budgets', {}).get('per_task_usd', 0.20)

        # 4. Try providers in tier (Fallback Chain)
        last_exception = None
        attempts_chain = []
        for provider_cfg in tier['providers']:
            try:
                # Pre-call Cost Estimation
                model_name = provider_cfg['model']
                provider_name = provider_cfg['name']
                cost_per_m = self.config.get('costs', {}).get(model_name)
                if cost_per_m is None:
                    cost_per_m = self.config.get('costs', {}).get(provider_name, 0.10)
                
                est_cost = (prompt_tokens * cost_per_m) / 1_000_000
                if est_cost > per_task_usd_limit:
                    msg = f"Estimated task cost ${est_cost:.4f} exceeds limit ${per_task_usd_limit:.4f} for provider {provider_name}/{model_name}"
                    logger.warning(msg)
                    attempts_chain.append({"provider": provider_name, "model": model_name, "result": "blocked", "error": msg})
                    continue

                provider = self._get_provider_instance(provider_cfg)
                if not provider.supports(mime_type):
                    continue
                
                # Retry loop (Exponential Backoff with Jitter)
                for attempt in range(3):
                    start_time = time.time()
                    try:
                        if attempt > 0:
                            delay = (2 ** attempt) + random.uniform(0, 1)
                            logger.info(f"Retrying {provider_name} in {delay:.1f}s (attempt {attempt+1}/3)...")
                            time.sleep(delay)
                            
                        # Execute call
                        # Ensure content_bytes is NOT dropped for text/plain if provided
                        data_to_send = content_bytes if content_bytes else b''
                        result_text, actual_tokens = provider.analyze(data_to_send, mime_type, prompt)
                        latency = time.time() - start_time
                        
                        # Calculate actual cost
                        cost = (actual_tokens * cost_per_m) / 1_000_000
                        
                        # Post-call budget enforcement
                        if cost > per_task_usd_limit:
                            msg = f"Actual task cost ${cost:.4f} exceeded limit ${per_task_usd_limit:.4f}"
                            logger.error(msg)
                            self._log_routing(task_type, tier_name, provider_cfg, actual_tokens, cost, "blocked", msg, attempt+1, latency, prompt_tokens)
                            raise RuntimeError(msg)

                        # Record usage
                        quota_manager.record_llm_usage(actual_tokens, cost)
                        
                        # Log success
                        self._log_routing(task_type, tier_name, provider_cfg, actual_tokens, cost, "success", "", attempt+1, latency, prompt_tokens)
                        
                        return {
                            "text": result_text,
                            "tokens": actual_tokens,
                            "cost": cost,
                            "provider": provider_name,
                            "model": model_name,
                            "tier": tier_name
                        }
                    except RateLimitError as e:
                        latency = time.time() - start_time
                        logger.warning(f"Provider {provider_name} rate limited: {e}")
                        self._log_routing(task_type, tier_name, provider_cfg, 0, 0, "rate_limit", str(e), attempt+1, latency, prompt_tokens)
                        if attempt < 2: # Continue to next retry in inner loop
                            continue
                        else:
                            attempts_chain.append({"provider": provider_name, "model": model_name, "result": "rate_limit_exhausted", "error": str(e)})
                            break # Try next provider in outer loop
                    except ProviderSkip as e:
                        latency = time.time() - start_time
                        logger.warning(f"Provider {provider_name} skipped: {e}")
                        attempts_chain.append({"provider": provider_name, "model": model_name, "result": "skipped", "error": str(e)})
                        self._log_routing(task_type, tier_name, provider_cfg, 0, 0, "skipped", str(e), attempt+1, latency, prompt_tokens)
                        break # Try next provider in tier
                    except Exception as e:
                        latency = time.time() - start_time
                        last_exception = e
                        err_msg = str(e).upper()
                        attempts_chain.append({"provider": provider_name, "model": model_name, "result": "error", "error": str(e)})
                        self._log_routing(task_type, tier_name, provider_cfg, 0, 0, "error", str(e), attempt+1, latency, prompt_tokens)
                        
                        # Retry only on very specific transient errors NOT already caught by RateLimitError
                        if any(x in err_msg for x in ["TIMEOUT", "CONNECTION_ERROR"]):
                            continue
                        break # Other errors → try next provider
                        
            except Exception as e:
                logger.warning(f"Failed to use provider {provider_cfg['name']}: {e}")
                last_exception = e
                continue
                
        # 5. Final Failure
        err_msg = str(last_exception) or "No valid providers available."
        self._log_routing(task_type, tier_name, {}, prompt_tokens, 0, "failure", f"Attempts: {attempts_chain}. Error: {err_msg}")
        raise RuntimeError(f"All providers in tier {tier_name} failed. Last error: {err_msg}")

    def _log_routing(self, task_type: str, tier: str, provider: Dict, tokens: int, cost: float, result: str, error: str = "", attempt: int = 1, latency: float = 0, est_tokens: int = 0):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_type": task_type,
            "tier": tier,
            "provider": provider.get('name', 'N/A'),
            "model": provider.get('model', 'N/A'),
            "est_tokens": est_tokens,
            "actual_tokens": tokens,
            "cost_usd": round(cost, 6),
            "result": result,
            "attempt": attempt,
            "latency_sec": round(latency, 2),
            "error": error
        }
        os.makedirs(os.path.dirname(LLM_LOG_PATH), exist_ok=True)
        try:
            with open(LLM_LOG_PATH, 'a') as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write LLM routing log: {e}")

# Global instance for easy access
_gateway = None

def call_llm(task_type: str, prompt: str, **kwargs) -> Dict[str, Any]:
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway.call(task_type, prompt, **kwargs)
