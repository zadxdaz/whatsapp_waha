# Ejemplos de Uso - WAHA Module

## 1. Envío de Mensaje Simple desde Python

```python
# En la consola de Odoo o en un método personalizado
self = env['res.partner'].browse(1)  # Partner ID 1

# Abrir compositor
self.action_send_whatsapp_message()

# O enviar directamente (código personalizado)
account = env['waha.account'].search([('status', '=', 'connected')], limit=1)
if account:
    message = env['waha.message'].create({
        'wa_account_id': account.id,
        'mobile_number': '+5215512345678',
        'body': '<p>Hola, este es un mensaje de prueba</p>',
        'message_type': 'outbound',
    })
    message.action_send()
```

## 2. Uso de Plantillas

```python
# Crear plantilla
template = env['waha.template'].create({
    'name': 'Confirmación de Pedido',
    'wa_account_id': account.id,
    'body': '''
        <p>Hola {{nombre}},</p>
        <p>Tu pedido #{{numero_pedido}} ha sido confirmado.</p>
        <p>Total: ${{total}}</p>
        <p>¡Gracias por tu compra!</p>
    ''',
    'status': 'approved',
})

# Crear variables
env['waha.template.variable'].create([
    {
        'template_id': template.id,
        'name': 'nombre',
        'field_name': 'name',
        'field_type': 'char',
    },
    {
        'template_id': template.id,
        'name': 'numero_pedido',
        'field_name': 'name',
        'field_type': 'char',
    },
    {
        'template_id': template.id,
        'name': 'total',
        'field_name': 'amount_total',
        'field_type': 'float',
    },
])

# Usar plantilla con sale.order
order = env['sale.order'].browse(1)
body = template._get_formatted_body(order)

message = env['waha.message'].create({
    'wa_account_id': account.id,
    'mobile_number': order.partner_id.mobile,
    'body': body,
    'wa_template_id': template.id,
    'message_type': 'outbound',
})
message.action_send()
```

## 3. Envío Masivo (Server Action)

```python
# Crear Server Action para envío masivo
# Settings → Technical → Server Actions → Create

# Nombre: Send WhatsApp to Selected Partners
# Modelo: res.partner
# Action To Do: Execute Python Code

# Python Code:
for partner in records:
    if not partner.mobile:
        continue
    
    account = env['waha.account'].search([
        ('status', '=', 'connected')
    ], limit=1)
    
    if not account:
        continue
    
    template = env.ref('waha.template_welcome')  # O tu plantilla
    body = template._get_formatted_body(partner)
    
    env['waha.message'].create({
        'wa_account_id': account.id,
        'mobile_number': partner.mobile,
        'body': body,
        'wa_template_id': template.id,
        'message_type': 'outbound',
    }).action_send()

# Ahora puedes seleccionar múltiples partners y ejecutar la acción
```

## 4. Automatización con Automated Actions

```python
# Settings → Technical → Automated Actions → Create

# Nombre: WhatsApp al Confirmar Pedido
# Modelo: sale.order
# Trigger: On Update
# Before Update Domain: [('state', '!=', 'sale')]
# Apply on: [('state', '=', 'sale')]

# Python Code:
account = env['waha.account'].search([('status', '=', 'connected')], limit=1)
template = env.ref('waha.template_order_confirmation')

if account and template and record.partner_id.mobile:
    body = template._get_formatted_body(record)
    env['waha.message'].create({
        'wa_account_id': account.id,
        'mobile_number': record.partner_id.mobile,
        'body': body,
        'wa_template_id': template.id,
        'message_type': 'outbound',
    }).action_send()
```

## 5. Webhook Testing

