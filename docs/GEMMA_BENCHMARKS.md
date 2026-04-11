# Gemma Model Benchmarking Results (NUC)

**Date:** 2026-04-11
**Hardware:** NUC 8i5-2020 (8 CPU, 32GB RAM)
**Status:** OpenClaw Performance Optimization (#17)

## Model Performance Summary

| Model       | Ingestion (tok/s) | Generation (tok/s) | Status | Total Response Time |
|-------------|-------------------|-------------------|--------|---------------------|
| gemma4:e2b  | 35.75             | 11.91             | ✅ Pass | 118.73s             |
| gemma4:e4b  | TBD               | TBD               | ❌ Fail | **Timeout (> 120s)** |

### Key Observations
1. **gemma4:e2b** is highly viable for "Background Reader" tasks. It handles prompt ingestion at ~36 tokens/sec and generates at a very usable ~12 tokens/sec.
2. **gemma4:e4b** creates a significant bottleneck on the NUC. During ingestion, it failed to return a response within the 120s timeout window. This confirms the user observation (revert commit `2f4b5da`) that the 4B variant is too heavy for primary or high-latency tasks on this CPU.
3. **Thermal Impact:** Running these benchmarks pushed the CPU package temperature to **83°C** (from 39°C idle). 

## Recommendations
- **Switch Reader Agents to 2B:** The `gemma-reader` agent in `openclaw.json` should be updated to use `ollama/gemma4:e2b` for improved latency and reliability.
- **Reserve e4b/qwen for Batching:** Heavier models should only be used for non-interactive batch tasks (like `nightly-ops`) if at all.
