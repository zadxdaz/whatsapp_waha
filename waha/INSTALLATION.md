# Installation Guide - WAHA Messaging Module

## Prerequisites

### 1. WAHA Server Setup

#### Option A: Docker (Recommended)

```bash
# Pull and run WAHA container
docker run -d \
  --name waha \
  --restart always \
  -p 3000:3000 \
  -v /path/to/waha-data:/app/.sessions \
  -e WHATSAPP_HOOK_URL=http://YOUR_ODOO_SERVER/waha/webhook \
  -e WHATSAPP_HOOK_EVENTS=message,message.ack,session.status \
  -e WHATSAPP_API_KEY=your-secret-api-key \
  devlikeapro/waha

# Check if running
docker ps | grep waha

# View logs
docker logs -f waha
```

#### Option B: Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'
services:
  waha:
    image: devlikeapro/waha
    container_name: waha
    restart: always
    ports:
      - "3000:3000"
    volumes:
      - ./waha-sessions:/app/.sessions
    environment:
      - WHATSAPP_HOOK_URL=http://YOUR_ODOO_SERVER/waha/webhook
      - WHATSAPP_HOOK_EVENTS=message,message.ack,session.status
      - WHATSAPP_API_KEY=your-secret-api-key
      - WHATSAPP_API_HOSTNAME=0.0.0.0
```

Run with:
```bash
docker-compose up -d
```

### 2. Python Dependencies

```bash
# Activate Odoo virtual environment
source /path/to/odoo-venv/bin/activate

# Install dependencies
pip install phonenumbers requests

# Or use requirements.txt
pip install -r requirements.txt
```

Create `requirements.txt`:
```
phonenumbers>=8.13.0
requests>=2.31.0
```

### 3. Network Configuration

#### If Odoo and WAHA are on different servers:

1. **Ensure ports are open:**
   - WAHA: Port 3000
   - Odoo: Port 8069 (or your custom port)

2. **Configure firewall (Ubuntu/Debian):**
```bash
sudo ufw allow 3000/tcp  # WAHA
sudo ufw allow 8069/tcp  # Odoo
```

3. **Use public URLs or ngrok for testing:**
```bash
# Terminal 1: Expose Odoo
ngrok http 8069

# Terminal 2: Expose WAHA
ngrok http 3000
```

## Module Installation

### Step 1: Copy Module Files

```bash
# Navigate to Odoo addons directory
cd /path/to/odoo/addons

# Clone or copy the waha module
cp -r /path/to/waha_integration/waha .

# Set correct permissions
chmod -R 755 waha
chown -R odoo:odoo waha
```

### Step 2: Update Odoo Addons Path

Edit `odoo.conf`:

```ini
[options]
addons_path = /path/to/odoo/addons,/path/to/custom/addons,/path/to/waha_integration
```

### Step 3: Restart Odoo

```bash
# Using systemd
sudo systemctl restart odoo

# Or directly
./odoo-bin -c /path/to/odoo.conf
```

### Step 4: Update Apps List

1. Login to Odoo as Administrator
2. Navigate to: **Apps**
3. Click: **Update Apps List** (in debug mode)
4. Confirm update

### Step 5: Install Module

1. Search for "WAHA" or "WhatsApp"
2. Find "WAHA Messaging"
3. Click **Install**

## Configuration

### Step 1: Create WhatsApp Account

1. Go to: **WhatsApp → Configuration → Accounts**
2. Click **Create**
3. Fill in details:
   - **Name**: My WhatsApp Business
   - **WAHA URL**: http://localhost:3000 (or your WAHA server URL)
   - **Session Name**: default (must be unique)
   - **API Key**: (leave empty if not configured in WAHA)
   - **Webhook Verify Token**: Generate random token (e.g., `waha_secret_123`)
4. Click **Save**

### Step 2: Connect to WhatsApp

1. Open the account record
2. Click **Connect** button
3. Wait for status to change to "Connecting"
4. Click **Get QR Code**
5. QR code will appear on the form

### Step 3: Link WhatsApp Mobile App

1. Open WhatsApp on your mobile device
2. Go to: **Settings → Linked Devices**
3. Tap **Link a Device**
4. Scan the QR code displayed in Odoo
5. Wait for connection confirmation

### Step 4: Verify Connection

- Status should change to "Connected"
- Phone UID field should be populated
- Check WAHA logs: `docker logs waha`

## Testing

### Test 1: Send Test Message

1. Create a partner with mobile number
2. Open partner form
3. Click "Send WhatsApp" button
4. Write test message
5. Click Send
6. Check message status in **WhatsApp → Messages**

### Test 2: Receive Message

1. Send message to your WhatsApp number from another phone
2. Check if message appears in: **WhatsApp → Messages**
3. Verify message is linked to partner (if phone matches)

### Test 3: Template

1. Create template: **WhatsApp → Templates**
2. Add variables: `Hello {{name}}, welcome!`
3. Send template to partner
4. Verify variables are replaced with actual data

## Webhook Configuration

### Configure WAHA to Send Webhooks

Ensure WAHA environment variables are set:

```bash
WHATSAPP_HOOK_URL=http://your-odoo-domain.com/waha/webhook
WHATSAPP_HOOK_EVENTS=message,message.ack,session.status
```

### Test Webhook Manually

```bash
curl -X POST http://localhost:8069/waha/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: your-verify-token" \
  -d '{
    "event": "session.status",
    "session": "default",
    "payload": {
      "status": "WORKING"
    }
  }'
