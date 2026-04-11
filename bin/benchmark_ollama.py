#!/usr/bin/env python3
import json
import time
import requests
import sys

# Ollama API Base URL (on NUC)
OLLAMA_URL = "http://localhost:11434/api/generate"

# Benchmark Models
MODELS = ["gemma4:e2b", "gemma4:e4b"]

# Test Prompt (Large enough to measure ingestion)
TEST_PROMPT = """
You are a documentation analysis assistant. Analyze the following project structure and provide a summary of its core purpose and modules.

Project: Toolbox
Modules:
- bin/: Contains executable scripts for Drive organization and Plaud automation.
- lib/: Core library for AI abstractions (Gemini, Ollama), Google API handling, and logging.
- services/: Higher-level composite services like drive_organizer.
- scripts/: Utility scripts for path fixing and reference generation.

Files of interest:
- ai_engine.py: Handles the LLM logic and caching.
- drive_utils.py: Manages Google Drive file operations.
- automation.py: The main entry point for Plaud recording processing.

Task: Summarize the primary data flow from email ingest to final storage in the PKM.
"""

def run_benchmark(model_name):
    print(f"\n--- Benchmarking Model: {model_name} ---")
    payload = {
        "model": model_name,
        "prompt": TEST_PROMPT,
        "stream": False
    }
    
    try:
        start_time = time.time()
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        end_time = time.time()
        
        if response.status_code != 200:
            print(f"Error: Ollama returned status {response.status_code}")
            return None
            
        data = response.json()
        
        # Ingestion Metrics
        prompt_eval_count = data.get("prompt_eval_count", 0)
        prompt_eval_duration = data.get("prompt_eval_duration", 1) / 1e9  # sec
        ingestion_tps = prompt_eval_count / prompt_eval_duration
        
        # Generation Metrics
        eval_count = data.get("eval_count", 0)
        eval_duration = data.get("eval_duration", 1) / 1e9  # sec
        generation_tps = eval_count / eval_duration
        
        # Total durations
        total_duration = data.get("total_duration", 1) / 1e9  # sec
        load_duration = data.get("load_duration", 0) / 1e9  # sec
        
        print(f"Ingestion: {prompt_eval_count} tokens in {prompt_eval_duration:.2f}s ({ingestion_tps:.2f} tok/s)")
        print(f"Generation: {eval_count} tokens in {eval_duration:.2f}s ({generation_tps:.2f} tok/s)")
        print(f"Load Time: {load_duration:.2f}s")
        print(f"Total Response Time: {total_duration:.2f}s")
        
        return {
            "model": model_name,
            "ingestion_tps": ingestion_tps,
            "generation_tps": generation_tps,
            "total_duration": total_duration
        }
        
    except Exception as e:
        print(f"Benchmark failed for {model_name}: {e}")
        return None

if __name__ == "__main__":
    results = []
    for model in MODELS:
        res = run_benchmark(model)
        if res:
            results.append(res)
    
    print("\n" + "="*40)
    print(f"{'Model':<15} | {'Ingest':<10} | {'Gen':<10}")
    print("-" * 40)
    for r in results:
        print(f"{r['model']:<15} | {r['ingestion_tps']:<10.2f} | {r['generation_tps']:<10.2f}")
    print("="*40)
