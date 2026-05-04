import sys
import os
import json

# Fix: Add the parent directory of 'toolbox' to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

try:
    from toolbox.lib.llm_gateway import LLMGateway
except ImportError:
    # Try local import if parent dir doesn't work (depends on how venv is set up)
    sys.path.insert(0, BASE_DIR)
    from lib.llm_gateway import LLMGateway

def test_live_routing():
    gateway = LLMGateway()
    
    print("--- Test 1: Cheapest Tier (Heartbeat) ---")
    res1 = gateway.call("heartbeat", "Tell me in 3 words if you are alive.")
    print(f"Response: {res1['text']}")
    print(f"Provider: {res1['provider']} ({res1['model']})")
    print(f"Cost: ${res1['cost']}")
    
    print("\n--- Test 2: Efficiency Tier (Automation) ---")
    res2 = gateway.call("automation", "Summarize this: The routing system is working.")
    print(f"Response: {res2['text']}")
    print(f"Provider: {res2['provider']} ({res2['model']})")
    print(f"Cost: ${res2['cost']}")

if __name__ == "__main__":
    try:
        test_live_routing()
    except Exception as e:
        print(f"\nERROR: {e}")
