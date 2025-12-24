# Documento Técnico: Módulo de Integración WAHA para Odoo v18

## 1. Introducción

### 1.1 Objetivo
Desarrollar un módulo para Odoo v18 que permita la integración con WAHA (WhatsApp HTTP API), proporcionando capacidades de envío y recepción de mensajes de WhatsApp directamente desde el sistema Odoo.

**Este módulo está diseñado siguiendo la arquitectura exacta del módulo oficial `whatsapp` de Odoo v18**, adaptado para usar WAHA como backend en lugar de WhatsApp Business API (Graph API).

### 1.2 ¿Qué es WAHA?
**WAHA** (WhatsApp HTTP API) es una solución auto-hospedada que permite interactuar con WhatsApp mediante una API REST. Características principales:

- **Código Abierto**: Versión Core gratuita sin límites de mensajes
- **Auto-hospedado**: Se ejecuta en tu propio servidor mediante Docker
- **API REST**: Interfaz HTTP simple y documentada
- **Multi-sesión**: Soporte para múltiples cuentas de WhatsApp
- **WebHooks**: Recepción de mensajes en tiempo real
- **Funcionalidades**:
  - Envío/Recepción de mensajes (texto, imágenes, videos, audios)
  - Gestión de grupos
  - WhatsApp Channels y Status
  - Gestión de contactos
  - Lectura de estados
  - Y más...

### 1.3 Alcance del Módulo
El módulo `waha` permitirá:
- Configurar múltiples cuentas WAHA desde Odoo (similar a `whatsapp.account`)
- Enviar mensajes de WhatsApp desde diferentes módulos usando plantillas
- Recibir mensajes mediante webhooks y crear canales de discusión
- Gestionar plantillas de mensajes con variables dinámicas y botones
- Sincronizar conversaciones con `discuss.channel` (chatter integrado)
- Registro completo de mensajes vinculados a `mail.message`
- Soporte para adjuntos (imágenes, documentos, videos, audio)
- Validación de números telefónicos con `phone_validation`
- Composer modal integrado similar a `whatsapp.composer`

### 1.4 Diferencias Clave con WhatsApp Oficial
| Aspecto | WhatsApp de Odoo | WAHA Integration |
|---------|------------------|------------------|
| **Backend** | WhatsApp Business API (Graph API) | WAHA (Auto-hospedado) |
| **Autenticación** | App ID, Secret, Token | URL WAHA + Session Name |
| **Plantillas** | Aprobadas por WhatsApp | Sin aprobación necesaria |
| **Límites** | Límites de WhatsApp Business | Sin límites (WAHA Core) |
| **QR Code** | No necesario | Escaneo inicial requerido |
| **Costo** | Mensajes pagos | Gratuito (auto-hospedado) |

---

## 2. Arquitectura del Módulo

### 2.1 Estructura de Directorios
```
waha/                                    # Nombre del módulo (similar a 'whatsapp')
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── discuss_channel.py           # Extensión para canales de discusión
│   ├── discuss_channel_member.py    # Miembros del canal
│   ├── ir_actions_server.py         # Acciones automatizadas
│   ├── mail_message.py              # Extensión de mensajes
│   ├── mail_thread.py               # Capacidades de WhatsApp en chatter
│   ├── models.py                    # Modelos base/abstractos
│   ├── res_partner.py               # Extensión de contactos
│   ├── res_users_settings.py        # Configuración de usuario
│   ├── waha_account.py              # Cuentas WAHA (= whatsapp.account)
│   ├── waha_message.py              # Mensajes WhatsApp (= whatsapp.message)
│   ├── waha_template.py             # Plantillas (= whatsapp.template)
│   ├── waha_template_button.py      # Botones de plantillas
│   └── waha_template_variable.py    # Variables de plantillas
├── wizard/
│   ├── __init__.py
│   ├── waha_composer.py             # Composer (= whatsapp.composer)
│   ├── waha_composer_views.xml
│   ├── waha_preview.py              # Vista previa de mensajes
│   └── waha_preview_views.xml
├── controller/
│   ├── __init__.py
│   └── webhook.py                   # Controlador de webhooks
├── tools/
│   ├── __init__.py
│   ├── waha_api.py                  # Cliente API WAHA (= WhatsAppApi)
│   ├── waha_exception.py            # Excepciones personalizadas
│   └── phone_validation.py          # Validación de teléfonos
├── views/
│   ├── discuss_channel_views.xml
│   ├── ir_actions_server_views.xml
│   ├── res_config_settings_views.xml
│   ├── res_partner_views.xml
│   ├── waha_account_views.xml
│   ├── waha_message_views.xml
│   ├── waha_template_views.xml
│   ├── waha_template_button_views.xml
│   ├── waha_template_variable_views.xml
│   └── waha_menus.xml
├── security/
│   ├── ir.model.access.csv
│   ├── ir_rules.xml                 # Reglas de registro
│   └── res_groups.xml               # Grupos de seguridad
├── data/
│   ├── ir_actions_server_data.xml   # Acciones del servidor
│   ├── ir_cron_data.xml             # Tareas programadas
│   ├── ir_module_category_data.xml  # Categorías
│   └── waha_demo.xml                # Datos demo
└── static/
    ├── description/
    │   ├── icon.png
    │   └── index.html
    └── src/
        ├── scss/
        │   └── *.scss               # Estilos
        ├── components/              # Componentes OWL
        │   └── **/*
        ├── views/                   # Vistas JS
        │   └── **/*
        └── core/
            ├── common/              # Código común
            ├── web/                 # Web backend
            └── public_web/          # Web pública
```

**Nota**: Esta estructura es IDÉNTICA al módulo oficial de WhatsApp de Odoo v18, solo cambiando `whatsapp` por `waha`.

### 2.2 Dependencias
- **Odoo**: v18.0
- **Python**: >= 3.10
- **Módulos Odoo**: 
  - `mail` (requerido - sistema de mensajería)
  - `phone_validation` (requerido - validación de números)
  - `contacts` (base - gestión de contactos)
- **Bibliotecas Python**:
  - `requests`: Para llamadas HTTP a WAHA API
  - `phonenumbers`: Para validación y formateo de números
  - `markupsafe`: Para manejo seguro de HTML

**Referencia**: Basado en el `__manifest__.py` del módulo oficial de WhatsApp:
```python
'depends': ['mail', 'phone_validation'],
'external_dependencies': {
    'python': ['phonenumbers'],
}
```

### 2.3 Integración con WAHA
```
┌─────────────────┐         HTTP API          ┌──────────────┐
│                 │ ────────────────────────> │              │
│   Odoo v18      │  POST /api/sendText       │  WAHA API    │
│   (Módulo)      │  POST /api/sendImage      │  (Docker)    │
│                 │ <──────────────────────── │              │
└─────────────────┘      Webhooks             └──────────────┘
        │                                              │
        │                                              │
        └──────────────> PostgreSQL <─────────────────┘
                      (Logs & Config)
```

---

## 3. Modelos de Datos

## 3. Modelos de Datos

