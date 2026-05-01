# AGENTS.md — toolbox

Global rules: `~/dotfiles/AGENTS.md` (if available)

## 1. Role & Deployment Boundary
- **Role**: You are a developer/author.
- **Workflow (Shared Libs)**: For changes to `lib/` or `config/`, you **must** create a branch and open a PR.
- **Workflow (Docs/Typos)**: Direct pushes to `main` are permitted only for documentation and minor typo fixes.
- **Deployment**: **Do not run deployment scripts.** The NUC automatically pulls from `main` and deploys every 15 minutes.
- **Manual Trigger**: If a manual rollout is needed, it must be done from a NUC-native session via `bash ~/github/tariqk00/setup/deploy_nuc.sh`.

## 2. Repo-specific Rules
- **Venv**: `cd ~/github/tariqk00/toolbox && source venv/bin/activate`
- **Tests**: `pytest tests/ -q` — **MUST** pass before any commit.
- **Credentials**: Never commit `config/credentials.json`, `config/secrets.env`, or any `token*.json`.
- **State**: Files in `config/*/state.json` are live production data — never reset without explicit instruction.
- **Paths**: Use relative paths or `$HOME`. Never hardcode `/home/tariqk`.
