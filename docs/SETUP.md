# System Setup & Rebuild Guide

This document captures the exact steps required to rebuild the **Chromebook (Dev)** and **NUC (Production)** environments for the Toolbox project.

---

## 🏗️ 1. Architecture Overview

- **Storage**: GitHub Private Repo (`tariqk00/toolbox`).
- **Dev Environment**: Chromebook (`penguin` container).
  - Used for: Coding, Testing, Dry Runs.
  - **RESTRICTION**: No automation timers enabled.
- **Prod Environment**: Intel NUC (`nuc8i5-2020`).
  - Used for: Hosted execution.
  - **FEATURE**: Runs hourly `ai-sorter.timer` automation.

---

## 💻 2. Chromebook Setup (Development)

### A. Prerequisites & Packages

```bash
sudo apt update
sudo apt install -y git python3 python3-venv gh
```

### B. GitHub Authentication (Critical)

We use a specific identified key for Antigravity access.

1.  Ensure `~/.ssh/id_ed25519_antigravity` exists.
2.  Configure SSH (`~/.ssh/config`):
    ```text
    Host github.com
      HostName github.com
      User git
      IdentityFile ~/.ssh/id_ed25519_antigravity
      IdentitiesOnly yes
    ```
3.  Authenticate GitHub CLI:
    ```bash
    gh auth login
    # Select: GitHub.com -> SSH -> /home/takhan/.ssh/id_ed25519_antigravity.pub
    ```

### C. Repository & Environment

```bash
cd ~/github/tariqk00
gh repo clone tariqk00/toolbox
cd toolbox/google-drive

# Setup Python Venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 🖥️ 3. NUC Setup (Production)

### A. System Prep

Connect via SSH:

```bash
ssh nuc
sudo apt update && sudo apt install -y git python3 python3-venv
```

### B. GitHub Authorization (Deploy Key)

Since the NUC is a headless server, we use a **Deploy Key**.

1.  Generate Key (if missing):
    ```bash
    ssh-keygen -t ed25519 -C "nuc8i5-2020" -f ~/.ssh/id_ed25519 -N ""
    ```
2.  Add to GitHub:
    - Copy key: `cat ~/.ssh/id_ed25519.pub`
    - Go to: `https://github.com/tariqk00/toolbox/settings/keys`
    - Add new Deploy Key (Read/Write recommended for logging).

### C. Deploy Code

```bash
mkdir -p ~/github/tariqk00
cd ~/github/tariqk00
git clone git@github.com:tariqk00/toolbox.git
cd toolbox/google-drive

# Setup Python Venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### D. Automation (The "Live" Switch)

1.  **Enable Linger** (allows timer to run even when user isn't logged in):
    ```bash
    sudo loginctl enable-linger tariqk
    ```
2.  **Install Service Files**:
    _Edit `ai-sorter.service` to ensure paths match `/home/tariqk/github/tariqk00/toolbox/...`_
    ```bash
    mkdir -p ~/.config/systemd/user
    cp ai-sorter.service ~/.config/systemd/user/
    cp ai-sorter.timer ~/.config/systemd/user/
    systemctl --user daemon-reload
    ```
3.  **Activate**:
    ```bash
    systemctl --user enable --now ai-sorter.timer
    systemctl --user list-timers
    ```

---

## 🔒 4. Secrets Management

Both environments require a `.env` or `credentials.json` (depending on the tool).
_Note: These are NOT in Git._

- **Google Credentials**: `credentials.json` and `token.json` must be manually SCP'd to `toolbox/google-drive/`.
- **Gemini Key**: Export `GEMINI_API_KEY` in environment or `.env` file.