**IMPORTANTE**: Esta sección está basada 100% en el módulo oficial de WhatsApp de Odoo v18, adaptando solo las llamadas API de WhatsApp Business a WAHA.

### 3.1 waha.account
Cuentas de WhatsApp conectadas a WAHA (equivalente exacto a `whatsapp.account`).

```python
# models/waha_account.py
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.addons.waha.tools.waha_api import WahaApi
from odoo.addons.waha.tools.waha_exception import WahaError

class WahaAccount(models.Model):
    _name = 'waha.account'
    _inherit = ['mail.thread']
    _description = 'WAHA WhatsApp Account'

    # Información básica
    name = fields.Char(string="Name", tracking=True, required=True)
    active = fields.Boolean(default=True, tracking=True)
    
    # Configuración WAHA (reemplaza app_uid, app_secret, account_uid de WhatsApp)
    waha_url = fields.Char(
        string="WAHA Server URL",
        required=True,
        default='http://localhost:3000',
        tracking=True,
        help='URL base del servidor WAHA (ej: http://localhost:3000)'
    )
    session_name = fields.Char(
        string="Session Name",
        required=True,
        default='default',
        tracking=True,
        help='Nombre de la sesión en WAHA'
    )
    api_key = fields.Char(
        string="API Key",
        groups='waha.group_waha_admin',
        help='API Key para autenticación si WAHA la requiere'
    )
    
    # Información del número conectado
    phone_uid = fields.Char(
        string="Phone Number ID",
        readonly=True,
        copy=False,
        help='ID del número de teléfono (auto-generado)'
    )
    account_uid = fields.Char(
        string="Account UID",
        compute='_compute_account_uid',
        store=True,
        help='UID de la cuenta (basado en session_name)'
    )
    
    # Webhook
    webhook_verify_token = fields.Char(
        string="Webhook Verify Token",
        compute='_compute_verify_token',
        groups='waha.group_waha_admin',
        store=True,
        help='Token de verificación para webhook'
    )
    callback_url = fields.Char(
        string="Callback URL",
        compute='_compute_callback_url',
        readonly=True,
        copy=False
    )
    
    # QR Code para conexión
    qr_code = fields.Binary(
        string="QR Code",
        attachment=False,
        help='Código QR para vincular WhatsApp'
    )
    qr_code_expiry = fields.Datetime(
        string="QR Expiry",
        help='Fecha de expiración del QR'
    )
    
    # Estado de conexión
    status = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connecting', 'Connecting'),
        ('connected', 'Connected'),
        ('error', 'Error')
    ], default='disconnected', readonly=True, tracking=True)
    
    # Configuración
    allowed_company_ids = fields.Many2many(
        comodel_name='res.company',
        string="Allowed Companies",
        default=lambda self: self.env.company
    )
    notify_user_ids = fields.Many2many(
        comodel_name='res.users',
        default=lambda self: self.env.user,
        domain=[('share', '=', False)],
        required=True,
        tracking=True,
        help="Users to notify when a message is received"
    )
    
    # Estadísticas
    templates_count = fields.Integer(
        string="Templates Count",
        compute='_compute_templates_count'
    )
    
    # SQL Constraints (igual que whatsapp.account)
    _sql_constraints = [
        ('phone_uid_unique', 'unique(phone_uid)',
         "The same phone number ID already exists")
    ]

    @api.depends('session_name')
    def _compute_account_uid(self):
        """Genera account_uid basado en session_name"""
        for account in self:
            if account.session_name:
                account.account_uid = f"waha_{account.session_name}"
            else:
                account.account_uid = False

    @api.depends('session_name')
    def _compute_verify_token(self):
        """Genera token de verificación (igual que WhatsApp)"""
        import secrets
        import string
        for rec in self:
            if rec.id and not rec.webhook_verify_token:
                rec.webhook_verify_token = ''.join(
                    secrets.choice(string.ascii_letters + string.digits) 
                    for _ in range(8)
                )

    def _compute_callback_url(self):
        """Calcula URL del webhook"""
        for account in self:
            account.callback_url = self.get_base_url() + '/waha/webhook'

    def _compute_templates_count(self):
        """Cuenta plantillas asociadas"""
        for account in self:
            account.templates_count = self.env['waha.template'].search_count([
                ('wa_account_id', '=', account.id)
            ])

    @api.constrains('notify_user_ids')
    def _check_notify_user_ids(self):
        """Valida que haya al menos un usuario (igual que WhatsApp)"""
        for account in self:
            if len(account.notify_user_ids) < 1:
                raise ValidationError(_("Users to notify is required"))

    # ============================================================
    # MÉTODOS DE CONEXIÓN Y GESTIÓN DE SESIÓN
    # ============================================================

    def action_connect(self):
        """Inicia la conexión a WAHA (= start session)"""
        self.ensure_one()
        try:
            api = WahaApi(self)
            result = api.start_session()
            self.write({'status': 'connecting'})
            self.message_post(body=_('Session connection initiated'))
            return self.action_get_qr()
        except WahaError as err:
            self.write({'status': 'error'})
            raise UserError(str(err)) from err

    def action_get_qr(self):
        """Obtiene código QR para escanear"""
        self.ensure_one()
        try:
            api = WahaApi(self)
            qr_data = api.get_qr_code()
            
            if qr_data.get('qr'):
                self.qr_code = qr_data['qr']
                self.qr_code_expiry = fields.Datetime.now() + timedelta(minutes=2)
                
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'waha.account',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'current',
            }
        except WahaError as err:
            raise UserError(str(err)) from err

    def action_refresh_status(self):
        """Actualiza el estado de la conexión"""
        self.ensure_one()
        try:
            api = WahaApi(self)
            status_data = api.get_session_status()
            
            # Mapear estados de WAHA a estados del modelo
            waha_status = status_data.get('status', 'DISCONNECTED')
            if waha_status in ['WORKING', 'CONNECTED']:
                self.status = 'connected'
                self.qr_code = False  # Limpiar QR cuando está conectado
            elif waha_status in ['STARTING', 'SCAN_QR_CODE']:
                self.status = 'connecting'
            else:
                self.status = 'disconnected'
                
            self.message_post(body=_('Status updated: %s', self.status))
        except WahaError as err:
            self.status = 'error'
            raise UserError(str(err)) from err

    def action_disconnect(self):
        """Desconecta la sesión WAHA"""
        self.ensure_one()
        try:
            api = WahaApi(self)
            api.stop_session()
            self.write({
                'status': 'disconnected',
                'qr_code': False,
            })
            self.message_post(body=_('Session disconnected'))
        except WahaError as err:
            raise UserError(str(err)) from err

    def button_sync_waha_templates(self):
        """
        Sincroniza plantillas desde WAHA
        (Equivalente a button_sync_whatsapp_account_templates)
        
        Nota: WAHA no tiene sistema de aprobación de plantillas,
        así que este método puede ser simplificado o eliminado.
        """
        self.ensure_one()
        # En WAHA no hay sincronización de plantillas desde el servidor
        # Las plantillas se crean localmente en Odoo
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Information"),
                'message': _("WAHA does not require template synchronization. "
                           "Create templates directly in Odoo."),
                'type': 'info',
                'sticky': False,
            }
        }

    # ============================================================
    # MÉTODOS DE ENVÍO DE MENSAJES
    # ============================================================

    def _send_waha_message(self, number, message_type='text', **kwargs):
        """
        Método privado para enviar mensajes a través de WAHA
        Similar a _send_whatsapp en whatsapp.account
        
        Args:
            number: Número de teléfono destino
            message_type: 'text', 'image', 'document', etc.
            **kwargs: body, media_id, caption, etc.
        """
        self.ensure_one()
        
        if self.status != 'connected':
            raise UserError(_('WhatsApp account is not connected.'))
        
        try:
            api = WahaApi(self)
            
            # Formatear número a formato WhatsApp
            chat_id = f"{number.replace('+', '')}@c.us"
            
            # Enviar según tipo
            if message_type == 'text':
                result = api.send_text(chat_id, kwargs.get('body', ''))
            elif message_type == 'image':
                result = api.send_image(
                    chat_id,
                    kwargs.get('media_data'),
                    kwargs.get('caption')
                )
            elif message_type == 'document':
                result = api.send_file(
                    chat_id,
                    kwargs.get('media_data'),
                    kwargs.get('filename'),
                    kwargs.get('mimetype')
                )
            else:
                raise UserError(_('Unsupported message type: %s', message_type))
            
            return result
            
        except WahaError as err:
            raise UserError(str(err)) from err

    # ============================================================
    # MÉTODOS AUXILIARES
    # ============================================================

    def _get_api_client(self):
        """Retorna instancia del cliente API"""
        self.ensure_one()
        return WahaApi(self)

    @api.model
    def _cron_check_connection_status(self):
        """
        Cron para verificar estado de conexiones
        Similar al cron de WhatsApp
        """
        accounts = self.search([('status', 'in', ['connected', 'connecting'])])
        for account in accounts:
            try:
                account.action_refresh_status()
            except Exception as e:
                _logger.error(
                    'Error checking WAHA account %s status: %s',
                    account.name, str(e)
                )
```

