#!/usr/bin/env python3
"""
Minimal MCP Server for Google Drive search.
Wraps the existing toolbox Drive utilities.
"""
import sys
import os
import json

# Add toolbox to path
sys.path.insert(0, '/home/tariqk/repos/personal')

from toolbox.lib.drive_utils import get_drive_service

def handle_request(request):
    """Handle a single JSON-RPC request."""
    method = request.get('method')
    params = request.get('params', {})
    req_id = request.get('id')
    
    if method == 'initialize':
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "gdrive-mcp-local", "version": "1.0.0"}
            }
        }
    elif method == 'notifications/initialized':
        return None  # No response for notifications
    elif method == 'tools/list':
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [{
                    "name": "search",
                    "description": "Search for files in Google Drive",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query (file name or content)"}
                        },
                        "required": ["query"]
                    }
                }]
            }
        }
    elif method == 'tools/call':
        tool_name = params.get('name')
        args = params.get('arguments', {})
        
        if tool_name == 'search':
            query = args.get('query', '')
            try:
                service = get_drive_service()
                # Build Google Drive query
                drive_query = f"name contains '{query}' or fullText contains '{query}'"
                results = service.files().list(
                    q=drive_query,
                    pageSize=20,
                    fields="files(id, name, mimeType, modifiedTime, webViewLink)"
                ).execute()
                
                files = results.get('files', [])
                content = []
                for f in files:
                    content.append(f"- {f['name']} ({f['mimeType']})")
                    if f.get('webViewLink'):
                        content.append(f"  Link: {f['webViewLink']}")
                
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{
                            "type": "text",
                            "text": f"Found {len(files)} files:\n" + "\n".join(content) if files else "No files found."
                        }]
                    }
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32603, "message": str(e)}
                }
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
            }
    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"}
        }

def main():
    """Main loop - read JSON-RPC from stdin, write responses to stdout."""
    sys.stderr.write("gdrive-mcp-local started.\n")
    sys.stderr.flush()
    
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            if response:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError as e:
            sys.stderr.write(f"JSON decode error: {e}\n")
            sys.stderr.flush()
        except Exception as e:
            sys.stderr.write(f"Error: {e}\n")
            sys.stderr.flush()

if __name__ == '__main__':
    main()
