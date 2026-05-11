# Flujo de un mensaje entrante — Módulo WAHA (Odoo)

Documento de referencia técnica para el módulo `whatsapp_waha/waha`.  
Describe cada paso, validación y bifurcación desde que WAHA dispara el webhook hasta que el mensaje aparece en Discuss.

---

## Índice

1. [Entrada: Webhook HTTP](#1-entrada-webhook-http)
2. [Validaciones de cuenta y token](#2-validaciones-de-cuenta-y-token)
3. [Enrutamiento por tipo de evento](#3-enrutamiento-por-tipo-de-evento)
4. [Procesamiento del mensaje (`_handle_incoming_message`)](#4-procesamiento-del-mensaje)
5. [Deduplicación](#5-deduplicación)
6. [Extracción de contexto (`_extract_message_context`)](#6-extracción-de-contexto)
7. [Creación de `waha.message`](#7-creación-de-wahamessage)
8. [Computed: `waha_chat_id`](#8-computed-waha_chat_id)
9. [Computed: `waha_partner_id`](#9-computed-waha_partner_id)
10. [Computed: `mail_message_id` (mensaje en Discuss)](#10-computed-mail_message_id)
11. [Procesamiento de media](#11-procesamiento-de-media)
12. [Actualización de metadata del chat](#12-actualización-de-metadata-del-chat)
13. [Eventos secundarios: ACK y sesión](#13-eventos-secundarios)
14. [Flujo para mensajes enviados desde el celular (`fromMe=true`)](#14-flujo-fromme)
15. [Diagrama de flujo completo](#15-diagrama)

---

## 1. Entrada: Webhook HTTP

**Archivo:** `controller/webhook.py`  
**Ruta:** `POST /waha/webhook` — pública, sin CSRF

WAHA envía un JSON con esta estructura mínima:

```json
{
  "session": "LOGRA_WAHA",
  "event": "message.any",
  "payload": { ... },
  "me": { "id": "549...@c.us" }
}
```

Odoo parsea el body crudo con `json.loads(request.httprequest.data)`.  
Si el parseo falla, responde `500` y loguea la excepción.

---

## 2. Validaciones de cuenta y token

### 2.1 Búsqueda de cuenta por sesión

```python
account = waha.account.search([('session_name', '=', session_name)])
```

| Resultado | Acción |
|-----------|--------|
| No encontrada | Responde `{"status": "error", "message": "Session not found"}` y sale |
| Encontrada | Continúa |

### 2.2 Verificación de token (opcional)

Si `account.webhook_verify_token` está configurado, Odoo verifica el token recibido.

**Prioridad de búsqueda del token recibido:**
1. Query param `?token=`
2. Header `X-Webhook-Token`

| Token recibido vs. esperado | Acción |
|---------------------------|--------|
| Coincide | Continúa |
| No coincide o vacío | Responde `403 {"status": "error", "message": "Invalid token"}` y sale |

---

## 3. Enrutamiento por tipo de evento

```
event = data.get('event')
```

| Evento | Handler |
|--------|---------|
| `message` | `_handle_incoming_message()` |
| `message.any` | `_handle_incoming_message()` (igual — cubre mensajes propios) |
| `message.ack` | `_handle_message_ack()` |
| `session.status` | `_handle_session_status()` |
| Cualquier otro | Log info "Unhandled event type" — responde `200 ok` sin procesar |

> **Nota:** `message` solo dispara para mensajes **recibidos**. `message.any` dispara para **todos** (recibidos + enviados desde el celular). Ambos usan el mismo handler.

---

## 4. Procesamiento del mensaje

**Método:** `_handle_incoming_message(data)`

Extrae del payload:
- `msg_uid` = `payload.get('id')` — identificador único del mensaje en WhatsApp

---

## 5. Deduplicación

Se aplican **dos capas** en orden.

### 5.1 Deduplicación por `msg_uid` (principal)

```python
existing = waha.message.search([
    ('msg_uid', '=', msg_uid),
    ('wa_account_id', '=', account.id)
])
```

Si existe → **sale sin hacer nada**.

### 5.2 Race condition guard — solo para `fromMe=True`

Cuando Odoo envía un mensaje, la secuencia es:
1. `message_post` crea el `mail.message`
2. Se crea `waha.message` con `state='outgoing'` y `msg_uid=False`
3. `_compute_msg_uid` llama a la WAHA API síncronamente
4. WAHA puede disparar el webhook **antes** de retornar la respuesta de la API
5. El webhook llega en una nueva transacción donde el `waha.message` del paso 2 todavía no commitió

Para cubrir este caso, cuando `fromMe=True`:

```python
twin = waha.message.search([
    ('wa_account_id', '=', account.id),
    ('raw_chat_id', '=', context['chat_id']),
    ('message_type', '=', 'outbound'),
    ('body', '=', context['body']),
    ('msg_uid', '=', False),           # ← clave: aún no tiene msg_uid
], order='id desc', limit=1)
```

Si encuentra el "gemelo" → le escribe el `msg_uid` y **sale sin crear duplicado**.

---

## 6. Extracción de contexto

**Método:** `_extract_message_context(payload)`

### 6.1 Determinación del chat y del contacto

| Dirección | `chat_id` | `sender_raw` (el contacto) |
|-----------|-----------|---------------------------|
| Inbound (`fromMe=False`) | `payload.from` | `payload.from` (1-1) o `payload.participant` (grupo) |
| Outbound (`fromMe=True`) | `payload.to` | `payload.to` (1-1) o `payload.participant` (grupo) |

`is_group` se determina por `'@g.us' in chat_id` (ya corregido para outbound).

### 6.2 Extracción de LID o teléfono del contacto

Del `sender_raw`:

| Sufijo | Resultado |
|--------|-----------|
| `@lid` | `sender_lid = parte numérica` |
| `@c.us` | `sender_phone = parte numérica` |
| Otro | `sender_phone = parte antes de `@` o el string completo` |

### 6.3 Body del mensaje

```python
body = payload.get('body', '')
```

- Si es `dict` → extrae `.text` o convierte con `str()`
- Si no es `str` → convierte con `str()`
- Si tiene `mentionedIds` → reemplaza `@<numeric_id>` con el nombre del contacto (`_resolve_mentions`)

### 6.4 Timestamp

```python
wa_timestamp = datetime.fromtimestamp(payload.get('timestamp'))
```

Si falla → usa `fields.Datetime.now()`.

### 6.5 Reply to (respuesta a otro mensaje)

Búsqueda en orden:
1. `payload.replyTo.id` (formato moderno WAHA)
2. `payload._data.quotedStanzaID` (fallback formato antiguo)

Si hay `reply_to_stanza_id`, se busca el `waha.message` original:
- Primero por `msg_uid` exacto
- Luego por `msg_uid ilike stanza_id` (fallback)

---

## 7. Creación de `waha.message`

```python
vals = {
    'msg_uid':             context['msg_uid'],
    'wa_account_id':       account.id,
    'message_type':        'outbound' if from_me else 'inbound',
    'state':               'sent'     if from_me else 'received',
    'body':                context['body'],
    'raw_chat_id':         context['chat_id'],
    'raw_sender_lid':      context['sender_lid'],
    'raw_sender_phone':    context['sender_phone'],
    'wa_timestamp':        context['wa_timestamp'],
    'raw_payload':         payload,
    # opcionales:
    'participant_id':      context['participant'],
    'reply_to_message_id': original_msg.id,
    'reply_to_msg_uid':    original_msg.msg_uid,
}
```

Al llamar `waha.message.create(vals)`, el ORM dispara automáticamente los tres computed fields encadenados:

```
raw_chat_id / wa_account_id
    └─► _compute_waha_chat_id
            └─► _compute_waha_partner_id
                    └─► _compute_mail_message_id
```

---

## 8. Computed: `waha_chat_id`

**Método:** `waha_message._compute_waha_chat_id`  
**Depende de:** `raw_chat_id`, `wa_account_id`

```python
chat = waha.chat.search([
    ('wa_chat_id', '=', raw_chat_id),
    ('wa_account_id', '=', account.id)
])
```

### Si no existe → `waha.chat.find_or_create()`

1. Para grupos: consulta WAHA API para obtener el nombre del grupo
2. Para 1-1: usa el nombre del partner si está disponible
3. Llama a `waha.chat.create()` que internamente invoca `_ensure_discuss_channel()`

### `_ensure_discuss_channel()`

Crea un `discuss.channel`:

```python
discuss.channel.create({
    'name':                  '<Cuenta> - <Contacto>',
    'channel_type':          'waha',
    'is_whatsapp':           True,
    'wa_chat_id':            wa_chat_id,
    'whatsapp_account_id':   account.id,
})
```

Luego llama a `_sync_channel_members()`:

| Chat tipo | Miembros agregados |
|-----------|-------------------|
| Individual | `partner_id` del contacto + `notify_user_ids` de la cuenta |
| Grupo | `group_participants` + `notify_user_ids` de la cuenta |
| Siempre | `account_partner_id` si está configurado y no está ya presente |

> Solo agrega miembros que no estén ya en `channel_partner_ids` (condición idempotente).

---

## 9. Computed: `waha_partner_id`

**Método:** `waha_message._compute_waha_partner_id`  
**Depende de:** `raw_sender_lid`, `raw_sender_phone`, `wa_account_id`, `message_type`

Identifica al **contacto** (la otra parte de la conversación), sin importar la dirección.

### Validaciones de entrada

| Condición | Acción |
|-----------|--------|
| Sin LID ni teléfono | `waha_partner_id = False` |
| Teléfono es `'0'` o `''` y sin LID | `waha_partner_id = False` |
| `sender_phone` contiene `@g.us` | `waha_partner_id = False` (grupos no tienen partner) |

### Búsqueda en orden

1. **Por LID** (`waha.partner.search [lid = sender_lid, account = account.id]`)
   - Si encuentra y le falta teléfono → actualiza `phone_number`
2. **Por teléfono** (`waha.partner.search [phone_number = sender_phone, account = account.id]`)
   - Si encuentra y le falta LID → actualiza `lid`
3. **Creación automática** via `waha.partner.find_or_create_by_lid_or_phone()`

### `find_or_create_by_lid_or_phone()`

1. **Enriquecimiento previo** (si `auto_enrich=True` y cuenta conectada):
   - Solo LID → consulta WAHA API para obtener teléfono
   - Solo teléfono → consulta WAHA API para obtener LID

2. Reintenta búsqueda con datos enriquecidos

3. Si no encuentra → `_create_partner_with_lid_or_phone()`:
   - Busca `res.partner` existente por teléfono (`mobile` o `phone` ilike)
   - Si existe → lo usa (sin crear duplicado)
   - Si no → crea `res.partner` con nombre desde WAHA (`name > pushname > verifiedName > "WhatsApp +teléfono"`)
   - Descarga avatar de perfil de WhatsApp
   - Crea `waha.partner` enlazado al `res.partner`

> Para grupos: `auto_enrich=False` (evita llamadas lentas a la API por cada participante)

---

## 10. Computed: `mail_message_id`

**Método:** `waha_message._compute_mail_message_id`  
**Depende de:** `waha_chat_id`, `waha_partner_id`, `body`, `wa_timestamp`, `message_type`, `reply_to_message_id`

Este computed puede dispararse **múltiples veces** en una misma transacción porque sus dependencias también son computed fields. Hay tres capas de protección:

### Capa 1: Check de cache ORM

```python
if message.mail_message_id:
    continue
```

### Capa 2: Check directo a DB (anti-recompute múltiple)

```python
self.env.cr.execute(
    'SELECT mail_message_id FROM waha_message WHERE id = %s', (message.id,)
)
row = self.env.cr.fetchone()
if row and row[0]:
    message.mail_message_id = row[0]
    continue
```

Bypasea el cache del ORM para detectar si un disparo anterior ya escribió el valor en DB.

### Capa 3: Check de mensaje existente en Discuss

Antes de llamar a `message_post`, busca si ya existe un `mail.message` equivalente en el canal:

**Método:** `_find_existing_discuss_mail_message()`

```python
# Búsqueda estricta (con autor esperado)
candidates = mail.message.search([
    ('model', '=', 'discuss.channel'),
    ('res_id', '=', channel.id),
    ('message_type', '=', 'comment'),
    ('author_id', '=', expected_author.id),
])
candidates = candidates.filtered(body_matches)

# Si no hay → búsqueda sin filtro de autor
if not candidates:
    candidates = mail.message.search([...sin author_id...])
    candidates = candidates.filtered(body_matches)
```

Desempate por timestamp (±5 minutos). Solo linkea si hay **exactamente 1** candidato.

Si encuentra → `mail_message_id = existing` y **no crea nada nuevo**.

### Validaciones para creación

| Condición | Acción |
|-----------|--------|
| `message_type == 'outbound'` sin `allow_outbound_discuss_sync` en contexto | Skip (mensajes enviados desde Odoo ya tienen su `mail.message`) |
| Sin `waha_chat_id` o sin `waha_partner_id` | `mail_message_id = False` |
| `waha_partner_id` sin `partner_id` | `mail_message_id = False` |
| Chat sin `discuss_channel_id` | `mail_message_id = False` |

### Autor del mensaje en Discuss

| Dirección | Autor |
|-----------|-------|
| Inbound | `waha_partner_id.partner_id` (el contacto) |
| Outbound (fromMe=True, desde celular) | `wa_account_id.account_partner_id` → fallback `notify_user_ids[:1].partner_id` → fallback `env.user.partner_id` |

### Creación vía `message_post`

```python
discuss_channel.with_context(skip_whatsapp_send=True).message_post(
    body=body_clean,
    message_type='comment',
    subtype_xmlid='mail.mt_comment',
    author_id=author_partner.id,
    date=wa_timestamp,
    parent_id=parent_mail_message.id,  # solo si es reply
)
```

El contexto `skip_whatsapp_send=True` evita que `mail_thread.py` vuelva a enviar el mensaje a WhatsApp (loop infinito).

---

## 11. Procesamiento de media

**Método:** `waha_message.process_payload_media()`

### Detección de tipo de contenido

| Condición en payload | `content_type` |
|---------------------|----------------|
| `payload.location` existe | `location` |
| `payload.hasMedia = True` + `type = 'image'` | `image` |
| `payload.hasMedia = True` + `type = 'video'` | `video` |
| `payload.hasMedia = True` + `type = 'audio'` o `'ptt'` | `audio` |
| `payload.hasMedia = True` + `type = 'sticker'` | `sticker` |
| `payload.hasMedia = True` + otro | `document` |
| Sin media | `text` → **sale sin hacer nada** |

### Descarga del archivo

```python
media_url = payload.media.url
# Fix de localhost → URL real del servidor WAHA
media_url = media_url.replace('http://localhost:3000', account.waha_url)

response = requests.get(media_url, headers={'X-Api-Key': api_key}, timeout=60)
```

### Creación de attachments

Se crean **dos copias** del attachment:

| Attachment | `res_model` | `res_id` | Propósito |
|------------|-------------|----------|-----------|
| Copia 1 | `waha.message` | `waha_message.id` | Registro interno |
| Copia 2 | `mail.message` | `mail_message_id.id` | Visible en Discuss UI |

La copia 2 se linkea a `mail.message.attachment_ids` y se notifica al canal via `channel._notify_thread()` para actualización en tiempo real.

---

## 12. Actualización de metadata del chat

```python
chat.update_last_message(message.wa_timestamp)
```

Incrementa `message_count` y actualiza `last_message_time`.

---

## 13. Eventos secundarios

### `message.ack` — Confirmación de entrega

Busca `waha.message` por `msg_uid` y actualiza `state`:

| ACK value | Estado Odoo |
|-----------|-------------|
| 0 | `error` |
| 1 | `outgoing` (en servidor) |
| 2 | `sent` |
| 3 | `delivered` |
| 4 | `read` |
| 5 | `read` (reproducido) |

También registra `sent_date`, `delivered_date`, `read_date` si aún no están.

### `session.status` — Estado de la sesión

Actualiza `waha.account.status`:

| WAHA status | Odoo status |
|-------------|-------------|
| `STOPPED` | `disconnected` |
| `STARTING` | `connecting` |
| `SCAN_QR_CODE` | `connecting` |
| `WORKING` | `connected` |
| `FAILED` | `error` |

---

## 14. Flujo fromMe=True (enviado desde el celular)

Cuando `fromMe=True` el mensaje lo envió el dueño de la cuenta desde su celular (no desde Odoo).

**Diferencias clave respecto a un mensaje inbound normal:**

| Campo | Inbound normal | fromMe=True |
|-------|---------------|-------------|
| `chat_id` | `payload.from` | `payload.to` (el destinatario) |
| `sender_raw` | `payload.from` | `payload.to` (para 1-1) |
| `message_type` | `inbound` | `outbound` |
| `state` | `received` | `sent` |
| Autor en Discuss | Contacto | `account_partner_id` |
| Contexto de creación | — | `allow_outbound_discuss_sync=True` |

El contexto `allow_outbound_discuss_sync=True` es lo que le dice a `_compute_mail_message_id` que sí debe crear el mensaje en Discuss (a diferencia de mensajes outbound enviados desde Odoo, que ya tienen su propio `mail.message`).

---

## 15. Diagrama de flujo completo

```
POST /waha/webhook
       │
       ▼
  Parsear JSON
       │
       ▼
  Buscar account por session_name ──► No encontrada → 404 error
       │
       ▼
  Verificar token (si configurado) ──► Inválido → 403 error
       │
       ▼
  ┌────────────────────────────────────────┐
  │          Tipo de evento                │
  └────────────────────────────────────────┘
       │              │              │
  message/       message.ack    session.status
  message.any        │              │
       │         Actualizar      Actualizar
       ▼         waha.message    waha.account
  _handle_incoming_message()     .status
       │
       ▼
  [DEDUP 1] Buscar por msg_uid
       │ Existe → return (no hacer nada)
       │
       ▼
  _extract_message_context()
  · chat_id (from/to según fromMe)
  · sender_raw → LID o teléfono
  · body, timestamp, reply_to
       │
       ▼
  [DEDUP 2] fromMe=True: buscar gemelo outbound sin msg_uid
       │ Encontrado → estampar msg_uid + return
       │
       ▼
  waha.message.create(vals)
       │
       ├──► _compute_waha_chat_id
       │         │ ¿existe waha.chat?
       │         ├─ Sí → usar existente
       │         └─ No → find_or_create()
       │                   └─► _ensure_discuss_channel()
       │                             └─► _sync_channel_members()
       │
       ├──► _compute_waha_partner_id
       │         │ Buscar por LID → por teléfono
       │         └─ No existe → find_or_create_by_lid_or_phone()
       │                            ├─ Enriquecer desde WAHA API
       │                            ├─ Buscar res.partner existente
       │                            └─ Crear res.partner + waha.partner
       │
       └──► _compute_mail_message_id
                 │ [DEDUP 3a] Check ORM cache
                 │ [DEDUP 3b] Check directo DB (SELECT sql)
                 │ [DEDUP 3c] _find_existing_discuss_mail_message()
                 │
                 │ ¿outbound sin allow_outbound_discuss_sync?
                 │    └─ Skip (enviado desde Odoo, ya tiene mail.message)
                 │
                 └─► discuss_channel.message_post(
                           body, author_id, date, parent_id,
                           context skip_whatsapp_send=True
                     )
                           │
                           └─► mail_message creado en Discuss
       │
       ▼
  process_payload_media()
  · Detectar tipo (image/video/audio/document)
  · Descargar desde URL WAHA
  · Crear ir.attachment × 2 (waha.message + mail.message)
  · Notificar canal (tiempo real)
       │
       ▼
  chat.update_last_message()
       │
       ▼
  Respuesta 200 {"status": "ok"}
```

---

## Archivos relevantes

| Archivo | Responsabilidad |
|---------|----------------|
| `controller/webhook.py` | Entrada HTTP, validaciones, enrutamiento, deduplicación |
| `models/waha_message.py` | Modelo principal, computed fields, envío, ACK |
| `models/waha_chat.py` | Gestión de chats y canales Discuss |
| `models/waha_partner.py` | Gestión de contactos WhatsApp |
| `models/waha_account.py` | Configuración de cuenta, `account_partner_id` |
| `models/mail_thread.py` | Override de `message_post` para capturar envíos desde Odoo |
| `models/discuss_channel.py` | Extensión del canal con campos WAHA |
| `tools/waha_api.py` | Cliente HTTP hacia el servidor WAHA |
