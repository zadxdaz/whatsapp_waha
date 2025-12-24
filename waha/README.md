# WAHA Messaging - Odoo WhatsApp Integration

Integración de WhatsApp para Odoo v18 usando WAHA (WhatsApp HTTP API).

## Características

- ✅ Envío y recepción de mensajes de WhatsApp
- ✅ Autenticación con código QR
- ✅ Soporte multi-cuenta
- ✅ Plantillas de mensajes con variables
- ✅ Webhooks para sincronización en tiempo real
- ✅ Seguimiento de estado de mensajes (enviado, entregado, leído)
- ✅ Integración con contactos y chatter
- ✅ Soporte para archivos adjuntos

## Requisitos

### Servidor WAHA

Instalar WAHA con Docker:

```bash
docker run -d \
  --name waha \
  -p 3000:3000 \
  -e WHATSAPP_HOOK_URL=http://your-odoo-server/waha/webhook \
  -e WHATSAPP_HOOK_EVENTS=message,message.ack,session.status \
  devlikeapro/waha
```

### Dependencias Python

```bash
pip install phonenumbers requests
```

## Instalación

1. Copiar módulo a directorio de addons de Odoo
2. Actualizar lista de aplicaciones
3. Instalar "WAHA Messaging"

## Configuración

### 1. Crear Cuenta de WhatsApp

**WhatsApp → Configuración → Cuentas → Crear**

- **WAHA URL**: http://localhost:3000
- **Nombre de Sesión**: default
- **API Key**: (si está habilitado en WAHA)
- **Token de Verificación Webhook**: token aleatorio

### 2. Conectar WhatsApp

1. Clic en botón "Conectar"
2. Clic en "Obtener código QR"
3. Escanear código QR con WhatsApp:
   - Abrir WhatsApp → Ajustes → Dispositivos vinculados
   - Vincular un dispositivo
   - Escanear código

### 3. Crear Plantillas

**WhatsApp → Plantillas → Crear**

Ejemplo:
```
Hola {{nombre}},

Tu pedido #{{numero_pedido}} ha sido confirmado.

Total: ${{total}}

Gracias por tu compra.
```

## Uso

### Enviar desde Contacto

1. Abrir contacto (res.partner)
2. Clic en "Enviar WhatsApp"
3. Seleccionar plantilla o escribir mensaje personalizado
4. Enviar

### Mensajes Entrantes

Los mensajes recibidos automáticamente:
- Se almacenan en waha.message
- Se vinculan al contacto (si coincide el teléfono)
- Aparecen en el chatter del contacto

## Estructura del Módulo

```
waha/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── waha_account.py          # Cuentas de WhatsApp
│   ├── waha_message.py          # Mensajes
│   ├── waha_template.py         # Plantillas
│   ├── res_partner.py           # Extensión de contactos
│   └── mail_thread.py           # Extensión de chatter
├── wizard/
│   └── waha_composer.py         # Compositor de mensajes
├── controller/
│   └── webhook.py               # Endpoint de webhook
├── tools/
│   ├── waha_api.py             # Cliente API de WAHA
│   ├── phone_validation.py     # Validación de teléfonos
│   └── waha_exception.py       # Excepciones personalizadas
├── views/                       # Vistas XML
├── security/                    # Seguridad y permisos
└── data/                        # Datos iniciales
```

## API de WAHA

El módulo utiliza los siguientes endpoints de WAHA:

- `POST /api/sessions/start` - Iniciar sesión
- `GET /api/sessions/{session}/auth/qr` - Obtener código QR
- `POST /api/sendText` - Enviar mensaje de texto
- `POST /api/sendImage` - Enviar imagen
- `POST /api/sendFile` - Enviar archivo
- `GET /api/sessions/{session}/status` - Obtener estado de sesión

## Webhooks

El módulo expone el endpoint `/waha/webhook` que recibe:

- `message` - Mensaje entrante
- `message.ack` - Confirmación de mensaje (enviado/entregado/leído)
- `session.status` - Cambio de estado de sesión

## Seguridad

### Grupos de Usuarios

- **WAHA User**: Puede enviar mensajes y ver sus propios mensajes
- **WAHA Admin**: Acceso completo a configuración y mensajes

### Reglas de Registro

- Acceso multi-compañía
- Usuarios solo ven mensajes de sus cuentas permitidas
- Administradores ven todo

## Troubleshooting

### La cuenta no se conecta

1. Verificar que WAHA está ejecutándose: `curl http://localhost:3000/health`
2. Revisar logs de WAHA: `docker logs waha`
3. Verificar que session_name es único
4. Intentar desconectar y volver a conectar

### Los mensajes no se envían

1. Verificar que la cuenta está "Conectada"
2. Verificar formato de número (E.164: +521234567890)
3. Revisar logs de WAHA
4. Revisar detalles de error en formulario de mensaje

### Webhook no funciona

1. Verificar que URL de webhook es accesible desde servidor WAHA
2. Verificar token de verificación
3. Revisar logs de Odoo
4. Probar webhook manualmente con curl

## Licencia

LGPL-3

## Créditos

- Proyecto WAHA: https://github.com/devlikeapro/waha
- Basado en el módulo oficial de WhatsApp de Odoo
