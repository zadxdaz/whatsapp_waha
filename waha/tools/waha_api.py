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
            try:
                error_data = e.response.json()
                error_msg = error_data.get('message', error_msg)
            except:
                error_msg = e.response.text or error_msg
            
            _logger.error('WAHA API Error: %s %s - %s', method, url, error_msg)
            raise
            
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

    def get_session_status(self):
        """Get session status"""
        return self._make_request('GET', f'/api/sessions/{self.session_name}')

    def stop_session(self):
        """Stop/delete session"""
        return self._make_request('DELETE', f'/api/sessions/{self.session_name}')

    def get_qr_code(self):
        """Get QR code for session"""
        return self._make_request('GET', f'/api/sessions/{self.session_name}/qr')

    def get_screenshot(self):
        """Get screenshot of WhatsApp Web"""
        return self._make_request('GET', f'/api/screenshot', data={
            'session': self.session_name
        })

    # ============================================================
    # MESSAGE SENDING
    # ============================================================

    def send_text(self, chat_id, text):
        """
        Send text message
        
        Args:
            chat_id: WhatsApp chat ID (e.g., "1234567890@c.us")
            text: Message text
        """
        return self._make_request('POST', '/api/sendText', data={
            'session': self.session_name,
            'chatId': chat_id,
            'text': text
        })

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
        """Get all contacts"""
        return self._make_request('GET', '/api/contacts', data={
            'session': self.session_name
        })

    def get_chats(self):
        """Get all chats"""
        return self._make_request('GET', '/api/chats', data={
            'session': self.session_name
        })

    def get_messages(self, chat_id, limit=100):
        """Get messages from a chat"""
        return self._make_request('GET', f'/api/chats/{chat_id}/messages', data={
            'session': self.session_name,
            'limit': limit
        })
