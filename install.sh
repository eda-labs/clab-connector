#!/bin/bash

# Create the wrapper script that preserves the original shell
cat > /usr/local/bin/clab-connector << 'EOF'
#!/usr/bin/env sh
exec uv run clab-connector "$@"
EOF

# Make it executable
chmod +x /usr/local/bin/clab-connector

echo "Installed clab-connector wrapper in /usr/local/bin/"