**Campos equivalentes entre WhatsApp y WAHA**:
| WhatsApp Official | WAHA Adaptation |
|-------------------|-----------------|
| `app_uid` | `session_name` |
| `app_secret` | `api_key` (opcional) |
| `account_uid` | `account_uid` (auto-generado) |
| `phone_uid` | `phone_uid` |
| `token` | *(incluido en API client)* |

### 3.2 waha.message
Registro de mensajes enviados y recibidos, vinculado con mail.message.

```python
class WahaMessage(models.Model):
    _name = 'waha.message'
    _description = 'WhatsApp Message'
    _order = 'create_date desc'
    _rec_name = 'waha_message_id'

    # Relaciones principales
    waha_account_id = fields.Many2one('waha.account', string='WhatsApp Account',
                                      required=True, ondelete='cascade', index=True)
    mail_message_id = fields.Many2one('mail.message', string='Mail Message',
                                      index=True, ondelete='cascade',
                                      help='Mensaje del chatter asociado')
    mobile_number = fields.Char(string='Mobile Number', required=True, index=True,
                                help='Número de teléfono del destinatario')
    mobile_number_formatted = fields.Char(string='Formatted Number', compute='_compute_mobile_formatted')
    
    # Identificadores WAHA
    waha_message_id = fields.Char(string='WhatsApp Message ID', readonly=True, copy=False,
                                  help='ID único del mensaje en WAHA')
    chat_id = fields.Char(string='Chat ID', compute='_compute_chat_id', store=True,
                          help='ID del chat en formato WhatsApp')
    
    # Contenido del mensaje
    body = fields.Html(string='Message Body')
    message_type = fields.Selection([
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('document', 'Document'),
        ('location', 'Location'),
        ('contact', 'Contact'),
        ('template', 'Template')
    ], default='text', required=True, string='Type')
    
    # Archivos adjuntos
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    media_url = fields.Char(string='Media URL', help='URL del archivo multimedia')
    
    # Estado del mensaje
    state = fields.Selection([
        ('outgoing', 'Sending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('received', 'Received'),
        ('error', 'Error'),
        ('cancel', 'Cancelled')
    ], default='outgoing', required=True, readonly=True, copy=False)
    failure_type = fields.Selection([
        ('unknown', 'Unknown'),
        ('network', 'Network Error'),
        ('account', 'Account Issue'),
        ('recipient', 'Recipient Issue')
    ], string='Failure Type', readonly=True)
    failure_reason = fields.Text(string='Failure Reason', readonly=True)
    
    # Metadata
    direction = fields.Selection([
        ('outgoing', 'Outgoing'),
        ('incoming', 'Incoming')
    ], required=True, default='outgoing', string='Direction')
    author_id = fields.Many2one('res.partner', string='Author', index=True)
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now)
    free_text_json = fields.Text(string='Free Text (JSON)', readonly=True,
                                 help='Datos adicionales del webhook en formato JSON')
    company_id = fields.Many2one('res.company', related='waha_account_id.company_id',
                                 store=True, index=True)

    @api.depends('mobile_number')
    def _compute_mobile_formatted(self):
        """Formatea el número de teléfono"""
        for message in self:
            if message.mobile_number:
                # Usar phonenumbers para formatear
                message.mobile_number_formatted = message.mobile_number
            else:
                message.mobile_number_formatted = False

    @api.depends('mobile_number')
    def _compute_chat_id(self):
        """Calcula el chat_id en formato WhatsApp"""
        for message in self:
            if message.mobile_number:
                # Formato: número@c.us (para usuarios individuales)
                clean_number = message.mobile_number.replace('+', '').replace(' ', '')
                message.chat_id = f"{clean_number}@c.us"
            else:
                message.chat_id = False

    def _post_message_in_chatter(self):
        """Publica el mensaje en el chatter del registro relacionado"""
        self.ensure_one()
        if self.mail_message_id:
            return self.mail_message_id
        
        # Buscar el partner asociado
        partner = self.env['res.partner'].search([
            '|', ('phone', '=', self.mobile_number),
            ('mobile', '=', self.mobile_number)
        ], limit=1)
        
        if partner and hasattr(partner, 'message_post'):
            message_vals = {
                'body': self.body,
                'message_type': 'whatsapp',
                'subtype_id': self.env.ref('mail.mt_comment').id,
                'author_id': self.author_id.id if self.author_id else False,
            }
            mail_message = partner.message_post(**message_vals)
            self.mail_message_id = mail_message.id
            return mail_message
        return False
```

**Métodos principales**:
- `action_send()`: Envía el mensaje a través de WAHA
- `action_retry()`: Reintenta el envío de mensajes fallidos
- `_post_message_in_chatter()`: Publica el mensaje en el chatter
- `_process_webhook_data()`: Procesa datos del webhook
- `_update_message_state()`: Actualiza el estado del mensaje