```bash
# Test incoming message webhook
curl -X POST http://localhost:8069/waha/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: tu_token_de_verificacion" \
  -d '{
    "event": "message",
    "session": "default",
    "payload": {
      "id": "true_1234567890@c.us_ABCDEF123456",
      "timestamp": 1234567890,
      "from": "5215512345678@c.us",
      "fromMe": false,
      "body": "Hola, necesito ayuda",
      "hasMedia": false,
      "ack": 0
    }
  }'

# Test message acknowledgment
curl -X POST http://localhost:8069/waha/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: tu_token_de_verificacion" \
  -d '{
    "event": "message.ack",
    "session": "default",
    "payload": {
      "id": "true_1234567890@c.us_ABCDEF123456",
      "ack": 3
    }
  }'

# Test session status
curl -X POST http://localhost:8069/waha/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: tu_token_de_verificacion" \
  -d '{
    "event": "session.status",
    "session": "default",
    "payload": {
      "status": "WORKING"
    }
  }'
```

## 6. Envío de Archivos

```python
# Enviar imagen
account = env['waha.account'].search([('status', '=', 'connected')], limit=1)

# Crear attachment
attachment = env['ir.attachment'].create({
    'name': 'promocion.jpg',
    'type': 'binary',
    'datas': base64_encoded_image,
    'mimetype': 'image/jpeg',
})

# Enviar con WAHA API
from odoo.addons.waha.tools.waha_api import WahaAPI

api = WahaAPI(account.waha_url, account.api_key)
result = api.send_image(
    session=account.session_name,
    chatId='5215512345678@c.us',
    file_url='http://tu-servidor/web/image/' + str(attachment.id),
    caption='¡Nueva promoción!'
)

# Guardar mensaje
message = env['waha.message'].create({
    'wa_account_id': account.id,
    'mobile_number': '+5215512345678',
    'body': '¡Nueva promoción! [Imagen adjunta]',
    'message_type': 'outbound',
    'state': 'sent',
    'msg_uid': result.get('id'),
})
```

## 7. Integración con Mail Thread

```python
# Cualquier modelo que herede mail.thread puede enviar WhatsApp

# Ejemplo en sale.order
class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    def action_confirm(self):
        res = super().action_confirm()
        # Enviar WhatsApp al confirmar
        self._send_whatsapp_confirmation()
        return res
    
    def _send_whatsapp_confirmation(self):
        template = self.env.ref('waha.template_order_confirmation')
        self._message_send_whatsapp(
            template_id=template.id,
            numbers=[self.partner_id.mobile] if self.partner_id.mobile else []
        )
```

## 8. Búsqueda y Filtrado de Mensajes

```python
# Buscar mensajes de un número específico
messages = env['waha.message'].search([
    ('mobile_number', '=', '+5215512345678')
])

# Mensajes no leídos
unread = env['waha.message'].search([
    ('message_type', '=', 'inbound'),
    ('state', '!=', 'read')
])

# Mensajes con error
errors = env['waha.message'].search([
    ('state', '=', 'error')
])

# Mensajes de hoy
from datetime import datetime, timedelta
today = datetime.now().replace(hour=0, minute=0, second=0)
today_messages = env['waha.message'].search([
    ('create_date', '>=', today)
])

# Estadísticas
total_sent = env['waha.message'].search_count([
    ('message_type', '=', 'outbound'),
    ('state', 'in', ['sent', 'delivered', 'read'])
])
```

## 9. Crear Plantilla con Botones

```python
template = env['waha.template'].create({
    'name': 'Menu Principal',
    'wa_account_id': account.id,
    'body': '<p>Bienvenido a nuestro servicio. ¿Qué necesitas?</p>',
    'status': 'approved',
})

# Agregar botones
buttons = [
    {
        'template_id': template.id,
        'sequence': 1,
        'button_type': 'quick_reply',
        'name': 'Ver Productos',
        'payload': 'productos',
    },
    {
        'template_id': template.id,
        'sequence': 2,
        'button_type': 'quick_reply',
        'name': 'Hablar con Ventas',
        'payload': 'ventas',
    },
    {
        'template_id': template.id,
        'sequence': 3,
        'button_type': 'url',
        'name': 'Visitar Web',
        'url': 'https://mi-sitio.com',
        'url_type': 'static',
    },
]

env['waha.template.button'].create(buttons)
```

