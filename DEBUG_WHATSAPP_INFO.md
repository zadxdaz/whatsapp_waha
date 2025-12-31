# WhatsApp Info Action - Debugging Tool

## 🔍 Nueva Funcionalidad: Obtener Información de WhatsApp

Se agregó una nueva acción en los partners para obtener información de WhatsApp directamente desde WAHA API, útil para debugging manual.

### 📍 Ubicación
- **Modelo**: `res.partner` 
- **Método**: `action_get_whatsapp_info()`
- **Vista**: Botón "WhatsApp Info" en partner form

### 🎯 Qué Hace

La acción obtiene información del contacto desde WAHA API y la muestra en una notificación con:
- Phone number
- Contact ID
- Name y Push Name
- Verification level
- Business account info
- Profile image (truncado)

### 🚀 Cómo Usar

1. Abre un contacto (Partner) en Odoo
2. Verifica que tenga número de teléfono (mobile o phone)
3. Haz click en el botón "WhatsApp Info" (icono info-circle)
4. Espera a que consulte WAHA API
5. Ve la información del contacto en WhatsApp

### 📊 Información que Retorna

```json
{
  "id": "5511999999999@c.us",
  "name": "John Doe",
  "pushName": "John",
  "verifiedLevel": "BUSINESS",
  "verifiedName": "John Business",
  "isBusiness": true,
  "image": "https://..."
}
```

### 🔧 Requisitos

- El partner debe tener mobile o phone number
- Al menos una cuenta WhatsApp conectada (status='connected')
- WAHA server corriendo y accessible

### 💡 Casos de Uso

1. **Validar sincronización**: Verificar que WAHA tiene el contacto
2. **Debuggear formato de chat_id**: Ver exactamente cómo WAHA identifica el contacto
3. **Verificar campos**: Confirmar name, pushName, verification status
4. **Testing manual**: Sin necesidad de enviar mensaje real

### ⚠️ Comportamiento

- **Sin teléfono**: Muestra error (rojo)
- **Sin cuenta conectada**: Muestra error (rojo)
- **Contacto no en WAHA**: Muestra warning (amarillo)
- **Éxito**: Muestra información (verde) con todos los datos

### 🔐 Seguridad

- Acción solo visible si el partner tiene teléfono
- No modifica datos, solo consulta
- Errores son loguados pero no exponen datos sensibles
- Log incluye la información completa del contacto

### 📝 Implementación

**Archivo**: `waha/models/res_partner.py`
**Método**: `action_get_whatsapp_info()`
- Valida teléfono y cuenta
- Llama `WahaApi.get_contact()`
- Formatea respuesta legible
- Maneja errores con notificaciones

**Vista**: `waha/views/res_partner_views.xml`
- Botón "WhatsApp Info" con icono info-circle
- Visible si partner tiene teléfono
- En la fila de botones de stat (junto a Send WhatsApp)

### 🛠️ Próximas Mejoras

- [ ] Ver logs de la última consulta
- [ ] Caché de información (5 min)
- [ ] Opción para refrescar caché
- [ ] Ver historial de cambios en el contacto
- [ ] Comparar con datos en Odoo

---

**Disponible desde**: Refactoring v2.0  
**Estado**: ✅ Producción Ready