### 3.3 waha.template
Plantillas reutilizables de mensajes WhatsApp.

```python
class WahaTemplate(models.Model):
    _name = 'waha.template'
    _description = 'WhatsApp Message Template'
    _inherit = ['mail.thread']
    _order = 'name'

    # Información básica
    name = fields.Char(string='Template Name', required=True, tracking=True, translate=True)
    waha_account_id = fields.Many2one('waha.account', string='WhatsApp Account',
                                      ondelete='cascade')
    template_name = fields.Char(string='Template Code', help='Código de la plantilla')
    status = fields.Selection([
        ('approved', 'Approved'),
        ('pending', 'Pending'),
        ('rejected', 'Rejected')
    ], default='approved', string='Status')
    
    # Contenido
    body = fields.Html(string='Template Body', translate=True, sanitize=False,
                       help='Usa {{object.field_name}} para variables dinámicas del modelo')
    header_type = fields.Selection([
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document'),
        ('none', 'None')
    ], default='none', string='Header Type')
    header_text = fields.Char(string='Header Text', translate=True)
    header_attachment_ids = fields.Many2many('ir.attachment', string='Header Attachments')
    footer_text = fields.Char(string='Footer Text', translate=True)
    
    # Botones de acción (opcional)
    button_ids = fields.One2many('waha.template.button', 'template_id', string='Buttons')
    
    # Modelo aplicable
    model_id = fields.Many2one('ir.model', string='Applies to',
                               help='Modelo de Odoo al que aplica esta plantilla',
                               ondelete='cascade')
    model = fields.Char(related='model_id.model', string='Model Technical Name', store=True)
    
    # Variables disponibles
    variable_ids = fields.One2many('waha.template.variable', 'template_id', string='Variables')
    
    # Control
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    def _render_template(self, res_ids, engine='qweb'):
        """Renderiza la plantilla con datos del registro"""
        self.ensure_one()
        results = {}
        for res_id in res_ids:
            record = self.env[self.model].browse(res_id)
            # Renderizar usando QWeb o Jinja2
            if engine == 'qweb':
                body = self.env['ir.qweb']._render(
                    self.body,
                    {'object': record}
                )
            else:
                # Usar jinja2
                from jinja2 import Template
                template = Template(self.body)
                body = template.render(object=record)
            results[res_id] = body
        return results

    def action_send_whatsapp(self):
        """Envía mensaje usando esta plantilla"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send WhatsApp',
            'res_model': 'waha.composer',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_template_id': self.id,
                'default_composition_mode': 'mass',
            }
        }


class WahaTemplateButton(models.Model):
    _name = 'waha.template.button'
    _description = 'WhatsApp Template Button'
    _order = 'sequence, id'

    template_id = fields.Many2one('waha.template', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    button_type = fields.Selection([
        ('quick_reply', 'Quick Reply'),
        ('url', 'URL'),
        ('phone', 'Phone Number')
    ], required=True, default='quick_reply')
    text = fields.Char(string='Button Text', required=True, translate=True)
    value = fields.Char(string='Value', help='URL o número de teléfono')


class WahaTemplateVariable(models.Model):
    _name = 'waha.template.variable'
    _description = 'Template Variable'
    _order = 'sequence'

    template_id = fields.Many2one('waha.template', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Variable Name', required=True)
    field_id = fields.Many2one('ir.model.fields', string='Field',
                               domain="[('model_id', '=', parent.model_id)]")
    demo_value = fields.Char(string='Demo Value', help='Valor para vista previa')
```

**Métodos principales**:
- `_render_template(res_ids)`: Renderiza la plantilla con datos del registro
- `action_send_whatsapp()`: Abre el composer con esta plantilla
- `action_preview()`: Vista previa de la plantilla

### 3.4 res.partner (extensión)
Extensión del modelo de contactos para agregar funcionalidades de WhatsApp.

```python
class ResPartner(models.Model):
    _inherit = 'res.partner'

    whatsapp_number = fields.Char(string='WhatsApp Number',
                                   help='Número en formato internacional sin +')
    whatsapp_chat_id = fields.Char(string='WhatsApp Chat ID', 
                                    compute='_compute_whatsapp_chat_id', 
                                    store=True)
    waha_message_ids = fields.One2many('waha.message', 'partner_id', 
                                       string='WhatsApp Messages')
    waha_message_count = fields.Integer(compute='_compute_waha_message_count')

    @api.depends('whatsapp_number')
    def _compute_whatsapp_chat_id(self):
        for partner in self:
            if partner.whatsapp_number:
                # Formato: número@c.us (para usuarios individuales)
                partner.whatsapp_chat_id = f"{partner.whatsapp_number}@c.us"
            else:
                partner.whatsapp_chat_id = False

    def action_send_whatsapp(self):
        """Abre wizard para enviar mensaje de WhatsApp"""
        return {
            'name': 'Send WhatsApp Message',
            'type': 'ir.actions.act_window',
            'res_model': 'send.whatsapp.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.id,
                'default_chat_id': self.whatsapp_chat_id
            }
        }

    def action_view_whatsapp_messages(self):
        """Ver historial de mensajes de WhatsApp"""
        return {
            'name': 'WhatsApp Messages',
            'type': 'ir.actions.act_window',
            'res_model': 'waha.message',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
        }
```

### 3.5 mail.composer.mixin
Mixin para agregar funcionalidad de WhatsApp a modelos con mail.thread.

```python
class MailComposerMixin(models.AbstractModel):
    """Mixin para agregar capacidades de enviar WhatsApp a cualquier modelo"""
    _name = 'mail.composer.mixin'
    _description = 'WhatsApp Composer Mixin'

    # Campos de WhatsApp
    waha_account_id = fields.Many2one('waha.account', string='WhatsApp Account')
    waha_template_id = fields.Many2one('waha.template', string='WhatsApp Template',
                                       domain="[('model', '=', render_model)]")
    
    def _prepare_waha_message_values(self, partners):
        """Prepara valores para crear mensajes de WhatsApp"""
        self.ensure_one()
        messages = []
        
        for partner in partners:
            # Obtener número sanitizado
            mobile = partner._phone_get_sanitized_number('mobile', 'E164')
            if not mobile:
                continue
            
            # Renderizar cuerpo del mensaje
            body = self.body
            if self.waha_template_id:
                body = self.waha_template_id._render_template([partner.id])[partner.id]
            
            message_vals = {
                'waha_account_id': self.waha_account_id.id,
                'mobile_number': mobile,
                'body': body,
                'message_type': 'text',
                'direction': 'outgoing',
                'state': 'outgoing',
            }
            messages.append(message_vals)
        
        return messages
```

### 3.6 mail.thread (extensión)
Extiende mail.thread para agregar botón de WhatsApp en el chatter.

```python
class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _message_get_default_recipients(self):
        """Override para incluir números de WhatsApp"""
        res = super()._message_get_default_recipients()
        
        # Agregar información de WhatsApp si el modelo tiene campo mobile
        for record in self:
            if record.id in res:
                mobile = False
                if hasattr(record, 'mobile'):
                    mobile = record.mobile
                elif hasattr(record, 'partner_id') and record.partner_id.mobile:
                    mobile = record.partner_id.mobile
                
                if mobile:
                    res[record.id]['mobile'] = mobile
        
        return res
```

