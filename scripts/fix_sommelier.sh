#!/bin/bash
# fix_sommelier.sh
# Fixes ChromeOS Screenshot Shortcuts by configuring the Sommelier display bridge globally.
# V2: Uses 'zz-' prefix to ensure override priority.

set -e

echo "🔧 Configuring Sommelier Accelerators (Global Fix V2)..."

# The accelerator string: Print (Screenshot) and Alt+Shift+S (Selection)
ACCEL_STRING="Print,<Alt><Shift>s"

# Override content
OVERRIDE_CONTENT="[Service]
Environment=\"SOMMELIER_ACCELERATORS=${ACCEL_STRING}\"
"

# Function to apply override
apply_override() {
    local service_dir="$1"
    # Essential: Start with 'zz-' to load AFTER 'cros-sommelier-x-override.conf'
    local override_file="${service_dir}/zz-cros-sommelier-override.conf"
    
    # Cleanup old attempts
    if [ -f "${service_dir}/cros-sommelier-override.conf" ]; then
        sudo rm "${service_dir}/cros-sommelier-override.conf"
    fi

    if [ -d "$service_dir" ]; then
        echo "   Targeting: $service_dir"
        
        # We need sudo to write to /etc
        echo "$OVERRIDE_CONTENT" | sudo tee "$override_file" > /dev/null
        echo "     ✅ Created: $override_file (High Priority)"
    fi
}

# Apply to Wayland bridge
apply_override "/etc/systemd/user/sommelier@0.service.d"

# Apply to X11 bridge (where VS Code lives)
apply_override "/etc/systemd/user/sommelier-x@0.service.d"

echo "🔄 Reloading systemd configuration..."
systemctl --user daemon-reload

echo "♻️  Restarting Sommelier services..."
systemctl --user restart sommelier@0.service
systemctl --user restart sommelier-x@0.service

echo "✅ Optimization Complete!"
echo "   NOTE: Your open windows may have closed or flickered."
echo "   Please launch Antigravity and test the Screenshot Key [o] now."
