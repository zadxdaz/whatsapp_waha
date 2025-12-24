#!/bin/bash
# Quick Start Script for WAHA Module Testing

echo "=================================="
echo "WAHA Module - Quick Start"
echo "=================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Check WAHA Docker
echo -e "${YELLOW}Step 1: Checking WAHA Docker container...${NC}"
if docker ps | grep -q waha; then
    echo -e "${GREEN}✓ WAHA container is running${NC}"
else
    echo -e "${RED}✗ WAHA container not found${NC}"
    echo ""
    echo "Starting WAHA container..."
    docker run -d \
      --name waha \
      --restart always \
      -p 3000:3000 \
      -v $(pwd)/waha-data:/app/.sessions \
      -e WHATSAPP_HOOK_URL=http://localhost:8069/waha/webhook \
      -e WHATSAPP_HOOK_EVENTS=message,message.ack,session.status \
      devlikeapro/waha
    
    echo -e "${GREEN}✓ WAHA container started${NC}"
fi

# Step 2: Check WAHA Health
echo ""
echo -e "${YELLOW}Step 2: Checking WAHA health...${NC}"
if curl -s http://localhost:3000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ WAHA is healthy and responding${NC}"
else
    echo -e "${RED}✗ WAHA is not responding${NC}"
    echo "Wait a few seconds for WAHA to start..."
    sleep 5
fi

# Step 3: Check Python dependencies
echo ""
echo -e "${YELLOW}Step 3: Checking Python dependencies...${NC}"
if python3 -c "import phonenumbers" 2>/dev/null; then
    echo -e "${GREEN}✓ phonenumbers installed${NC}"
else
    echo -e "${RED}✗ phonenumbers not installed${NC}"
    echo "Installing phonenumbers..."
    pip3 install phonenumbers
fi

if python3 -c "import requests" 2>/dev/null; then
    echo -e "${GREEN}✓ requests installed${NC}"
else
    echo -e "${RED}✗ requests not installed${NC}"
    echo "Installing requests..."
    pip3 install requests
fi

# Step 4: Module location
echo ""
echo -e "${YELLOW}Step 4: Module Information${NC}"
MODULE_PATH=$(pwd)
echo "Module path: $MODULE_PATH/waha"
echo ""

# Step 5: Next steps
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Copy module to Odoo addons:"
echo "   cp -r $MODULE_PATH/waha /path/to/odoo/addons/"
echo ""
echo "2. Restart Odoo:"
echo "   sudo systemctl restart odoo"
echo "   # or"
echo "   ./odoo-bin -c odoo.conf"
echo ""
echo "3. Update Apps List in Odoo:"
echo "   - Activate Debug Mode"
echo "   - Apps → Update Apps List"
echo ""
echo "4. Install WAHA Messaging module"
echo ""
echo "5. Create WhatsApp Account:"
echo "   - WhatsApp → Configuration → Accounts → Create"
echo "   - WAHA URL: http://localhost:3000"
echo "   - Session Name: default"
echo ""
echo "6. Connect and scan QR code"
echo ""
echo -e "${GREEN}Ready to go!${NC}"
echo ""
echo "Documentation:"
echo "  - README.md - General info"
echo "  - INSTALLATION.md - Detailed installation guide"
echo "  - MODULE_STATUS.md - Complete structure and status"
echo ""
echo "WAHA Dashboard: http://localhost:3000"
echo "Odoo: http://localhost:8069"
echo ""
