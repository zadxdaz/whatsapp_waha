# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import requests
import base64
import json

_logger = logging.getLogger(__name__)


class WahaApi:
    """
    WAHA API Client
    Handles all communication with WAHA server
    Based on WhatsAppApi class from official Odoo WhatsApp module
    """

    def __init__(self, account):
        """
        Initialize WAHA API client
        
        Args:
            account: waha.account record
        """
        self.account = account
        self.base_url = account.waha_url.rstrip('/')
        self.session_name = account.session_name
        self.api_key = account.api_key
        self.headers = {'Content-Type': 'application/json'}
        if self.api_key:
            self.headers['X-Api-Key'] = self.api_key

    def _make_request(self, method, endpoint, data=None, files=None, timeout=30):
        """
        Make HTTP request to WAHA API
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint
            data: JSON data to send
            files: Files to upload
            timeout: Request timeout in seconds
            
        Returns:
            dict: Response data
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                json=data if data and not files else None,
                files=files,
                headers=self.headers,
                timeout=timeout
            )
            
            # Log request for debugging
            _logger.debug('WAHA API Request: %s %s - Status: %s', method, url, response.status_code)
            
            response.raise_for_status()
            
            # Return JSON if available
            if response.content:
                try:
                    return response.json()
                except json.JSONDecodeError:
                    return {'raw': response.text}
            return {}
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}"
            error_detail = ""
            try:
                error_data = e.response.json()
                error_msg = error_data.get('message', error_msg)
                # WAHA error response might have error field
                if 'error' in error_data:
                    error_detail = str(error_data['error'])
            except:
                error_msg = e.response.text or error_msg
            
            full_error = f"{error_msg}{' - ' + error_detail if error_detail else ''}"
            _logger.error('WAHA API HTTP Error: %s %s - %s', method, url, full_error)
            
            # Re-raise with more context
            raise Exception(full_error) from e
            
        except requests.exceptions.Timeout as e:
            _logger.error('WAHA API Timeout: %s %s - Server not responding', method, url)
            raise
            
        except requests.exceptions.ConnectionError as e:
            _logger.error('WAHA API Connection Error: %s %s - Cannot connect to server', method, url)
            raise
            
        except Exception as e:
            _logger.error('WAHA API Unexpected Error: %s %s - %s', method, url, str(e))
            raise

    # ============================================================
    # SESSION MANAGEMENT
    # ============================================================

    def start_session(self):
        """Start a new WAHA session"""
        # First, try to get existing session
        try:
            session_info = self._make_request('GET', f'/api/sessions/{self.session_name}')
            # Session exists, start it if stopped
            if session_info.get('status') in ['STOPPED', 'FAILED']:
                return self._make_request('POST', f'/api/sessions/{self.session_name}/start')
            # Session already running or starting
            return session_info
        except requests.exceptions.HTTPError as e:
            # Session doesn't exist (404), create it
            if e.response.status_code == 404:
                return self._make_request('POST', '/api/sessions', data={
                    'name': self.session_name,
                    'config': {
                        'proxy': None,
                        'noweb': {
                            'store': {
                                'enabled': True,
                            }
                        }
                    }
                })
            # Other error, re-raise
            raise

    def get_session_status(self):
        """Get session status"""
        return self._make_request('GET', f'/api/sessions/{self.session_name}')

    def stop_session(self):
        """Stop/delete session"""
        return self._make_request('DELETE', f'/api/sessions/{self.session_name}')

    def get_qr_code(self):
        """Get QR code for session"""
        return self._make_request('GET', f'/api/{self.session_name}/auth/qr')

    def get_screenshot(self):
        """Get screenshot of WhatsApp Web"""
        return self._make_request('GET', f'/api/screenshot', data={
            'session': self.session_name
        })

    # ============================================================
    # MESSAGE SENDING
    # ============================================================

    def send_text(self, chat_id, text, reply_to=None):
        """
        Send text message
        
        Args:
            chat_id: WhatsApp chat ID (e.g., "1234567890@c.us")
            text: Message text (max 4096 characters for WhatsApp)
            reply_to: Optional message UID to reply to (helps establish context)
            
        Raises:
            ValueError: If text is empty or too long
        """
        if not text or not text.strip():
            raise ValueError("Message text cannot be empty")
        
        if len(text) > 4096:
            raise ValueError("Message text exceeds 4096 character limit")
        
        if not chat_id:
            raise ValueError("Chat ID cannot be empty")
        
        _logger.debug('Sending text to %s: %s', chat_id, text[:100] + '...' if len(text) > 100 else text)
        
        data = {
            'session': self.session_name,
            'chatId': chat_id,
            'text': text
        }
        
        # Add reply_to if provided - this helps establish context in the chat
        #if reply_to:
        #    data['reply_to'] = reply_to
        #    _logger.debug('Replying to message: %s', reply_to)
        
        _logger.info("data: %s", data)
        
        result = self._make_request('POST', '/api/sendText', data=data)
        _logger.info('=== WAHA API send_text() Response ===')
        _logger.info('Message ID: %s', result.get('message_id', result.get('id', 'N/A')))
        _logger.debug('Full response: %s', result)
        
        return result

    def send_image(self, chat_id, image_data, caption=None):
        """
        Send image message
        
        Args:
            chat_id: WhatsApp chat ID
            image_data: Base64 encoded image data
            caption: Optional caption
        """
        data = {
            'session': self.session_name,
            'chatId': chat_id,
            'file': {
                'mimetype': 'image/jpeg',
                'data': image_data
            }
        }
        if caption:
            data['caption'] = caption
        
        return self._make_request('POST', '/api/sendImage', data=data)

    def send_file(self, chat_id, file_data, filename, mimetype):
        """
        Send file/document message
        
        Args:
            chat_id: WhatsApp chat ID
            file_data: Base64 encoded file data
            filename: File name
            mimetype: MIME type
        """
        return self._make_request('POST', '/api/sendFile', data={
            'session': self.session_name,
            'chatId': chat_id,
            'file': {
                'filename': filename,
                'mimetype': mimetype,
                'data': file_data
            }
        })

    def send_video(self, chat_id, video_data, caption=None):
        """Send video message"""
        data = {
            'session': self.session_name,
            'chatId': chat_id,
            'file': {
                'mimetype': 'video/mp4',
                'data': video_data
            }
        }
        if caption:
            data['caption'] = caption
        
        return self._make_request('POST', '/api/sendVideo', data=data)

    def send_audio(self, chat_id, audio_data):
        """Send audio message"""
        return self._make_request('POST', '/api/sendAudio', data={
            'session': self.session_name,
            'chatId': chat_id,
            'file': {
                'mimetype': 'audio/ogg',
                'data': audio_data
            }
        })

    def send_location(self, chat_id, latitude, longitude, title=None):
        """Send location message"""
        data = {
            'session': self.session_name,
            'chatId': chat_id,
            'latitude': latitude,
            'longitude': longitude
        }
        if title:
            data['title'] = title
        
        return self._make_request('POST', '/api/sendLocation', data=data)

    # ============================================================
    # WEBHOOK MANAGEMENT
    # ============================================================

    def set_webhook(self, webhook_url):
        """Configure webhook URL for this session"""
        return self._make_request('POST', f'/api/sessions/{self.session_name}/webhook', data={
            'url': webhook_url
        })

    # ============================================================
    # CONTACTS AND CHATS
    # ============================================================

    def get_contacts(self):
        """Get all contacts for this session
        
        Note: This endpoint is not commonly used. Use get_contact() for specific lookups.
        """
        # WAHA endpoint: GET /api/contacts?session={session}
        # This endpoint may not be available in all WAHA versions
        try:
            return self._make_request('GET', f'/api/contacts?session={self.session_name}')
        except Exception as e:
            _logger.warning('get_contacts not available (non-critical): %s', str(e))
            return []

    def get_contact(self, phone_number):
        """Get a specific contact by phone number
        
        Args:
            phone_number: Phone number (with or without country code)
        
        Returns:
            Contact information dict or None if not found
        """
        try:
            # Normalize phone to WhatsApp format (e.g., 1234567890@c.us)
            normalized_phone = str(phone_number).replace('+', '').replace(' ', '')
            
            # Try different WhatsApp ID formats
            contact_ids = [
                f"{normalized_phone}@c.us",
                f"{normalized_phone}@lid",
                normalized_phone,
            ]
            
            # WAHA endpoint: GET /api/contacts?session={session}&contactId={contactId}
            for contact_id in contact_ids:
                try:
                    result = self._make_request(
                        'GET',
                        f'/api/contacts?session={self.session_name}&contactId={contact_id}'
                    )
                    
                    # If we get a valid response (not error), return it
                    if result and isinstance(result, str):
                        # API returns a string with contact info
                        return {'id': contact_id, 'name': result}
                    elif result:
                        return result
                        
                except Exception:
                    # Try next format
                    continue
            
            _logger.debug('Contact not found in WhatsApp for: %s', phone_number)
            return None
            
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning('Could not get contact from WAHA (non-critical): %s', str(e))
            return None

    def get_contact_profile_picture(self, contact_id):
        """Get contact's profile picture URL
        
        Args:
            contact_id: WhatsApp contact ID (e.g., 1234567890@c.us)
        
        Returns:
            Profile picture URL (string) or None if not available
        """
        try:
            # WAHA endpoint: GET /api/contacts/profile-picture?session={session}&contactId={contactId}
            result = self._make_request(
                'GET',
                f'/api/contacts/profile-picture?session={self.session_name}&contactId={contact_id}'
            )
            
            # API returns a string with the URL or null
            if result and isinstance(result, str) and result != 'null':
                return result
            
            return None
            
        except Exception as e:
            _logger.debug('Could not get profile picture for %s: %s', contact_id, str(e))
            return None

    def get_group_info(self, group_id):
        """Get group information
        
        Args:
            group_id: WhatsApp group ID (e.g., 123456@g.us)
        
        Returns:
            Group information dict or None if not found
        """
        try:
            # WAHA endpoint: GET /api/{session}/groups/{id}
            result = self._make_request(
                'GET',
                f'/api/{self.session_name}/groups/{group_id}'
            )
            
            return result if result else None
            
        except Exception as e:
            _logger.debug('Could not get group info for %s: %s', group_id, str(e))
            return None

    def get_chats(self):
        """Get all chats for this session"""
        # WAHA requires session name in the URL path
        return self._make_request('GET', f'/api/{self.session_name}/chats')

    def get_messages(self, chat_id, limit=100):
        """Get messages from a chat"""
        # WAHA requires session name in the URL path
        return self._make_request('GET', f'/api/{self.session_name}/chats/{chat_id}/messages?limit={limit}')
