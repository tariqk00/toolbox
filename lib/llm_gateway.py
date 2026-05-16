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
import re
import inspect
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from toolbox.lib import log_manager, quota_manager
from toolbox.lib.providers.groq import GroqProvider
from toolbox.lib.providers.ollama import OllamaProvider
from toolbox.lib.providers.gemini import GeminiProvider
from toolbox.lib.providers.deepseek import DeepSeekProvider
from toolbox.lib.providers.base import ProviderSkip, RateLimitError, QuotaExhaustedError

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
        self.deepseek_key = os.getenv('DEEPSEEK_API_KEY')

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
        elif name == 'deepseek':
            if not self.deepseek_key:
                raise ValueError("DeepSeek key missing (DEEPSEEK_API_KEY in config/secrets.env)")
            return DeepSeekProvider(model_name=model, api_key=self.deepseek_key)
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

    def _resolve_source(self, source: Optional[str]) -> str:
        if source:
            return source

        current_file = os.path.abspath(__file__)
        frame = inspect.currentframe()
        try:
            frame = frame.f_back.f_back.f_back if frame and frame.f_back and frame.f_back.f_back and frame.f_back.f_back.f_back else None
            while frame:
                filename = os.path.abspath(frame.f_code.co_filename)
                if filename != current_file:
                    if filename.startswith(BASE_DIR):
                        rel = os.path.splitext(os.path.relpath(filename, BASE_DIR))[0]
                        return rel.replace(os.sep, '/')
                    return Path(filename).stem
                frame = frame.f_back
        finally:
            del frame
        return "unknown"

    def call(self, task_type: str, prompt: str, content_bytes: bytes = b'', mime_type: str = 'text/plain', require_json: bool = False, source: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Unified entry point for LLM calls with routing and budget enforcement.
        If require_json is True, malformed JSON will trigger fallback to next provider.
        """
        # 1. Routing logic
        source = self._resolve_source(source)
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
            self._log_routing(task_type, tier_name, {}, prompt_tokens, 0, "blocked", msg, source=source)
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
        degraded_providers = quota_manager.get_degraded_providers()

        for provider_cfg in tier['providers']:
            try:
                # Pre-call Cost Estimation
                model_name = provider_cfg['model']
                provider_name = provider_cfg['name']

                # Circuit Breaker: Skip degraded providers
                if provider_name in degraded_providers:
                    logger.info(f"Skipping degraded provider: {provider_name}")
                    attempts_chain.append({"provider": provider_name, "model": model_name, "result": "degraded", "error": "Provider marked as degraded for today"})
                    continue

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
                    attempts_chain.append({
                        "provider": provider_name,
                        "model": model_name,
                        "result": "unsupported_mime",
                        "error": f"{mime_type} is not supported",
                    })
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
                        
                        # --- JSON Validation (if requested) ---
                        parsed_json = None
                        if require_json:
                            try:
                                parsed_json = _parse_json(result_text)
                            except Exception as e:
                                logger.warning(f"Provider {provider_name} returned invalid JSON: {e}")
                                attempts_chain.append({"provider": provider_name, "model": model_name, "result": "json_error", "error": str(e)})
                                self._log_routing(task_type, tier_name, provider_cfg, actual_tokens, 0, "json_error", str(e), attempt+1, latency, prompt_tokens, source=source)
                                last_exception = e
                                break # Fail this provider, try next one in tier (outer loop)

                        # Calculate actual cost
                        cost = (actual_tokens * cost_per_m) / 1_000_000
                        
                        # Post-call budget enforcement
                        if cost > per_task_usd_limit:
                            msg = f"Actual task cost ${cost:.4f} exceeded limit ${per_task_usd_limit:.4f}"
                            logger.error(msg)
                            self._log_routing(task_type, tier_name, provider_cfg, actual_tokens, cost, "blocked", msg, attempt+1, latency, prompt_tokens, source=source)
                            raise RuntimeError(msg)

                        # Record usage
                        quota_manager.record_llm_usage(
                            actual_tokens,
                            cost,
                            metadata={
                                "source": source,
                                "task_type": task_type,
                                "provider": provider_name,
                                "model": model_name,
                            },
                        )
                        
                        # Log success
                        self._log_routing(task_type, tier_name, provider_cfg, actual_tokens, cost, "success", "", attempt+1, latency, prompt_tokens, source=source)
                        
                        return {
                            "text": result_text,
                            "json": parsed_json,
                            "tokens": actual_tokens,
                            "cost": cost,
                            "provider": provider_name,
                            "model": model_name,
                            "tier": tier_name
                        }
                    except RateLimitError as e:
                        latency = time.time() - start_time
                        last_exception = e
                        logger.warning(f"Provider {provider_name} rate limited: {e}")
                        self._log_routing(task_type, tier_name, provider_cfg, 0, 0, "rate_limit", str(e), attempt+1, latency, prompt_tokens, source=source)
                        if attempt < 2: # Continue to next retry in inner loop
                            continue
                        else:
                            attempts_chain.append({"provider": provider_name, "model": model_name, "result": "rate_limit_exhausted", "error": str(e)})
                            break # Try next provider in outer loop
                    except QuotaExhaustedError as e:
                        latency = time.time() - start_time
                        logger.error(f"Quota exhausted for {provider_name}: {e}. Tripping circuit breaker.")
                        quota_manager.mark_provider_degraded(provider_name)
                        attempts_chain.append({"provider": provider_name, "model": model_name, "result": "quota_exhausted", "error": str(e)})
                        self._log_routing(task_type, tier_name, provider_cfg, 0, 0, "quota_exhausted", str(e), attempt+1, latency, prompt_tokens, source=source)
                        break # Try next provider in tier (outer loop)
                    except ProviderSkip as e:
                        latency = time.time() - start_time
                        logger.warning(f"Provider {provider_name} skipped: {e}")
                        attempts_chain.append({"provider": provider_name, "model": model_name, "result": "skipped", "error": str(e)})
                        self._log_routing(task_type, tier_name, provider_cfg, 0, 0, "skipped", str(e), attempt+1, latency, prompt_tokens, source=source)
                        break # Try next provider in tier
                    except Exception as e:
                        latency = time.time() - start_time
                        last_exception = e
                        err_msg = str(e).upper()
                        attempts_chain.append({"provider": provider_name, "model": model_name, "result": "error", "error": str(e)})
                        self._log_routing(task_type, tier_name, provider_cfg, 0, 0, "error", str(e), attempt+1, latency, prompt_tokens, source=source)
                        
                        # Retry only on very specific transient errors NOT already caught by RateLimitError
                        if any(x in err_msg for x in ["TIMEOUT", "CONNECTION_ERROR"]):
                            continue
                        break # Other errors → try next provider
                        
            except Exception as e:
                logger.warning(f"Failed to use provider {provider_cfg['name']}: {e}")
                last_exception = e
                continue
                
        # 5. Final Failure
        if last_exception:
            err_msg = str(last_exception)
        elif attempts_chain:
            err_msg = f"No provider completed successfully. Attempts: {attempts_chain}"
        else:
            err_msg = "No valid providers available."
        self._log_routing(task_type, tier_name, {}, prompt_tokens, 0, "failure", f"Attempts: {attempts_chain}. Error: {err_msg}", source=source)
        raise RuntimeError(f"All providers in tier {tier_name} failed. Last error: {err_msg}")

    def _log_routing(self, task_type: str, tier: str, provider: Dict, tokens: int, cost: float, result: str, error: str = "", attempt: int = 1, latency: float = 0, est_tokens: int = 0, source: str = "unknown"):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
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

def call_llm(task_type: str, prompt: str, require_json: bool = False, source: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway.call(task_type, prompt, require_json=require_json, source=source, **kwargs)

def _parse_json(text: str) -> dict:
    """Robustly extract JSON from LLM markdown-wrapped text."""
    try:
        return json.loads(text)
    except:
        clean = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
        clean = re.sub(r'\s*```$', '', clean, flags=re.MULTILINE)
        try:
            return json.loads(clean)
        except:
            match = re.search(r'(\{.*\})', clean, re.DOTALL)
            if match:
                return json.loads(match.group(1))
    raise ValueError("No valid JSON found in response")

def call_json_llm(task_type: str, prompt: str, **kwargs) -> tuple[dict, str, int]:
    """Helper for legacy scripts expecting (json_dict, reasoning, tokens).
    Leverages native gateway JSON fallback for resilience.
    """
    res = call_llm(task_type, prompt, require_json=True, **kwargs)
    data = res['json']
    reasoning = data.get('reasoning', '') or res['text'][:200]
    return data, reasoning, res['tokens']
