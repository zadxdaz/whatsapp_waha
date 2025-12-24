# Part of Odoo. See LICENSE file for full copyright and licensing details.


class WahaError(Exception):
    """Custom exception for WAHA-related errors"""
    
    def __init__(self, message, error_code=None, error_data=None):
        self.message = message
        self.error_code = error_code
        self.error_data = error_data
        super().__init__(self.message)
    
    def __str__(self):
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message