```

Expected response:
```json
{"status": "ok"}
```

## Troubleshooting

### Issue: Module Not Appearing in Apps List

**Solution:**
```bash
# Check module is in addons path
ls -la /path/to/odoo/addons/waha

# Check Odoo logs
tail -f /var/log/odoo/odoo.log

# Update apps list in debug mode
# Settings → Activate Debug Mode → Apps → Update Apps List
```

### Issue: Import Errors

**Solution:**
```bash
# Verify Python dependencies
pip list | grep phonenumbers
pip list | grep requests

# Reinstall if needed
pip install --upgrade phonenumbers requests
```

### Issue: Cannot Connect to WAHA

**Solution:**
```bash
# Test WAHA is accessible
curl http://localhost:3000/health

# Check WAHA logs
docker logs waha

# Verify network connectivity
ping your-waha-server

# Check firewall
sudo ufw status
```

### Issue: Webhooks Not Working

**Solution:**
1. Verify webhook URL is accessible from WAHA server
2. Check Odoo is not behind firewall blocking incoming requests
3. Review Odoo logs for webhook errors
4. Verify webhook token matches in both WAHA and Odoo

### Issue: Messages Stuck in "Outgoing"

**Solution:**
1. Check account status is "Connected"
2. Verify phone number format (must include country code)
3. Check WAHA logs for API errors
4. Review message failure details in Odoo

## Production Deployment

### Security Checklist

- [ ] Use HTTPS for Odoo and WAHA
- [ ] Set strong API keys for WAHA
- [ ] Configure webhook verify token
- [ ] Restrict access to WAHA port (3000) using firewall
- [ ] Use secure passwords for Odoo users
- [ ] Enable multi-factor authentication
- [ ] Regular backups of WAHA sessions directory

### Performance Optimization

1. **WAHA**: Increase resources if handling many sessions
```yaml
deploy:
  resources:
    limits:
      memory: 2G
      cpus: '2'
```

2. **Odoo**: Configure workers based on load
```ini
[options]
workers = 4
max_cron_threads = 2
```

3. **Database**: Add indexes for phone number searches
```sql
CREATE INDEX idx_partner_mobile ON res_partner(mobile);
CREATE INDEX idx_partner_phone ON res_partner(phone);
CREATE INDEX idx_waha_msg_number ON waha_message(mobile_number);
```

### Monitoring

Set up monitoring for:
- WAHA container health
- Odoo cron job execution
- Message delivery rates
- Webhook response times

### Backup Strategy

```bash
# Backup WAHA sessions
tar -czf waha-sessions-$(date +%Y%m%d).tar.gz /path/to/waha-sessions/

# Backup Odoo database (example)
pg_dump odoo_db > odoo_backup_$(date +%Y%m%d).sql
```

## Support

- **WAHA Documentation**: https://waha.devlike.pro
- **Odoo Documentation**: https://www.odoo.com/documentation/18.0
- **Module Issues**: Report to module maintainer

## Next Steps

After installation:
1. Create message templates for common use cases
2. Configure partner records with mobile numbers
3. Set up automated messages using server actions
4. Train users on sending/receiving WhatsApp messages
5. Monitor message statistics and delivery rates