---

## 4. Configuración y Settings

### 4.1 res.config.settings
Configuración global de WAHA en Settings.

```python
class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Configuración global de WAHA
    waha_server_url = fields.Char(
        string='WAHA Server URL',
        config_parameter='waha_integration.waha_server_url',
        default='http://localhost:3000'
    )
    waha_api_key = fields.Char(
        string='WAHA API Key',
        config_parameter='waha_integration.waha_api_key',
        groups='base.group_system'
    )
    
    # Cuenta por defecto
    waha_default_account_id = fields.Many2one(
        'waha.account',
        string='Default WhatsApp Account',
        config_parameter='waha_integration.default_account_id'
    )
```

---

## 5. Controladores (Webhooks)

### 5.1 Webhook Controller
Endpoint para recibir eventos de WAHA.

```python
# controllers/webhook.py
from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class WahaWebhookController(http.Controller):

    @http.route('/waha/webhook/<string:session_name>', 
                type='json', auth='public', methods=['POST'], csrf=False)
    def waha_webhook(self, session_name, **kwargs):
        """
        Recibe webhooks de WAHA
        URL: https://tu-odoo.com/waha/webhook/default
        """
        try:
            data = json.loads(request.httprequest.data)
            _logger.info(f'Received webhook for session {session_name}: {data}')

            # Buscar la sesión
            session = request.env['waha.session'].sudo().search([
                ('session_name', '=', session_name)
            ], limit=1)

            if not session:
                _logger.warning(f'Session {session_name} not found')
                return {'status': 'error', 'message': 'Session not found'}

            # Procesar el evento según el tipo
            event_type = data.get('event')
            
            if event_type == 'message':
                session._process_incoming_message(data)
            elif event_type == 'message.ack':
                session._process_message_ack(data)
            elif event_type == 'state.change':
                session._process_state_change(data)
            
            return {'status': 'success'}

        except Exception as e:
            _logger.error(f'Error processing webhook: {str(e)}', exc_info=True)
            return {'status': 'error', 'message': str(e)}

    @http.route('/waha/webhook/test', type='http', auth='public', 
                methods=['GET'], csrf=False)
    def test_webhook(self, **kwargs):
        """Endpoint de prueba"""
        return "WAHA Webhook is active"
```

---

## 5. Servicios y Lógica de Negocio

### 5.1 Cliente WAHA API
Clase auxiliar para interactuar con WAHA.

```python
# models/waha_api_client.py
import requests
import logging
import base64
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class WahaApiClient:
    """Cliente para interactuar con WAHA API"""
    
    def __init__(self, base_url, api_key=None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {}
        if api_key:
            self.headers['X-Api-Key'] = api_key

    def _make_request(self, method, endpoint, data=None, files=None):
        """Realiza petición HTTP a WAHA"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.request(
                method=method,
                url=url,
                json=data if data and not files else None,
                files=files,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.RequestException as e:
            _logger.error(f'WAHA API error: {str(e)}')
            raise UserError(f'Error comunicándose con WAHA: {str(e)}')

    # Sesiones
    def start_session(self, session_name):
        """Inicia una sesión"""
        return self._make_request('POST', '/api/sessions', 
                                  data={'name': session_name})

    def get_session_status(self, session_name):
        """Obtiene estado de la sesión"""
        return self._make_request('GET', f'/api/sessions/{session_name}')

    def stop_session(self, session_name):
        """Detiene una sesión"""
        return self._make_request('DELETE', f'/api/sessions/{session_name}')

    def get_qr_code(self, session_name):
        """Obtiene el código QR"""
        return self._make_request('GET', f'/api/sessions/{session_name}/qr')

    # Mensajes
    def send_text(self, session_name, chat_id, text):
        """Envía mensaje de texto"""
        return self._make_request('POST', f'/api/sendText', data={
            'session': session_name,
            'chatId': chat_id,
            'text': text
        })

    def send_image(self, session_name, chat_id, image_data, caption=None):
        """Envía imagen"""
        data = {
            'session': session_name,
            'chatId': chat_id,
            'file': {
                'mimetype': 'image/jpeg',
                'data': image_data  # Base64
            }
        }
        if caption:
            data['caption'] = caption
        return self._make_request('POST', '/api/sendImage', data=data)

    def send_file(self, session_name, chat_id, file_data, filename, mimetype):
        """Envía archivo"""
        return self._make_request('POST', '/api/sendFile', data={
            'session': session_name,
            'chatId': chat_id,
            'file': {
                'filename': filename,
                'mimetype': mimetype,
                'data': file_data  # Base64
            }
        })

    # Webhooks
    def set_webhook(self, session_name, webhook_url):
        """Configura webhook"""
        return self._make_request('POST', f'/api/sessions/{session_name}/webhook', 
                                  data={'url': webhook_url})
```

### 5.2 Integración en waha.session

```python
# En models/waha_session.py
from .waha_api_client import WahaApiClient

class WahaSession(models.Model):
    # ... (campos definidos anteriormente)

    def _get_api_client(self):
        """Retorna instancia del cliente API"""
        self.ensure_one()
        return WahaApiClient(self.waha_url, self.api_key)

    def action_start_session(self):
        """Inicia la sesión en WAHA"""
        for session in self:
            try:
                client = session._get_api_client()
                result = client.start_session(session.session_name)
                session.write({'state': 'connecting'})
                session.message_post(body='Session started successfully')
                return True
            except Exception as e:
                session.write({'state': 'error'})
                raise UserError(f'Error starting session: {str(e)}')

    def action_get_qr(self):
        """Obtiene y muestra el código QR"""
        self.ensure_one()
        try:
            client = self._get_api_client()
            qr_data = client.get_qr_code(self.session_name)
            # qr_data contiene la imagen en base64
            self.qr_code = qr_data.get('qr')
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'waha.session',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'current',
            }
        except Exception as e:
            raise UserError(f'Error getting QR: {str(e)}')

    def send_message(self, chat_id, text=None, attachment=None, message_type='text'):
        """Envía un mensaje a través de WAHA"""
        self.ensure_one()
        client = self._get_api_client()
        
        # Crear registro de mensaje
        message = self.env['waha.message'].create({
            'session_id': self.id,
            'chat_id': chat_id,
            'message_type': message_type,
            'body': text,
            'direction': 'outbound',
            'state': 'sending'
        })

        try:
            if message_type == 'text':
                result = client.send_text(self.session_name, chat_id, text)
            elif message_type == 'image' and attachment:
                result = client.send_image(
                    self.session_name, 
                    chat_id, 
                    base64.b64encode(attachment).decode(), 
                    text
                )
            
            message.write({
                'state': 'sent',
                'message_id': result.get('id')
            })
            return message
        except Exception as e:
            message.write({
                'state': 'failed',
                'error_message': str(e)
            })
            raise
```

