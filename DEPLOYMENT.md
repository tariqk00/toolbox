# Deployment & Environment Rules

## 🛑 STRICT RULE: DEV vs PROD

### 💻 Development: Chromebook (penguin)

- **Role**: Coding, Testing, Dry Runs (`--scan`).
- **Automation**: **NEVER** run systemd timers or cron jobs here.
- **State**: Check `systemctl --user list-timers` regularly to ensure it is EMPTY.

### 🖥️ Production: NUC (nuc8i5-2020)

- **Role**: Execution, Automation, Hosting.
- **Automation**: Runs `ai-sorter.timer` (Hourly).
- **Deployment**: Code is deployed here for active duty.

---

## ⚠️ Known Issue: Deployment Blockage (Jan 2026)

- **Issue**: `git push` from Chromebook is blocked by permission errors.
- **Workaround**: Deploy to NUC via SCP/Manual Copy.
- **Do NOT**: Do not enable timers on Chromebook to "compensate". This causes Split Brain file corruption.

## Service Names

- **Chromebook**: `drive-sorter.service` (DISABLED)
- **NUC**: `ai-sorter.service` (ACTIVE)