## 10. Monitoreo y Logs

```python
# Ver logs de WAHA
import subprocess
subprocess.run(['docker', 'logs', '-f', 'waha'])

# En Odoo, ver logs del webhook
# Settings → Technical → Logging

# Programáticamente
import logging
_logger = logging.getLogger(__name__)

_logger.info('WhatsApp message sent: %s', message.id)
_logger.error('Failed to send WhatsApp: %s', error)

# Verificar estado de cuentas
accounts = env['waha.account'].search([])
for account in accounts:
    account.action_refresh_status()
    print(f"{account.name}: {account.status}")
```

## 11. Multi-Account Usage

```python
# Configurar múltiples cuentas
account_support = env['waha.account'].create({
    'name': 'Soporte Técnico',
    'waha_url': 'http://localhost:3000',
    'session_name': 'support',
})

account_sales = env['waha.account'].create({
    'name': 'Ventas',
    'waha_url': 'http://localhost:3000',
    'session_name': 'sales',
})

# Enviar desde cuenta específica
def send_from_support(number, message):
    return env['waha.message'].create({
        'wa_account_id': account_support.id,
        'mobile_number': number,
        'body': message,
        'message_type': 'outbound',
    }).action_send()

def send_from_sales(number, message):
    return env['waha.message'].create({
        'wa_account_id': account_sales.id,
        'mobile_number': number,
        'body': message,
        'message_type': 'outbound',
    }).action_send()
```

## 12. Reportes y Estadísticas

```python
# Crear reporte de mensajería
from datetime import datetime, timedelta

def get_messaging_stats(days=30):
    start_date = datetime.now() - timedelta(days=days)
    
    stats = {
        'total_sent': env['waha.message'].search_count([
            ('create_date', '>=', start_date),
            ('message_type', '=', 'outbound'),
        ]),
        'total_received': env['waha.message'].search_count([
            ('create_date', '>=', start_date),
            ('message_type', '=', 'inbound'),
        ]),
        'delivery_rate': 0,
        'read_rate': 0,
    }
    
    sent = env['waha.message'].search([
        ('create_date', '>=', start_date),
        ('message_type', '=', 'outbound'),
    ])
    
    if sent:
        delivered = sent.filtered(lambda m: m.state in ['delivered', 'read'])
        read = sent.filtered(lambda m: m.state == 'read')
        
        stats['delivery_rate'] = (len(delivered) / len(sent)) * 100
        stats['read_rate'] = (len(read) / len(sent)) * 100
    
    return stats

# Uso
stats = get_messaging_stats(30)
print(f"Mensajes enviados: {stats['total_sent']}")
print(f"Mensajes recibidos: {stats['total_received']}")
print(f"Tasa de entrega: {stats['delivery_rate']:.2f}%")
print(f"Tasa de lectura: {stats['read_rate']:.2f}%")
```

## Notas Adicionales

### Formato de Números
Siempre usa formato E.164 para números telefónicos:
- ✅ Correcto: `+5215512345678`
- ❌ Incorrecto: `5512345678`, `55 1234 5678`, `(55) 1234-5678`

### Límites de WAHA
- Número máximo de sesiones: Depende de tu plan
- Tamaño máximo de archivo: ~100MB
- Rate limiting: Según configuración de WAHA

### Mejores Prácticas
1. Siempre verificar que la cuenta esté conectada antes de enviar
2. Validar números telefónicos antes de crear mensajes
3. Usar plantillas para mensajes frecuentes
4. Implementar manejo de errores robusto
5. Monitorear logs regularmente
6. Hacer backup de sesiones WAHA

### Debugging
```python
# Habilitar modo debug en cliente API
from odoo.addons.waha.tools.waha_api import WahaAPI
api = WahaAPI(url, api_key, debug=True)

# Ver detalles de mensaje
message = env['waha.message'].browse(1)
print(message.free_text_json)  # JSON completo del webhook
```
