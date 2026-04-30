import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = ROOT / "config" / "inbox_scanner"
BIN_ROOT = ROOT / "bin"


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_inbox_scanner_config_paths_resolve_to_existing_credentials_and_tokens():
    configs = sorted(CONFIG_ROOT.glob("*/config.json"))
    assert configs, "Expected inbox_scanner config.json files to exist"

    for config_path in configs:
        data = json.loads(config_path.read_text())
        token_base_dir = Path(data["token_base_dir"]).expanduser()
        credentials_path = Path(data["credentials_path"]).expanduser()
        token_path = token_base_dir / "config" / data["token_filename"]

        assert token_base_dir.exists(), f"{config_path} token_base_dir missing: {token_base_dir}"
        assert credentials_path.exists(), f"{config_path} credentials_path missing: {credentials_path}"
        assert token_path.exists(), f"{config_path} token file missing: {token_path}"


def test_auth_related_bin_scripts_import_cleanly():
    targets = [
        ("monitor_tokens.py", "toolbox_bin_monitor_tokens"),
        ("setup_gmail_auth.py", "toolbox_bin_setup_gmail_auth"),
        ("generate_combined_token.py", "toolbox_bin_generate_combined_token"),
    ]

    for filename, module_name in targets:
        module = _load_module(BIN_ROOT / filename, module_name)
        assert module is not None
