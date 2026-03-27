#!/bin/bash
# verify-openclaw.sh
# Description: Daily health check for OpenClaw native deployment.

# Colors for readability
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SERVER="nuc"
if [ "$(hostname)" = "nuc8i5-2020" ]; then
    CMD_PREFIX=""
    IS_NUC=true
else
    CMD_PREFIX="ssh $SERVER"
    IS_NUC=false
fi

echo -e "=========================================================="
echo -e " 🦞 ${GREEN}OpenClaw Daily Verification & Health Suite${NC} 🦞 "
echo -e "=========================================================="
echo -e "Time: $(date)\n"

# 1. Nightly Maintenance
echo -e ">>> 1. Nightly Maintenance Tasks (11:55 PM & 6:00 AM)"
MAINTENANCE_LOGS=$($CMD_PREFIX 'journalctl --user -u openclaw-heartbeat.service --since "24 hours ago" | grep -i "Read HEARTBEAT.md"' 2>/dev/null)
if [ -n "$MAINTENANCE_LOGS" ]; then
    echo -e "   [${GREEN}OK${NC}] Found scheduled heartbeat logs in the last 24 hours."
else
    echo -e "   [${RED}WARNING${NC}] No scheduled heartbeat execution logs found!"
fi
echo ""

# 2. Heartbeat Timer
echo -e ">>> 2. 30-Minute Heartbeat Timer Health"
TIMER_STATUS=$($CMD_PREFIX 'systemctl --user status openclaw-heartbeat.timer | grep -E "Active:|Trigger:"' 2>/dev/null)
if echo "$TIMER_STATUS" | grep -q "active (waiting)"; then
    TRIGGER_TIME=$(echo "$TIMER_STATUS" | grep "Trigger:" | sed 's/^[ \t]*//')
    echo -e "   [${GREEN}OK${NC}] Timer is Active."
    echo -e "   [${GREEN}INFO${NC}] ${TRIGGER_TIME}"
else
    echo -e "   [${RED}FAIL${NC}] Timer is not active! Output:\n$TIMER_STATUS"
fi
echo ""

# 3. Doctor
echo -e ">>> 3. OpenClaw Doctor Assessment"
DOCTOR_OUT=$($CMD_PREFIX '/home/tariqk/bin/openclaw doctor | grep -vE "allowInsecureAuth|dangerouslyDisableDeviceAuth|openclaw-gateway"' 2>&1)
if [[ "$DOCTOR_OUT" == *"Config invalid"* || "$DOCTOR_OUT" == *"error:"* || "$DOCTOR_OUT" == *"Config keys"* ]]; then
    # We strip empty lines and the ASCII box drawing that doctor outputs if there's an error.
    echo -e "   [${RED}WARNING${NC}] Doctor reported issues:"
    echo "$DOCTOR_OUT" | sed 's/^/      /'
else
    echo -e "   [${GREEN}OK${NC}] Passed. No unexpected configuration warnings."
fi
echo ""

# 4. Telegram Sync & Internal Errors
echo -e ">>> 4. Telegram Sync & Internal Errors (Last 5000 lines)"
ERRORS_OUT=$($CMD_PREFIX '/home/tariqk/bin/openclaw logs | tail -n 5000 | grep -iE "error:|ETIMEDOUT|ENETUNREACH|telegram/network|disconnect"' 2>/dev/null)
if [ -n "$ERRORS_OUT" ]; then
    ERROR_COUNT=$(echo "$ERRORS_OUT" | wc -l)
    echo -e "   [${YELLOW}WARNING${NC}] ${ERROR_COUNT} Network/Sync warnings detected recently (showing last 5):"
    echo "$ERRORS_OUT" | tail -n 5 | sed 's/^/      /'
else
    echo -e "   [${GREEN}OK${NC}] No recent Telegram sync or internal errors found."
fi
echo ""

# 5. Gateway Stability
echo -e ">>> 5. Gateway Service Stability"
GATEWAY_ERR=$($CMD_PREFIX 'journalctl --user -u openclaw-gateway.service --since "24 hours ago" | grep -iE "error|failed|crash|restart"' 2>/dev/null)
if [ -n "$GATEWAY_ERR" ]; then
    echo -e "   [${RED}WARNING${NC}] Gateway service crashed or restarted recently:"
    echo "$GATEWAY_ERR" | tail -n 3 | sed 's/^/      /'
else
    echo -e "   [${GREEN}OK${NC}] Gateway service is stable. No crashes recorded."
fi
echo ""

# 6. Repo Sync & Diff
echo -e ">>> 6. Configuration Repo Sync & Diff"
if [ "$IS_NUC" = true ]; then
    cp /home/tariqk/.openclaw/openclaw.json /home/tariqk/repos/personal/setup/hosts/nuc-server/openclaw/openclaw.json
    rsync -a --delete /home/tariqk/.openclaw/workspace/ /home/tariqk/repos/personal/setup/hosts/nuc-server/openclaw/workspace/
    echo -e "   [${GREEN}OK${NC}] State synced to ~/repos/personal/setup/hosts/nuc-server/openclaw."
else
    scp $SERVER:/home/tariqk/.openclaw/openclaw.json /home/tariqk/repos/personal/setup/hosts/nuc-server/openclaw/openclaw.json >/dev/null 2>&1
    rsync -a --delete -e ssh $SERVER:/home/tariqk/.openclaw/workspace/ /home/tariqk/repos/personal/setup/hosts/nuc-server/openclaw/workspace/ >/dev/null 2>&1
    echo -e "   [${GREEN}OK${NC}] Interal State synced locally to setup repo."
    
    cd /home/tariqk/repos/personal/setup || exit 1
    git add hosts/nuc-server/openclaw/ -N
    DIFF_OUT=$(git diff --stat hosts/nuc-server/openclaw)
    if [ -n "$DIFF_OUT" ]; then
        echo -e "   [${YELLOW}INFO${NC}] Config changes found:"
        echo "$DIFF_OUT" | awk '{print "      " $0}'
    else
        echo -e "   [${GREEN}OK${NC}] Configuration matches repository (no changes)."
    fi
fi

echo -e "\n=========================================================="
echo -e " Verification Complete."
echo -e "=========================================================="
