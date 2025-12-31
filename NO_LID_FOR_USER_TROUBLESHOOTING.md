# Troubleshooting: "No LID for user" Error

## Problema
Cuando intentas enviar un mensaje de WhatsApp, recibis el error:
```
Error: No LID for user
```

Este error viene de WAHA/WhatsApp Web y significa que no puede encontrar el ID local (LID) del usuario/chat donde intentas enviar el mensaje.

---

## Causas Principales

### 1. **El contacto no existe en WhatsApp Web**
El contacto al que intentas enviar no está en tu lista de contactos de WhatsApp Web.

**Solución:**
- Abre WhatsApp Web manualmente
- Busca el número de teléfono en la barra de búsqueda
- Abre un chat con ese contacto (aunque sea vacío)
- Espera a que se sincronice con WAHA
- Intenta enviar nuevamente

### 2. **No hay conversación iniciada**
Aunque el contacto exista, es posible que no haya una conversación previa iniciada.

**Solución:**
- En WhatsApp Web, busca el contacto
- Haz clic para abrir el chat (aunque esté vacío)
- Envía al menos un mensaje (puede ser un emoji o espacio)
- Espera a que WhatsApp sincronice
- Intenta desde Odoo nuevamente

### 3. **Formato de número incorrecto**
El número telefónico no está en el formato correcto que espera WhatsApp.

**Solución:**
- Verifica el número tenga código de país (ej: +549111234567 o 549111234567)
- En Argentina: +549 + área + número (sin primer 9)
- En general: +[país][área][número]
- Asegúrate de no tener espacios o caracteres especiales

### 4. **Sesión desincronizada**
La sesión de WhatsApp Web en WAHA se desincronizó del navegador real.

**Solución:**
- En Odoo: Ve a Cuenta de WhatsApp → Botón "Reconectar"
- En WAHA: Reinicia el contenedor: `docker restart waha-1`
- Vuelve a escanear el QR
- Espera a que estado sea "connected"
- Intenta enviar nuevamente

---

## Pasos de Diagnóstico

### 1. **Verificar lista de chats en WAHA**
```bash
# Ver todos los chats disponibles
curl -X GET "http://localhost:3000/api/chats" \
  -H "X-Api-Key: TU_API_KEY"
```

Busca si el número (en formato `número@c.us`) aparece en la lista. Si no está, necesitas iniciar manualmente una conversación en WhatsApp Web.

### 2. **Verificar logs de WAHA**
```bash
docker logs -f waha-1 | grep -i "sendText\|LID"
```

Esto te mostrará exactamente qué está pasando cuando intentas enviar.

### 3. **Verificar logs de Odoo**
```bash
docker logs -f waha-odoo-1 | grep -i "whatsapp\|sending\|error"
```

Busca mensajes de warning o error sobre qué número se está intentando enviar.

### 4. **Validar número en Odoo**
- Ve a Contactos
- Busca el contacto
- Verifica que el campo "Teléfono" o "Móvil" tenga el formato correcto
- Prueba actualizar el número si es necesario

---

## Solución Definitiva: Sincronizar Contactos

Si tienes muchos contactos y quieres asegurar que todos estén disponibles en WAHA:

### Opción 1: Manual en WhatsApp Web
1. Abre WhatsApp Web (http://localhost:3000 o donde esté WAHA)
2. Ve a tu lista de contactos
3. Abre chats con todos tus contactos principales
4. Espera a que se sincronicen con WAHA

### Opción 2: Automática (próximo desarrollo)
Se puede agregar una función "Sincronizar Contactos" que:
- Obtiene todos los contactos de Odoo
- Intenta abrir un chat con cada uno en WAHA
- Almacena la información del chat en la BD

---

## Cómo Evitar Este Error

### 1. **Enriquecer datos de contactos**
- Asegúrate que todos los contactos en Odoo tengan número de teléfono
- Formatea los números correctamente antes de crear contactos

### 2. **Validar antes de enviar**
- El sistema ahora valida que el chat exista antes de enviar
- Si no existe, muestra un aviso claro

### 3. **Contactos Entrantes**
- Cuando recibis un mensaje, se crea automáticamente el contacto y el chat
- Es más confiable enviar a números que ya te contactaron

---

## Configuración Recomendada

### En Odoo
```
Ajustes → WhatsApp Waha → Cuentas
- Nombre: Tu cuenta
- URL de WAHA: http://waha:3000
- Nombre de Sesión: default
- Clave API: (tu API key)
```

### Validar Contactos
- Teléfono formato: +549111234567 (con +)
- O: 549111234567 (sin +)
- Nunca: 11 1234567 (sin código de país)

---

## Soporte Adicional

Si el problema persiste:

1. **Revisar logs completos:**
   ```bash
   docker logs waha-1 > /tmp/waha_logs.txt
   docker logs waha-odoo-1 > /tmp/odoo_logs.txt
   ```

2. **Verificar estado de sesión:**
   ```bash
   curl -X GET "http://localhost:3000/api/sessions/default" \
     -H "X-Api-Key: TU_API_KEY"
   ```

3. **Reiniciar limpiamente:**
   ```bash
   docker compose restart
   ```

4. **Abrir sesión nueva:**
   - Eliminar sesión en WAHA
   - Crear sesión nueva
   - Escanear QR nuevamente
