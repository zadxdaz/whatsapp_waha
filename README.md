# WAHA WhatsApp Integration for Odoo

Complete WhatsApp integration for Odoo using [WAHA (WhatsApp HTTP API)](https://waha.devlike.pro/).

## 📋 Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Architecture](#architecture)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## ✨ Features

### Core Functionality
- ✅ **Two-way messaging** - Send and receive WhatsApp messages
- ✅ **Media support** - Images, videos, audio, documents
- ✅ **Audio conversion** - Automatic OGG to MP3 conversion for browser compatibility
- ✅ **Group chats** - Full support for WhatsApp groups
- ✅ **Contact management** - Sync contacts with Odoo partners
- ✅ **Message templates** - Pre-defined message templates
- ✅ **Discuss integration** - Messages appear in Odoo Discuss interface

### Advanced Features
- ✅ **Real-time webhooks** - Instant message delivery via WAHA webhooks
- ✅ **Message status tracking** - Sent, delivered, read, failed states
- ✅ **Attachment management** - Automatic file downloads and storage
- ✅ **Chat history** - Complete conversation history per contact
- ✅ **Multi-account support** - Connect multiple WhatsApp numbers
- ✅ **Smart media handling** - Full-quality downloads (not thumbnails)

## 🔧 Requirements

- **Odoo**: 18.0 or higher
- **Python**: 3.10+
- **WAHA**: Latest version (WEBJS engine recommended)
- **ffmpeg**: Required for audio conversion (installed automatically in Docker)

### Python Dependencies
```txt
requests>=2.31.0
phonenumbers>=8.13.0
```

## 📦 Installation

### 1. Clone the Repository

```bash
cd /path/to/odoo/addons
git clone https://github.com/zadxdaz/whatsapp_waha.git waha
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Install ffmpeg (if not using Docker)

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

### 4. Update Odoo Configuration

Add the module path to your `odoo.conf`:
```ini
[options]
addons_path = /path/to/odoo/addons,/path/to/custom/addons
```

### 5. Install the Module

1. Restart Odoo server
2. Go to **Apps** menu
3. Update Apps List
4. Search for "WAHA WhatsApp"
5. Click **Install**

## ⚙️ Configuration

### 1. Configure WAHA Server

The module requires a running WAHA instance. See [WAHA Installation Guide](https://waha.devlike.pro/docs/how-to/install/).

**Docker Compose Example:**
```yaml
services:
  waha:
    image: devlikeapro/waha:latest
    restart: always
    ports:
      - "3000:3000"
    environment:
      - WAHA_API_KEY=your-secret-key
    volumes:
      - ./sessions:/app/.sessions
      - ./media:/app/.media
```

### 2. Create WhatsApp Account in Odoo

1. Go to **WhatsApp** → **Accounts**
2. Click **Create**
3. Fill in the details:
   - **Name**: My WhatsApp Business
   - **Session Name**: default (must match WAHA session)
   - **WAHA URL**: http://localhost:3000
   - **API Key**: your-secret-key
   - **Webhook URL**: http://your-odoo-server/waha/webhook

4. Click **Save**
5. Click **Start Session** to connect
6. Scan QR code with WhatsApp mobile app

### 3. Configure Webhook in WAHA

The webhook URL is automatically configured when you start a session from Odoo.

**Manual configuration (if needed):**
```bash
curl -X POST http://localhost:3000/api/sessions/default/webhooks \
  -H "X-Api-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "http://your-odoo-server/waha/webhook",
    "events": ["message", "message.ack"]
  }'
