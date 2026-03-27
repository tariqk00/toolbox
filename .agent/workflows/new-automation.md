---
description: Create a new automation module following the Fitness Automation pattern
---

This workflow guides you through creating a new domain-specific automation module in `toolbox`.

1.  **Define Domain**:
    -   Choose a unique domain name (e.g., `finance`, `smarthome`).
    -   Create directory: `toolbox/[domain]/`.

2.  **Initialize Module**:
    -   Create `toolbox/[domain]/__init__.py`.
    -   Create `toolbox/[domain]/requirements.txt`.
    -   Create `toolbox/[domain]/main.py` (or specific script name).

3.  **Setup Environment**:
    -   Create venv: `python3 -m venv toolbox/[domain]/venv`.
    -   Install deps: `source toolbox/[domain]/venv/bin/activate && pip install -r toolbox/[domain]/requirements.txt`.

4.  **Create Service Files**:
    -   Create `setup/services/[domain]-[action].service`.
    -   Create `setup/services/[domain]-[action].timer`.

5.  **Documentation**:
    -   Update `toolbox/scriptReferences.md`.
    -   Add to `setup/docs/ENV_SETUP.md` (Deployment section).

6.  **Verification**:
    -   Run dry-run test.
    -   Deploy to NUC using `setup/scripts/deploy_fitness.sh` (or create a new deployment script if needed).
