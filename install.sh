#!/bin/bash

# Create the wrapper script
cat > /usr/local/bin/clab-connector << 'EOF'
#!/bin/bash
uv run clab-connector "$@"
EOF

# Make it executable
chmod +x /usr/local/bin/clab-connector

echo "Installed clab-connector wrapper in /usr/local/bin/"