# AGENTS.md — toolbox

Global rules: `~/dotfiles/AGENTS.md`

## Repo-specific

- Venv: `cd ~/github/tariqk00/toolbox && source venv/bin/activate`
- Tests: `pytest tests/ -q` — must pass before any commit
- Never commit `config/credentials.json` or any `token*.json`
- State files (`config/*/state.json`) are live production data — never reset without explicit instruction