---

## 6. Wizard de Envío

### 6.1 send.whatsapp.wizard

```python
# wizard/send_whatsapp_wizard.py
from odoo import models, fields, api
from odoo.exceptions import UserError

class SendWhatsappWizard(models.TransientModel):
    _name = 'send.whatsapp.wizard'
    _description = 'Send WhatsApp Message Wizard'

    session_id = fields.Many2one('waha.session', string='Session', 
                                 required=True,
                                 domain=[('state', '=', 'connected')])
    partner_id = fields.Many2one('res.partner', string='Contact')
    chat_id = fields.Char(string='Chat ID', required=True)
    template_id = fields.Many2one('waha.template', string='Template')
    message_type = fields.Selection([
        ('text', 'Text'),
        ('image', 'Image'),
        ('document', 'Document')
    ], default='text', required=True)
    body = fields.Text(string='Message', required=True)
    attachment_id = fields.Many2one('ir.attachment', string='Attachment')

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id and self.partner_id.whatsapp_chat_id:
            self.chat_id = self.partner_id.whatsapp_chat_id

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if self.template_id:
            # Renderizar template si es necesario
            self.body = self.template_id.body
            self.message_type = self.template_id.message_type

    def action_send(self):
        """Envía el mensaje de WhatsApp"""
        self.ensure_one()
        
        if not self.session_id:
            raise UserError('Please select a WAHA session')
        
        if self.session_id.state != 'connected':
            raise UserError('Session is not connected')

        try:
            attachment_data = None
            if self.attachment_id:
                attachment_data = self.attachment_id.datas

            message = self.session_id.send_message(
                chat_id=self.chat_id,
                text=self.body,
                attachment=attachment_data,
                message_type=self.message_type
            )

            # Vincular con el contacto si existe
            if self.partner_id:
                message.partner_id = self.partner_id

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': 'WhatsApp message sent successfully',
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            raise UserError(f'Error sending message: {str(e)}')
```

---

## 7. Vistas XML

### 7.1 Vistas de Sesión

```xml
<!-- views/waha_session_views.xml -->
<odoo>
    <record id="view_waha_session_form" model="ir.ui.view">
        <field name="name">waha.session.form</field>
        <field name="model">waha.session</field>
        <field name="arch" type="xml">
            <form string="WAHA Session">
                <header>
                    <button name="action_start_session" string="Start Session" 
                            type="object" class="oe_highlight"
                            attrs="{'invisible': [('state', '!=', 'draft')]}"/>
                    <button name="action_get_qr" string="Get QR Code" 
                            type="object" class="oe_highlight"
                            attrs="{'invisible': [('state', '!=', 'connecting')]}"/>
                    <button name="action_check_status" string="Check Status" 
                            type="object"/>
                    <button name="action_stop_session" string="Stop Session" 
                            type="object" class="btn-danger"
                            attrs="{'invisible': [('state', 'not in', ['connected', 'connecting'])]}"/>
                    <field name="state" widget="statusbar" 
                           statusbar_visible="draft,connecting,connected"/>
                </header>
                <sheet>
                    <div class="oe_button_box" name="button_box">
                        <button name="action_view_messages" type="object" 
                                class="oe_stat_button" icon="fa-comments">
                            <field name="message_count" widget="statbutton" 
                                   string="Messages"/>
                        </button>
                    </div>
                    <field name="qr_code" widget="image" 
                           attrs="{'invisible': [('qr_code', '=', False)]}"
                           class="oe_avatar"/>
                    <group>
                        <group>
                            <field name="name"/>
                            <field name="session_name"/>
                            <field name="phone_number"/>
                            <field name="active"/>
                        </group>
                        <group>
                            <field name="waha_url"/>
                            <field name="api_key" password="True"/>
                            <field name="webhook_url" readonly="1"/>
                            <field name="last_sync" readonly="1"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Configuration">
                            <group>
                                <field name="company_id" groups="base.group_multi_company"/>
                            </group>
                        </page>
                    </notebook>
                </sheet>
                <div class="oe_chatter">
                    <field name="message_follower_ids"/>
                    <field name="activity_ids"/>
                    <field name="message_ids"/>
                </div>
            </form>
        </field>
    </record>

    <record id="view_waha_session_tree" model="ir.ui.view">
        <field name="name">waha.session.tree</field>
        <field name="model">waha.session</field>
        <field name="arch" type="xml">
            <tree string="WAHA Sessions">
                <field name="name"/>
                <field name="session_name"/>
                <field name="phone_number"/>
                <field name="state" widget="badge" 
                       decoration-success="state=='connected'"
                       decoration-info="state=='connecting'"
                       decoration-danger="state=='error'"/>
                <field name="last_sync"/>
                <field name="company_id" groups="base.group_multi_company"/>
            </tree>
        </field>
    </record>
</odoo>
```

### 7.2 Vistas de Mensajes

```xml
<!-- views/waha_message_views.xml -->
<odoo>
    <record id="view_waha_message_form" model="ir.ui.view">
        <field name="name">waha.message.form</field>
        <field name="model">waha.message</field>
        <field name="arch" type="xml">
            <form string="WhatsApp Message">
                <header>
                    <button name="action_send" string="Send" type="object" 
                            class="oe_highlight"
                            attrs="{'invisible': [('state', '!=', 'draft')]}"/>
                    <button name="action_retry" string="Retry" type="object"
                            attrs="{'invisible': [('state', '!=', 'failed')]}"/>
                    <field name="state" widget="statusbar"/>
                </header>
                <sheet>
                    <group>
                        <group>
                            <field name="session_id"/>
                            <field name="partner_id"/>
                            <field name="chat_id"/>
                            <field name="direction"/>
                        </group>
                        <group>
                            <field name="message_type"/>
                            <field name="message_id"/>
                            <field name="timestamp"/>
                        </group>
                    </group>
                    <group>
                        <field name="body" widget="html"/>
                        <field name="media_url" 
                               attrs="{'invisible': [('message_type', '=', 'text')]}"/>
                        <field name="attachment" filename="attachment_name"
                               attrs="{'invisible': [('attachment', '=', False)]}"/>
                        <field name="attachment_name" invisible="1"/>
                    </group>
                    <group attrs="{'invisible': [('state', '!=', 'failed')]}">
                        <field name="error_message"/>
                    </group>
                    <notebook>
                        <page string="Webhook Data" 
                              attrs="{'invisible': [('webhook_data', '=', False)]}">
                            <field name="webhook_data" widget="ace" 
                                   options="{'mode': 'json'}"/>
                        </page>
                    </notebook>
                </sheet>
            </form>
        </field>
    </record>

    <record id="view_waha_message_tree" model="ir.ui.view">
        <field name="name">waha.message.tree</field>
        <field name="model">waha.message</field>
        <field name="arch" type="xml">
            <tree string="WhatsApp Messages">
                <field name="timestamp"/>
                <field name="session_id"/>
                <field name="partner_id"/>
                <field name="chat_id"/>
                <field name="direction" widget="badge"/>
                <field name="message_type"/>
                <field name="body"/>
                <field name="state" widget="badge" 
                       decoration-success="state=='sent'"
                       decoration-danger="state=='failed'"/>
            </tree>
        </field>
    </record>
</odoo>
```

