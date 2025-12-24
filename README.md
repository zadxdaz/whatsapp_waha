# WAHA Integration for Odoo v18

Módulo de integración WhatsApp para Odoo v18 usando WAHA (WhatsApp HTTP API).

## 🚀 Características

- ✅ Envío y recepción de mensajes WhatsApp
- ✅ Autenticación con código QR
- ✅ Soporte multi-cuenta
- ✅ Sistema de plantillas con variables dinámicas
- ✅ Webhooks en tiempo real
- ✅ Integración con contactos y chatter de Odoo
- ✅ Seguimiento de estados de mensajes

## 📦 Contenido del Repositorio

- **waha/** - Módulo completo de Odoo
- **DOCUMENTO_TECNICO_WAHA_ODOO.md** - Especificación técnica original

## 🔧 Instalación Rápida

```bash
# 1. Clonar repositorio
git clone https://github.com/pedrojabie/whatsapp_waha.git
cd whatsapp_waha

# 2. Instalar WAHA con Docker
docker run -d --name waha -p 3000:3000 \
  -e WHATSAPP_HOOK_URL=http://localhost:8069/waha/webhook \
  devlikeapro/waha

# 3. Instalar dependencias Python
pip install phonenumbers requests

# 4. Copiar módulo a Odoo
cp -r waha /path/to/odoo/addons/

# 5. Reiniciar Odoo e instalar módulo
```

## 📚 Documentación

Dentro de la carpeta `waha/`:
- **README.md** - Guía de uso
- **INSTALLATION.md** - Instalación detallada
- **EXAMPLES.md** - Ejemplos de código
- **TECHNICAL_SUMMARY.md** - Resumen técnico
- **quick_start.sh** - Script de inicio rápido

## 🎯 Uso Básico

### 1. Configurar Cuenta WhatsApp
```
WhatsApp → Configuración → Cuentas → Crear
- WAHA URL: http://localhost:3000
- Session Name: default
- Conectar y escanear QR
```

### 2. Enviar Mensaje
```python
# Desde Python
partner = env['res.partner'].browse(1)
partner.action_send_whatsapp_message()
```

### 3. Crear Plantilla
```
WhatsApp → Plantillas → Crear
Body: "Hola {{nombre}}, tu pedido #{{numero}} está listo"
```

## 🏗️ Estructura del Módulo

```
waha/
├── models/          # Modelos de datos
├── views/           # Vistas XML
├── wizard/          # Asistentes
├── controller/      # Webhook endpoint
├── tools/           # API client
├── security/        # Permisos
└── data/            # Datos iniciales
```

## 📊 Estadísticas

- **Archivos:** 38
- **Líneas de código:** ~5,880+
- **Modelos:** 7
- **Vistas:** 8
- **Documentación:** 8 archivos

## 🛡️ Seguridad

- Grupos de usuarios (User/Admin)
- Control multi-compañía
- Tokens de webhook
- API keys cifradas

## 🔗 Enlaces

- **WAHA Project:** https://github.com/devlikeapro/waha
- **WAHA Docs:** https://waha.devlike.pro
- **Odoo Docs:** https://www.odoo.com/documentation/18.0

## 📝 Licencia

LGPL-3

## 👨‍💻 Autor

Desarrollado siguiendo el patrón del módulo oficial de WhatsApp de Odoo v18.

## 🤝 Contribuir

Pull requests son bienvenidos. Para cambios importantes, por favor abra un issue primero.

## ⭐ Si te gusta este proyecto

¡Dale una estrella en GitHub! ⭐
