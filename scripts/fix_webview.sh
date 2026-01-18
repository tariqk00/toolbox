#!/bin/bash
# fix_webview.sh
# Fixes "InvalidStateError: Failed to register a ServiceWorker" in Antigravity Webviews
# 1. Kills lingering processes.
# 2. Cleans corrupted IPC/GPU caches.
# 3. Disables Hardware Acceleration in argv.json (Permanent Fix for ChromeOS).

set -e

echo "🧹 Starting Antigravity Webview Cleanup & Fix..."

# --- STEP 1: Process Termination ---
echo "🔪 Terminating lingering editor processes..."
# Killing the specific binary names for this environment
pkill -f "antigravity" || true
pkill -f "code" || true
pkill -f "vscode" || true
pkill -f "language_server" || true 
sleep 2

# --- STEP 2: Permanent Fix (Disable GPU) ---
echo "🛠️  Applying Webview Stability Fix (Disabling GPU Acceleration)..."

# Correct locations for Antigravity environment
ARGV_PATHS=(
    "$HOME/.antigravity/argv.json"
    "$HOME/.vscode/argv.json"
    "$HOME/.config/Antigravity/argv.json"
)

PATCH_APPLIED=false

for JSON_FILE in "${ARGV_PATHS[@]}"; do
    if [ -f "$JSON_FILE" ]; then
        echo "   Found config: $JSON_FILE"
        
        # Check if already disabled
        if grep -q "disable-hardware-acceleration" "$JSON_FILE"; then
            echo "     ✅ GPU Acceleration already disabled."
            PATCH_APPLIED=true
        else
            # Backup
            cp "$JSON_FILE" "$JSON_FILE.bak"
            
            # Insert the config line before the last closing brace
            sed -i '$s/}/,\n\t"disable-hardware-acceleration": true\n}/' "$JSON_FILE"
            
            echo "     ✅ Fixed: Added 'disable-hardware-acceleration': true"
            PATCH_APPLIED=true
        fi
    fi
done

if [ "$PATCH_APPLIED" = false ]; then
    echo "   ⚠️  Could not find 'argv.json' automatically."
    echo "       Searched: ${ARGV_PATHS[*]}"
fi


# --- STEP 3: Cache Cleanup ---
# Correct cache paths for Antigravity
CONFIG_DIRS=(
    "$HOME/.config/Antigravity"
    "$HOME/.config/Code"
)

echo "🗑️  Cleaning cache directories..."
for DIR in "${CONFIG_DIRS[@]}"; do
    if [ -d "$DIR" ]; then
        echo "   Scanning: $DIR"
        
        # Remove Service Worker Cache
        if [ -d "$DIR/Service Worker" ]; then
            rm -rf "$DIR/Service Worker"
            echo "     ✅ Removed: $DIR/Service Worker"
        fi
        if [ -d "$DIR/Service Worker" ]; then # sometimes partial remove needs check
             rm -rf "$DIR/Service Worker" 
        fi
        
        # Remove GPU Cache
        if [ -d "$DIR/GPUCache" ]; then
            rm -rf "$DIR/GPUCache"
            echo "     ✅ Removed: $DIR/GPUCache"
        fi
         
        # Remove generic Cache
        if [ -d "$DIR/Cache" ]; then
            rm -rf "$DIR/Cache"
            echo "     ✅ Removed: $DIR/Cache"
        fi
    fi
done

echo "✅ Optimization Complete!"
echo "🔄 Please restart the editor."
