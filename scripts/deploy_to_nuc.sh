#!/bin/bash
# toolbox/scripts/deploy_to_nuc.sh
# Automates the deployment workflow: Commit -> Push -> Pull (NUC) -> Restart Service

NUC_HOST="tariqk@172.30.0.169"
REMOTE_REPO="/home/tariqk/github/tariqk00/toolbox"
SERVICE_NAME="ai-sorter.service"

echo "=== Deployment Start: $(date) ==="

# 1. Check for uncommitted changes
if [[ -n $(git status -s) ]]; then
  echo "⚠️  You have uncommitted changes."
  echo "   Please commit them before deploying."
  exit 1
fi

# 2. Push to GitHub
echo "🚀 Pushing to origin/master..."
git push origin master
if [ $? -ne 0 ]; then
    echo "❌ Git push failed."
    exit 1
fi

# 3. Pull on NUC
echo "🔄 Updating NUC ($NUC_HOST)..."
ssh $NUC_HOST "cd $REMOTE_REPO && git fetch --all && git reset --hard origin/master"
if [ $? -ne 0 ]; then
    echo "❌ SSH Git pull/reset failed."
    exit 1
fi

# 4. Restart Service
echo "♻️  Restarting Service: $SERVICE_NAME..."
ssh $NUC_HOST "systemctl --user restart $SERVICE_NAME && systemctl --user status $SERVICE_NAME --no-pager"

echo "=== Deployment Complete ==="
