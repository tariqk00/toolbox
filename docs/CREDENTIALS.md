# Credential Management Standard

This document defines the source of truth for all secrets, tokens, and credentials in the personal automation ecosystem.

## 1. The Source of Truth: `toolbox/config/`

All credentials MUST be stored in `~/github/tariqk00/toolbox/config/`. This directory is the central hub for both the Chromebook (Dev) and NUC (Prod).

### Global Secrets: `secrets.env`
The `secrets.env` file contains all API keys, passwords, and static tokens.
- **n8n**: `N8N_API_KEY`, `N8N_HOST`
- **GitHub**: `GITHUB_PERSONAL_ACCESS_TOKEN`
- **Garmin**: `GARMIN_EMAIL`, `GARMIN_PASSWORD`
- **Gemini**: `GEMINI_API_KEY`, `GEMINI_FREE_API_KEY`
- **Telegram**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

### Google OAuth Tokens: `token_*.json`
Google tokens are granularly named to prevent confusion:
- `token_gmail_plaud.json`: Primary Gmail scope for Plaud/Ingestion.
- `token_full_drive.json`: Full Drive access for AI Sorter.
- `token_tasks.json`: Google Tasks access.
- `token_combined.json`: Legacy combined scopes helper output. Deprecated and not part of the active managed token inventory.

## 2. Portability & Symlinks

To maintain compatibility with legacy code or specific service requirements, we use **absolute symlinks** pointing back to `toolbox/config/`.

**Example Pattern:**
`~/github/tariqk00/plaud/config/token.json -> ~/github/tariqk00/toolbox/config/token_gmail_plaud.json`

## 3. Environment Variables

Avoid hardcoding secrets in systemd units or `.bashrc`.
- **Systemd**: Use `EnvironmentFile=%h/github/tariqk00/toolbox/config/secrets.env`.
- **Python**: Use `from dotenv import load_dotenv` pointing to the central `secrets.env`.

## 4. Drift Prevention
- **NUC Deployment**: `deploy_nuc.sh` verifies the existence of these paths.
- **Portability Test**: `scripts/test_portability.py` checks for hardcoded secret paths.
- **Cleanup**: Any new `token.json` or `.env` files found in sub-repos should be moved to `toolbox/config/` and symlinked.