### 7.3 Menús

```xml
<!-- views/menu_views.xml -->
<odoo>
    <menuitem id="menu_waha_root" name="WhatsApp" sequence="50" 
              web_icon="waha_integration,static/description/icon.png"/>

    <menuitem id="menu_waha_sessions" name="Sessions" 
              parent="menu_waha_root" sequence="10"
              action="action_waha_session"/>

    <menuitem id="menu_waha_messages" name="Messages" 
              parent="menu_waha_root" sequence="20"
              action="action_waha_message"/>

    <menuitem id="menu_waha_templates" name="Templates" 
              parent="menu_waha_root" sequence="30"
              action="action_waha_template"/>

    <menuitem id="menu_waha_config" name="Configuration" 
              parent="menu_waha_root" sequence="100"/>
</odoo>
```

---

## 8. Seguridad

### 8.1 Grupos de Acceso

```xml
<!-- security/waha_security.xml -->
<odoo>
    <record id="group_waha_user" model="res.groups">
        <field name="name">WAHA User</field>
        <field name="category_id" ref="base.module_category_marketing"/>
        <field name="implied_ids" eval="[(4, ref('base.group_user'))]"/>
    </record>

    <record id="group_waha_manager" model="res.groups">
        <field name="name">WAHA Manager</field>
        <field name="category_id" ref="base.module_category_marketing"/>
        <field name="implied_ids" eval="[(4, ref('group_waha_user'))]"/>
    </record>
</odoo>
```

### 8.2 Reglas de Acceso

```csv
# security/ir.model.access.csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_waha_session_user,waha.session.user,model_waha_session,group_waha_user,1,0,0,0
access_waha_session_manager,waha.session.manager,model_waha_session,group_waha_manager,1,1,1,1
access_waha_message_user,waha.message.user,model_waha_message,group_waha_user,1,1,1,0
access_waha_message_manager,waha.message.manager,model_waha_message,group_waha_manager,1,1,1,1
access_waha_template_user,waha.template.user,model_waha_template,group_waha_user,1,0,0,0
access_waha_template_manager,waha.template.manager,model_waha_template,group_waha_manager,1,1,1,1
```

---

## 9. Instalación y Configuración

### 9.1 Requisitos Previos

1. **Instalar WAHA**:
```bash
# Descargar imagen Docker
docker pull devlikeapro/waha

# Ejecutar WAHA
docker run -d \
  --name waha \
  -p 3000:3000 \
  -v waha_data:/app/sessions \
  devlikeapro/waha

# Verificar que esté corriendo
curl http://localhost:3000/
```

2. **Instalar el módulo en Odoo**:
```bash
# Copiar módulo a addons
cp -r waha_integration /path/to/odoo/addons/

# Actualizar lista de aplicaciones
# En Odoo: Apps > Update Apps List

# Instalar módulo
# En Odoo: Apps > Search "WAHA" > Install
```

### 9.2 Configuración Inicial

1. **Crear una Sesión WAHA**:
   - Ir a WhatsApp > Sessions > Create
   - Nombre: "Principal"
   - WAHA URL: `http://localhost:3000` (o tu URL)
   - Session Name: `default`
   - Guardar

2. **Iniciar Sesión**:
   - Hacer clic en "Start Session"
   - Hacer clic en "Get QR Code"
   - Escanear el QR con WhatsApp en el móvil
   - Esperar a que el estado cambie a "Connected"

3. **Configurar Webhook**:
   - El webhook se configura automáticamente
   - URL: `https://tu-odoo.com/waha/webhook/default`
   - Asegurar que el servidor sea accesible públicamente

### 9.3 Configurar Contactos

1. En el formulario de contacto, agregar número de WhatsApp:
   - Campo: "WhatsApp Number"
   - Formato: número sin `+` (ej: `12132132130`)

2. El campo `whatsapp_chat_id` se calcula automáticamente

---

## 10. Casos de Uso

### 10.1 Enviar Mensaje desde Contacto

```python
# Desde un contacto
partner = self.env['res.partner'].browse(partner_id)
partner.action_send_whatsapp()
# Se abre wizard para enviar mensaje
```

### 10.2 Envío Automático desde Ventas

```python
# Extender sale.order
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        res = super().action_confirm()
        # Enviar mensaje de WhatsApp al confirmar venta
        if self.partner_id.whatsapp_chat_id:
            session = self.env['waha.session'].search([
                ('state', '=', 'connected')
            ], limit=1)
            
            if session:
                message = f"""
                Hola {self.partner_id.name},
                
                Tu pedido {self.name} ha sido confirmado.
                Total: {self.amount_total} {self.currency_id.symbol}
                
                Gracias por tu compra!
                """
                session.send_message(
                    chat_id=self.partner_id.whatsapp_chat_id,
                    text=message
                )
        return res
```

### 10.3 Recibir y Procesar Mensajes

```python
# En waha_session.py
def _process_incoming_message(self, webhook_data):
    """Procesa mensaje entrante desde webhook"""
    payload = webhook_data.get('payload', {})
    
    # Extraer datos del mensaje
    chat_id = payload.get('from')
    text = payload.get('body', '')
    message_id = payload.get('id')
    
    # Buscar o crear contacto
    partner = self._find_or_create_partner(chat_id, payload)
    
    # Crear registro de mensaje
    message = self.env['waha.message'].create({
        'session_id': self.id,
        'partner_id': partner.id if partner else False,
        'chat_id': chat_id,
        'message_id': message_id,
        'direction': 'inbound',
        'message_type': 'text',
        'body': text,
        'state': 'sent',
        'webhook_data': json.dumps(webhook_data),
    })
    
    # Procesamiento adicional (respuestas automáticas, crear leads, etc.)
    self._process_message_logic(message)
    
    return message

def _find_or_create_partner(self, chat_id, payload):
    """Busca o crea contacto desde número de WhatsApp"""
    # Extraer número del chat_id (formato: 1234567890@c.us)
    phone = chat_id.split('@')[0]
    
    partner = self.env['res.partner'].search([
        ('whatsapp_number', '=', phone)
    ], limit=1)
    
    if not partner:
        # Crear nuevo contacto
        name = payload.get('notifyName') or f'WhatsApp {phone}'
        partner = self.env['res.partner'].create({
            'name': name,
            'whatsapp_number': phone,
            'phone': phone,
        })
    
    return partner
```

---

## 11. Pruebas y Validación

### 11.1 Pruebas Unitarias

