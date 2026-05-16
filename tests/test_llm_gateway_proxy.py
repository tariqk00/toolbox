import json
import unittest
import threading
import time
import requests
from unittest.mock import patch, MagicMock
from http.server import HTTPServer

from toolbox.bin.llm_gateway_proxy import LLMGatewayProxyHandler

class TestLLMGatewayProxy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Run server in a background thread
        cls.server = HTTPServer(('127.0.0.1', 0), LLMGatewayProxyHandler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        # Give it a moment to start
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    @patch('toolbox.bin.llm_gateway_proxy.call_llm')
    def test_completions_automation_mapping(self, mock_call_llm):
        mock_call_llm.return_value = {
            "text": "Hello from gateway",
            "tokens": 10,
            "cost": 0.0001
        }
        
        payload = {
            "model": "gateway/automation",
            "messages": [{"role": "user", "content": "Hi"}]
        }
        
        resp = requests.post(f"http://127.0.0.1:{self.port}/v1/chat/completions", json=payload)
        self.assertEqual(resp.status_code, 200)
        
        data = resp.json()
        self.assertEqual(data['choices'][0]['message']['content'], "Hello from gateway")
        self.assertEqual(data['usage']['total_tokens'], 10)
        
        # Verify call_llm was called with correct task_type
        mock_call_llm.assert_called_once()
        args, kwargs = mock_call_llm.call_args
        self.assertEqual(kwargs['task_type'], 'automation')
        self.assertIn("USER: Hi", kwargs['prompt'])
        self.assertEqual(kwargs['source'], 'openclaw')

    @patch('toolbox.bin.llm_gateway_proxy.call_llm')
    def test_unsupported_model(self, mock_call_llm):
        payload = {
            "model": "unknown/model",
            "messages": [{"role": "user", "content": "Hi"}]
        }
        
        resp = requests.post(f"http://127.0.0.1:{self.port}/v1/chat/completions", json=payload)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unsupported model", resp.json()['error']['message'])

    @patch('toolbox.bin.llm_gateway_proxy.call_llm')
    def test_streaming_returns_sse_chunks(self, mock_call_llm):
        mock_call_llm.return_value = {"text": "oneshot response", "tokens": 5}
        payload = {
            "model": "gateway/automation",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True
        }
        
        resp = requests.post(f"http://127.0.0.1:{self.port}/v1/chat/completions", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers['Content-Type'], 'text/event-stream')

        lines = [line.removeprefix("data: ") for line in resp.text.splitlines() if line.startswith("data: ")]
        self.assertGreaterEqual(len(lines), 3)
        chunk = json.loads(lines[0])
        final_chunk = json.loads(lines[1])
        self.assertEqual(chunk['object'], "chat.completion.chunk")
        self.assertEqual(chunk['choices'][0]['delta']['content'], "oneshot response")
        self.assertIsNone(chunk['choices'][0]['finish_reason'])
        self.assertEqual(final_chunk['choices'][0]['finish_reason'], "stop")
        self.assertEqual(lines[-1], "[DONE]")

    @patch('toolbox.bin.llm_gateway_proxy.call_llm')
    def test_openai_response_shape(self, mock_call_llm):
        mock_call_llm.return_value = {"text": "response", "tokens": 5}
        
        payload = {
            "model": "gateway/heartbeat",
            "messages": [{"role": "user", "content": "Hi"}]
        }
        
        resp = requests.post(f"http://127.0.0.1:{self.port}/v1/chat/completions", json=payload)
        data = resp.json()
        
        self.assertEqual(data['object'], "chat.completion")
        self.assertTrue(data['id'].startswith("chatcmpl-"))
        self.assertIsInstance(data['created'], int)
        self.assertEqual(data['model'], "gateway/heartbeat")
        self.assertEqual(data['choices'][0]['message']['role'], "assistant")
        self.assertEqual(data['choices'][0]['finish_reason'], "stop")

if __name__ == '__main__':
    unittest.main()
