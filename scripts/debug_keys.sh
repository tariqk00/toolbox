#!/bin/bash
# debug_keys.sh
# Launches xev to capture key events.

LOG_FILE="$HOME/github/tariqk00/key_debug.log"

echo "🕵️  Step 1: Launching Key Capture Tool..."
echo "     A small white window calling 'Event Tester' will appear."
echo "     Please click on that window to focus it."
echo ""
echo "⌨️  Step 2: Press your Screenshot Key [o] !"
echo "     Also press Alt+Shift+S."
echo ""
echo "❌  Step 3: Close the white window."
echo ""
echo "     (Output will be saved to $LOG_FILE)"

# Run xev, grepping for KeyPress events and the details immediate following
# We capture stderr/stdout to file
xev -event keyboard > "$LOG_FILE" 2>&1

echo "✅ Capture complete."
echo "   Please ask the AI to 'read the log file'."
