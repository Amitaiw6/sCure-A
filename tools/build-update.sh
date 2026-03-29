#!/bin/bash
#
# sCure Update Package Builder
# Run on your development machine to create a signed update package.
#
# Usage:
#   ./tools/build-update.sh [version]
#   Example: ./tools/build-update.sh 1.2.0
#
# Output:
#   updates/scure-update-1.2.0.scu   (signed update package)
#
# First time setup (generate signing keys):
#   ./tools/build-update.sh --init-keys
#
# The .scu file is a tar.gz with a manifest + signature.
# Copy it to a USB stick root folder to deploy.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
KEYS_DIR="$PROJECT_DIR/keys"
UPDATES_DIR="$PROJECT_DIR/updates"
PRIVATE_KEY="$KEYS_DIR/scure-update.key"
PUBLIC_KEY="$KEYS_DIR/scure-update.pub"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Generate signing keys
if [ "$1" = "--init-keys" ]; then
    echo -e "${YELLOW}Generating signing keys...${NC}"
    mkdir -p "$KEYS_DIR"
    openssl genrsa -out "$PRIVATE_KEY" 4096
    openssl rsa -in "$PRIVATE_KEY" -pubout -out "$PUBLIC_KEY"
    echo -e "${GREEN}Keys generated:${NC}"
    echo "  Private: $PRIVATE_KEY (KEEP SECRET!)"
    echo "  Public:  $PUBLIC_KEY (deploy to RPi)"
    echo ""
    echo "Copy public key to RPi:"
    echo "  scp $PUBLIC_KEY pi@<rpi-ip>:/opt/scure/keys/"
    exit 0
fi

# Version
VERSION="${1:-$(date +%Y%m%d.%H%M%S)}"
echo -e "${GREEN}Building sCure update package v${VERSION}${NC}"

# Check keys exist
if [ ! -f "$PRIVATE_KEY" ]; then
    echo -e "${RED}Error: Signing key not found. Run: ./tools/build-update.sh --init-keys${NC}"
    exit 1
fi

# Step 1: Build frontend
echo -e "${YELLOW}[1/5] Building frontend...${NC}"
cd "$PROJECT_DIR"
npm run build

# Step 2: Create staging directory
echo -e "${YELLOW}[2/5] Staging files...${NC}"
STAGING=$(mktemp -d)
PACKAGE_NAME="scure-update-${VERSION}"

mkdir -p "$STAGING/$PACKAGE_NAME/frontend"
mkdir -p "$STAGING/$PACKAGE_NAME/server"
mkdir -p "$STAGING/$PACKAGE_NAME/materials/presets"

# Frontend build
cp -r dist/* "$STAGING/$PACKAGE_NAME/frontend/"

# Server files
cp server/app.py "$STAGING/$PACKAGE_NAME/server/"
cp server/requirements.txt "$STAGING/$PACKAGE_NAME/server/"
[ -d server/hardware ] && cp -r server/hardware "$STAGING/$PACKAGE_NAME/server/"

# Preset materials
cp -r public/materials/presets/* "$STAGING/$PACKAGE_NAME/materials/presets/"

# Step 3: Create manifest
echo -e "${YELLOW}[3/5] Creating manifest...${NC}"
cat > "$STAGING/$PACKAGE_NAME/manifest.json" << EOF
{
  "name": "sCure",
  "version": "${VERSION}",
  "build_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "build_machine": "$(hostname)",
  "min_firmware": "0.60.0",
  "files": {
    "frontend": "frontend/",
    "server": "server/",
    "presets": "materials/presets/"
  },
  "install": {
    "pre_install": "install.sh --pre",
    "post_install": "install.sh --post",
    "rollback": "install.sh --rollback"
  }
}
EOF

# Step 4: Create install script
cat > "$STAGING/$PACKAGE_NAME/install.sh" << 'INSTALL_EOF'
#!/bin/bash
# sCure Update Installer - runs on RPi CM5
set -e

INSTALL_DIR="/opt/scure"
BACKUP_DIR="/opt/scure-backup-$(date +%Y%m%d%H%M%S)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

case "$1" in
  --pre)
    echo "[UPDATE] Pre-install: backing up current version..."
    cp -r "$INSTALL_DIR" "$BACKUP_DIR" 2>/dev/null || true
    ;;
  --post)
    echo "[UPDATE] Installing new version..."

    # Stop services
    systemctl stop scure-ui 2>/dev/null || true
    systemctl stop scure-api 2>/dev/null || true

    # Update frontend
    rm -rf "$INSTALL_DIR/frontend"
    cp -r "$SCRIPT_DIR/frontend" "$INSTALL_DIR/frontend"

    # Update server
    cp "$SCRIPT_DIR/server/app.py" "$INSTALL_DIR/server/app.py"
    cp "$SCRIPT_DIR/server/requirements.txt" "$INSTALL_DIR/server/requirements.txt"
    pip3 install -r "$INSTALL_DIR/server/requirements.txt" --quiet

    # Update presets (don't touch user materials)
    cp -r "$SCRIPT_DIR/materials/presets/"* "$INSTALL_DIR/materials/presets/"

    # Rebuild C++ driver if source updated
    if [ -d "$SCRIPT_DIR/server/hardware" ]; then
      cp -r "$SCRIPT_DIR/server/hardware" "$INSTALL_DIR/server/hardware"
      cd "$INSTALL_DIR/server/hardware"
      [ -f build.sh ] && chmod +x build.sh && ./build.sh && cp hw_driver*.so ../
    fi

    # Restart services
    systemctl start scure-api
    systemctl start scure-ui

    echo "[UPDATE] Complete! Version: $(cat "$SCRIPT_DIR/manifest.json" | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])")"
    ;;
  --rollback)
    echo "[UPDATE] Rolling back..."
    if [ -d "$BACKUP_DIR" ]; then
      rm -rf "$INSTALL_DIR"
      mv "$BACKUP_DIR" "$INSTALL_DIR"
      systemctl restart scure-api scure-ui
      echo "[UPDATE] Rolled back successfully"
    else
      echo "[UPDATE] No backup found!"
      exit 1
    fi
    ;;
esac
INSTALL_EOF
chmod +x "$STAGING/$PACKAGE_NAME/install.sh"

# Step 5: Package and sign
echo -e "${YELLOW}[4/5] Packaging...${NC}"
mkdir -p "$UPDATES_DIR"
cd "$STAGING"
tar czf "$PACKAGE_NAME.tar.gz" "$PACKAGE_NAME/"

echo -e "${YELLOW}[5/5] Signing package...${NC}"
openssl dgst -sha256 -sign "$PRIVATE_KEY" -out "$PACKAGE_NAME.tar.gz.sig" "$PACKAGE_NAME.tar.gz"

# Create final .scu package (tar with payload + signature)
tar cf "$UPDATES_DIR/$PACKAGE_NAME.scu" "$PACKAGE_NAME.tar.gz" "$PACKAGE_NAME.tar.gz.sig"

# Cleanup
rm -rf "$STAGING"

# Summary
SIZE=$(du -h "$UPDATES_DIR/$PACKAGE_NAME.scu" | cut -f1)
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Update package ready!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "  File:    ${UPDATES_DIR}/${PACKAGE_NAME}.scu"
echo -e "  Version: ${VERSION}"
echo -e "  Size:    ${SIZE}"
echo ""
echo -e "  ${YELLOW}Deploy:${NC} Copy .scu file to USB stick root"
echo -e "  ${YELLOW}Install:${NC} Insert USB → Settings → Update Software"
echo ""
