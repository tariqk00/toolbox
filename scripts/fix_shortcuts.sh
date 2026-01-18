#!/bin/bash
# fix_shortcuts.sh
# Fixes ChromeOS Screenshot Shortcuts blocked by VS Code (Antigravity edition)
# by setting "keyboard.dispatch": "keyCode" in User Settings.

set -e

echo "⌨️  Applying VS Code Shortcut Fix..."

# Correct path for Antigravity environment
SETTINGS_PATHS=(
    "$HOME/.config/Antigravity/User/settings.json"
    "$HOME/.config/Code/User/settings.json"
)

PATCH_APPLIED=false

for JSON_FILE in "${SETTINGS_PATHS[@]}"; do
    if [ -f "$JSON_FILE" ]; then
        echo "   Found settings: $JSON_FILE"
        
        # Check if already set
        if grep -q "\"keyboard.dispatch\": \"keyCode\"" "$JSON_FILE"; then
            echo "     ✅ 'keyboard.dispatch' already set to 'keyCode'."
            PATCH_APPLIED=true
        else
            # Backup
            cp "$JSON_FILE" "$JSON_FILE.bak"
            
            # Use sed to insert the setting. 
            sed -i '$s/}/,\n\t"keyboard.dispatch": "keyCode"\n}/' "$JSON_FILE"
            
            echo "     ✅ Fixed: Added 'keyboard.dispatch': 'keyCode'"
            PATCH_APPLIED=true
        fi
    fi
done

if [ "$PATCH_APPLIED" = false ]; then
    echo "   ⚠️  Could not find 'settings.json' automatically."
    echo "       Checked: ${SETTINGS_PATHS[*]}"
else
    echo "✅ Fix Applied!"
    echo "🔄 Please Restart VS Code for keyboard changes to take effect."
fi