```python
# tests/test_waha_session.py
from odoo.tests import TransactionCase
from odoo.exceptions import UserError

class TestWahaSession(TransactionCase):

    def setUp(self):
        super().setUp()
        self.session = self.env['waha.session'].create({
            'name': 'Test Session',
            'waha_url': 'http://localhost:3000',
            'session_name': 'test',
        })

    def test_session_creation(self):
        """Verifica creación de sesión"""
        self.assertEqual(self.session.state, 'draft')
        self.assertTrue(self.session.webhook_url)

    def test_chat_id_computation(self):
        """Verifica cálculo de chat_id"""
        partner = self.env['res.partner'].create({
            'name': 'Test Contact',
            'whatsapp_number': '1234567890'
        })
        self.assertEqual(partner.whatsapp_chat_id, '1234567890@c.us')

    def test_send_message(self):
        """Prueba envío de mensaje (mock)"""
        # Implementar con mock de la API
        pass
```

### 11.2 Checklist de Validación

- [ ] Sesión WAHA se inicia correctamente
- [ ] QR Code se muestra y es escaneable
- [ ] Estado de sesión se actualiza a "Connected"
- [ ] Envío de mensaje de texto funciona
- [ ] Envío de imagen funciona
- [ ] Webhook recibe mensajes entrantes
- [ ] Mensajes se asocian correctamente con contactos
- [ ] Plantillas se renderizan correctamente
- [ ] Permisos de seguridad funcionan
- [ ] Multi-sesión funciona correctamente

---

## 12. Mantenimiento y Extensiones

### 12.1 Logs y Debugging

```python
# Activar modo debug en WAHA
# Variable de entorno: DEBUG=1

# En Odoo, verificar logs
import logging
_logger = logging.getLogger(__name__)

# Nivel de log para el módulo
_logger.setLevel(logging.DEBUG)
```

### 12.2 Posibles Extensiones

1. **Integración con CRM**:
   - Crear leads automáticamente desde mensajes
   - Asociar conversaciones a oportunidades

2. **Chatbot/Respuestas Automáticas**:
   - Definir keywords y respuestas
   - Integración con IA (ChatGPT, etc.)

3. **Campañas Masivas**:
   - Envío de mensajes a múltiples contactos
   - Seguimiento de métricas

4. **WhatsApp Business API**:
   - Soporte para plantillas oficiales
   - Integración con catálogos

5. **Reportes y Analytics**:
   - Dashboard de mensajes
   - Estadísticas de engagement

### 12.3 Actualización de WAHA

```bash
# Actualizar imagen Docker
docker pull devlikeapro/waha

# Recrear contenedor
docker stop waha
docker rm waha
docker run -d --name waha -p 3000:3000 -v waha_data:/app/sessions devlikeapro/waha
```

---

## 13. Troubleshooting

### 13.1 Problemas Comunes

| Problema | Causa | Solución |
|----------|-------|----------|
| QR no se muestra | WAHA no está corriendo | Verificar `docker ps` y reiniciar WAHA |
| Mensajes no se envían | Sesión desconectada | Reconectar sesión, verificar estado |
| Webhook no recibe | URL no accesible | Usar ngrok o servidor público |
| Error 401 en API | API Key incorrecta | Verificar configuración de API Key |
| Sesión se desconecta | Límite de dispositivos | Desconectar otros dispositivos |

### 13.2 Verificación del Sistema

```bash
# Verificar WAHA está corriendo
curl http://localhost:3000/

# Verificar sesiones activas
curl http://localhost:3000/api/sessions

# Ver logs de WAHA
docker logs waha

# En Odoo, verificar configuración
# Settings > Technical > System Parameters
```

---

## 14. Referencias y Documentación

### 14.1 Enlaces Útiles

- **WAHA Documentación**: https://waha.devlike.pro/docs/
- **WAHA GitHub**: https://github.com/devlikeapro/waha
- **WAHA Swagger**: http://localhost:3000/swagger
- **Odoo v18 Documentation**: https://www.odoo.com/documentation/18.0/
- **WhatsApp API Limits**: https://developers.facebook.com/docs/whatsapp/

### 14.2 API Endpoints Principales

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/sessions` | POST | Crear sesión |
| `/api/sessions/{name}` | GET | Estado de sesión |
| `/api/sessions/{name}/qr` | GET | Obtener QR |
| `/api/sendText` | POST | Enviar texto |
| `/api/sendImage` | POST | Enviar imagen |
| `/api/sendFile` | POST | Enviar archivo |
| `/api/sendLocation` | POST | Enviar ubicación |
| `/api/contacts` | GET | Listar contactos |
| `/api/chats` | GET | Listar chats |
| `/api/groups` | POST | Crear grupo |

---

## 15. Anexos

### 15.1 Manifest del Módulo

```python
# __manifest__.py
{
    'name': 'WAHA WhatsApp Integration',
    'version': '18.0.1.0.0',
    'category': 'Marketing',
    'summary': 'Integrate WhatsApp with Odoo using WAHA API',
    'description': """
        WAHA WhatsApp Integration
        =========================
        
        This module integrates Odoo v18 with WAHA (WhatsApp HTTP API)
        
        Features:
        ---------
        * Send and receive WhatsApp messages
        * Multiple WhatsApp sessions support
        * Message templates
        * Webhook integration
        * Partner WhatsApp integration
        * Message history and logs
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'contacts',
    ],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/waha_security.xml',
        'security/ir.model.access.csv',
        'data/waha_data.xml',
        'views/waha_session_views.xml',
        'views/waha_message_views.xml',
        'views/waha_template_views.xml',
        'views/res_partner_views.xml',
        'views/menu_views.xml',
        'wizard/send_whatsapp_wizard_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/banner.png'],
    'price': 0.00,
    'currency': 'USD',
}
```

### 15.2 Estructura de Webhook de WAHA

```json
{
  "event": "message",
  "session": "default",
  "payload": {
    "id": "true_1234567890@c.us_BAE5F5E5F5E5F5E5",
    "timestamp": 1234567890,
    "from": "1234567890@c.us",
    "body": "Hello from WhatsApp!",
    "hasMedia": false,
    "ack": 1,
    "fromMe": false,
    "notifyName": "John Doe"
  }
}
```

### 15.3 Ejemplo de Respuesta API

```json
// POST /api/sendText Response
{
  "id": "true_1234567890@c.us_BAE5F5E5F5E5F5E5",
  "timestamp": 1234567890,
  "status": "sent"
}
```

---

## 16. Conclusiones

Este documento técnico proporciona una guía completa para desarrollar un módulo de integración entre Odoo v18 y WAHA (WhatsApp HTTP API). 

**Beneficios clave**:
- ✅ Comunicación directa con clientes vía WhatsApp
- ✅ Automatización de notificaciones
- ✅ Centralización de conversaciones
- ✅ Historial de mensajes
- ✅ Solución auto-hospedada y privada

**Próximos pasos**:
1. Implementar los modelos base
2. Configurar integración con WAHA API
3. Desarrollar controladores de webhook
4. Crear vistas y wizards
5. Implementar casos de uso específicos
6. Realizar pruebas exhaustivas
7. Desplegar en producción

---

**Versión del Documento**: 1.0  
**Fecha**: Diciembre 2024  
**Autor**: Equipo de Desarrollo  
**Estado**: Borrador Técnico
