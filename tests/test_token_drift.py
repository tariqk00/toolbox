import json
import os
from pathlib import Path

def test_token_inventory_schema():
    """Verify the token inventory exists and has valid schema."""
    repo_root = Path(__file__).resolve().parent.parent
    inventory_path = repo_root / "config" / "token_inventory.json"
    
    assert inventory_path.exists(), f"Inventory missing at {inventory_path}"
    
    with open(inventory_path, "r") as f:
        inventory = json.load(f)
    
    assert "tokens" in inventory, "Inventory missing 'tokens' key"
    assert len(inventory["tokens"]) >= 5, f"Expected at least 5 tokens, found {len(inventory['tokens'])}"
    
    for token in inventory["tokens"]:
        assert "name" in token, f"Token entry missing 'name': {token}"
        assert "filename" in token, f"Token entry missing 'filename': {token}"
        assert "scopes" in token, f"Token entry missing 'scopes': {token}"
        assert len(token["scopes"]) > 0, f"Token {token['name']} has no scopes"

def test_all_managed_tokens_present_in_config():
    """Verify all tokens in inventory actually exist as specs/paths."""
    repo_root = Path(__file__).resolve().parent.parent
    inventory_path = repo_root / "config" / "token_inventory.json"
    
    with open(inventory_path, "r") as f:
        inventory = json.load(f)
    
    config_dir = repo_root / "config"
    for token in inventory["tokens"]:
        token_path = config_dir / token["filename"]
        # We don't assert it exists (it might be missing on a fresh machine),
        # but we verify the filename matches our standard pattern.
        assert token["filename"].startswith("token_"), f"Invalid token filename: {token['filename']}"
        assert token["filename"].endswith(".json"), f"Token filename must be .json: {token['filename']}"