```

## 📱 Usage

### Sending Messages

#### From Discuss Interface
1. Open **Discuss** app
2. Select a WhatsApp chat or create new
3. Type your message and send

#### From Partner Form
1. Open a **Contact** (res.partner)
2. Click **Send WhatsApp** button
3. Compose and send message

#### Programmatically
```python
# Create and send message
message = self.env['waha.message'].create({
    'body': 'Hello from Odoo!',
    'wa_account_id': account.id,
    'partner_id': partner.id,
    'direction': 'outbound',
    'content_type': 'text',
})
# Message is automatically sent via compute method
```

### Receiving Messages

Messages are received automatically via webhooks:
1. WAHA sends webhook to Odoo
2. Message is created in `waha.message`
3. Discuss channel message is auto-created
4. Media is downloaded and attached
5. Contact is synced with partner

### Working with Media

#### Images and Videos
```python
# Media is automatically downloaded from URL (full quality)
# Attachments are created and linked to:
# - waha.message
# - discuss.channel
# - mail.message
```

#### Audio Messages
```python
# Audio files are automatically:
# 1. Downloaded from WAHA
# 2. Converted from OGG/Opus to MP3
# 3. Attached to message
```

### Message Templates

1. Go to **WhatsApp** → **Templates**
2. Click **Create**
3. Define template with variables: `{customer_name}`, `{order_number}`, etc.
4. Use template when sending messages

## 🏗️ Architecture

### Models

#### `waha.account`
Manages WhatsApp accounts and WAHA session connections.

**Key Methods:**
- `start_session()` - Connect to WhatsApp
- `stop_session()` - Disconnect
- `get_qr()` - Get QR code for authentication
- `test_connection()` - Verify WAHA connectivity

#### `waha.message`
Core message model with bidirectional sync.

**Key Features:**
- Auto-send on create (outbound messages)
- Auto-create discuss message
- Media processing and attachment creation
- Status tracking (sent, delivered, read, failed)

**Key Methods:**
- `process_payload_media()` - Download and attach media
- `_convert_audio_to_mp3()` - Convert audio files
- `update_status_from_webhook()` - Update from WAHA

#### `waha.chat`
Represents WhatsApp conversations (1:1 or groups).

**Key Features:**
- Linked to `discuss.channel`
- Last message tracking
- Unread count management

#### `waha.partner`
Extended contact information for WhatsApp.

**Key Features:**
- WhatsApp ID (wa_id)
- Profile picture sync
- Push name tracking

### Controllers

#### `webhook.py`
Handles incoming WAHA webhooks.

**Endpoints:**
- `POST /waha/webhook` - Receive messages and status updates

**Supported Events:**
- `message` - New incoming message
- `message.ack` - Message status update

### Tools

#### `waha_api.py`
Python wrapper for WAHA API.

**Methods:**
- `send_text()` - Send text message
- `send_file()` - Send media file
- `get_qr()` - Get QR code
- `start_session()` - Initialize session
- `stop_session()` - Close session

#### `phone_validation.py`
Phone number validation and formatting using `phonenumbers` library.

## 🔨 Development

### Project Structure

```
waha/
├── __init__.py
├── __manifest__.py
├── controller/
│   ├── __init__.py
│   └── webhook.py          # Webhook endpoint
├── data/
│   ├── ir_actions_server_data.xml
│   ├── ir_cron_data.xml
│   └── waha_demo.xml
├── migrations/
│   └── 2.0/
│       ├── __init__.py
│       └── post_migrate.py
├── models/
│   ├── __init__.py
│   ├── discuss_channel.py
│   ├── mail_thread.py
│   ├── res_partner.py
│   ├── res_users_settings.py
│   ├── waha_account.py
│   ├── waha_chat.py
│   ├── waha_group.py
│   ├── waha_message.py
│   ├── waha_partner.py
│   └── waha_template.py
├── security/
│   ├── ir.model.access.csv
│   ├── ir_module_category_data.xml
│   ├── ir_rules.xml
│   └── res_groups.xml
├── tools/
│   ├── __init__.py
│   ├── phone_validation.py
│   └── waha_api.py
├── views/
│   ├── discuss_channel_views.xml
│   ├── res_partner_views.xml
│   ├── waha_account_views.xml
│   ├── waha_chat_views.xml
│   ├── waha_menus.xml
│   ├── waha_message_views.xml
│   ├── waha_partner_views.xml
│   └── waha_template_views.xml
└── wizard/
    ├── __init__.py
    ├── waha_composer.py
    └── waha_composer_views.xml
```

### Running Tests

```bash
# Run module tests
odoo-bin -d test_db -i waha --test-enable --stop-after-init

# Run specific test
odoo-bin -d test_db -i waha --test-enable --test-tags /waha
```

### Debugging

Enable debug logging in `odoo.conf`:
```ini
[options]
log_level = debug
log_handler = odoo.addons.waha:DEBUG
```

View logs:
```bash
# Docker
docker compose logs -f odoo | grep waha

# Direct installation
tail -f /var/log/odoo/odoo.log | grep waha
```

## 🐛 Troubleshooting

### Common Issues

#### 1. Messages not received
**Symptoms:** Incoming messages don't appear in Odoo

**Solutions:**
- Check webhook is configured in WAHA
- Verify webhook URL is accessible from WAHA container
- Check Odoo logs for webhook errors
- Test webhook manually: `curl -X POST http://odoo:8069/waha/webhook`

#### 2. Media not downloading
**Symptoms:** Images/videos show as broken attachments

**Solutions:**
- Verify WAHA URL is accessible from Odoo
- Check API key is correct
- Ensure sufficient disk space
- Check file permissions on attachment storage

#### 3. Audio files not playing
**Symptoms:** Audio attachments download but don't play inline

**Solutions:**
- Verify ffmpeg is installed: `ffmpeg -version`
- Check audio conversion logs
- Ensure libmp3lame codec is available
- Test manual conversion: `ffmpeg -i input.ogg output.mp3`

#### 4. QR code not appearing
**Symptoms:** Can't scan QR to connect WhatsApp

**Solutions:**
- Check WAHA session status: `GET /api/sessions/default`
- Restart WAHA session
- Clear browser cache
- Verify WAHA container is running

#### 5. Duplicate messages
**Symptoms:** Same message appears multiple times

**Solutions:**
- Check for multiple webhook configurations
- Verify message deduplication by `msg_uid`
- Check cron jobs aren't running multiple times

### Debug Commands

```bash
# Check WAHA status
curl -H "X-Api-Key: your-key" http://localhost:3000/api/sessions

# Test webhook endpoint
curl -X POST http://localhost:8069/waha/webhook \
  -H "Content-Type: application/json" \
  -d '{"event":"message","payload":{"from":"1234567890@c.us"}}'

# Verify ffmpeg
docker compose exec odoo ffmpeg -version

# Check Odoo database
docker compose exec postgres psql -U odoo -d odoo \
  -c "SELECT COUNT(*) FROM waha_message;"
```

## 📄 License

This module is licensed under LGPL-3.

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📞 Support

- **GitHub Issues**: https://github.com/zadxdaz/whatsapp_waha/issues
- **WAHA Documentation**: https://waha.devlike.pro/
- **Odoo Documentation**: https://www.odoo.com/documentation/18.0/

## 🙏 Credits

- **WAHA**: https://waha.devlike.pro/
- **Odoo**: https://www.odoo.com/

---

**Version:** 2.0  
**Odoo Version:** 18.0  
**Last Updated:** January 2026
