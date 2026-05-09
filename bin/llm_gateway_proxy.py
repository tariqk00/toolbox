#!/usr/bin/env python3
"""
OpenAI-compatible proxy for LLMGateway.
Routes requests from OpenClaw and other OpenAI-compatible clients through 
the centralized LLMGateway routing and budget control plane.

Usage:
    export LLM_GATEWAY_PROXY_PORT=8081
    python3 bin/llm_gateway_proxy.py
"""
import os
import sys
import json
import time
import uuid
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List

# Add repo root and its parent to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from toolbox.lib.llm_gateway import call_llm

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("llm_gateway_proxy")

# Configuration
HOST = os.getenv('LLM_GATEWAY_PROXY_HOST', '127.0.0.1')
PORT = int(os.getenv('LLM_GATEWAY_PROXY_PORT', '8081'))

# Model to Task Mapping
MODEL_MAP = {
    "gateway/automation": "automation",
    "gateway/heartbeat": "heartbeat",
    "gateway/coding": "coding",
    "gateway/frontier": "frontier",
    "gateway/efficiency": "efficiency",
    "gateway/cheapest": "cheapest"
}

class LLMGatewayProxyHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/v1/chat/completions':
            self.handle_completions()
        else:
            self.send_error(404, "Not Found")

    def handle_completions(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            request_json = json.loads(post_data)
        except json.JSONDecodeError:
            self.send_error_json(400, "Invalid JSON")
            return

        model = request_json.get('model', '')
        messages = request_json.get('messages', [])
        stream = request_json.get('stream', False)

        if stream:
            self.send_error_json(400, "Streaming is not supported yet.")
            return

        # Robust model mapping: try exact match first, then base name
        base_model = model.split('/')[-1]
        task_type = MODEL_MAP.get(model) or MODEL_MAP.get(base_model)
        
        if not task_type:
            self.send_error_json(400, f"Unsupported model: {model}. Supported tasks: {list(MODEL_MAP.values())}")
            return

        # Convert messages to prompt
        prompt = self.format_messages(messages)
        
        try:
            logger.info(f"Proxying {model} -> task_type={task_type}")
            # We don't support multi-modal via proxy yet, so content_bytes=b''
            result = call_llm(task_type=task_type, prompt=prompt)
            
            response = self.format_openai_response(model, result)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
        except Exception as e:
            logger.error(f"Gateway error: {e}")
            self.send_error_json(500, str(e))

    def format_messages(self, messages: List[Dict[str, str]]) -> str:
        """Simple conversion of role/content list to a flat prompt."""
        lines = []
        for msg in messages:
            role = msg.get('role', 'user').upper()
            content = msg.get('content', '')
            # Handle list of content (e.g. for vision, though we don't support image bytes yet)
            if isinstance(content, list):
                text_parts = [p.get('text', '') for p in content if p.get('type') == 'text']
                content = "\n".join(text_parts)
            
            lines.append(f"{role}: {content}")
        
        return "\n\n".join(lines)

    def format_openai_response(self, model: str, gateway_result: Dict[str, Any]) -> Dict[str, Any]:
        """Convert LLMGateway result to OpenAI Chat Completion format."""
        completion_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())
        
        # Gateway returns total tokens. We estimate prompt tokens to be helpful.
        total_tokens = gateway_result.get('tokens', 0)
        # Rough estimate: 4 chars per token for prompt
        # gateway_result doesn't give us prompt vs completion tokens yet.
        # We'll just put everything in completion_tokens for now as a baseline.
        
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created_time,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": gateway_result.get('text', '')
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0, # Not tracked separately by gateway yet
                "completion_tokens": total_tokens,
                "total_tokens": total_tokens
            }
        }

    def send_error_json(self, code: int, message: str):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        error_response = {
            "error": {
                "message": message,
                "type": "invalid_request_error",
                "code": code
            }
        }
        self.wfile.write(json.dumps(error_response).encode('utf-8'))

    def log_message(self, format, *args):
        # Override to use our logger instead of stderr
        logger.info("%s - - [%s] %s" %
                    (self.client_address[0],
                     self.log_date_time_string(),
                     format % args))

def run(server_class=HTTPServer, handler_class=LLMGatewayProxyHandler):
    server_address = (HOST, PORT)
    httpd = server_class(server_address, handler_class)
    logger.info(f"Starting LLMGateway Proxy on {HOST}:{PORT}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping proxy...")
        httpd.server_close()

if __name__ == '__main__':
    run()
