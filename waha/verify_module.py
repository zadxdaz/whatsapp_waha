#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WAHA Module Verification Script
Verifies that all required files and structure are in place
"""

import os
import sys
from pathlib import Path

# Colors for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def check_file(filepath, required=True):
    """Check if a file exists"""
    exists = os.path.isfile(filepath)
    status = f"{GREEN}✓{RESET}" if exists else f"{RED}✗{RESET}"
    req_marker = " (required)" if required else " (optional)"
    print(f"  {status} {filepath}{req_marker if required and not exists else ''}")
    return exists

def check_dir(dirpath):
    """Check if a directory exists"""
    exists = os.path.isdir(dirpath)
    status = f"{GREEN}✓{RESET}" if exists else f"{RED}✗{RESET}"
    print(f"  {status} {dirpath}/")
    return exists

def main():
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}WAHA Module Structure Verification{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    # Get module path
    module_path = Path(__file__).parent
    os.chdir(module_path)
    
    print(f"Module path: {module_path}\n")
    
    errors = []
    warnings = []
    
    # Check main files
    print(f"{YELLOW}Main Files:{RESET}")
    if not check_file("__init__.py"): errors.append("__init__.py")
    if not check_file("__manifest__.py"): errors.append("__manifest__.py")
    check_file("README.md", required=False)
    check_file("INSTALLATION.md", required=False)
    
    # Check models
    print(f"\n{YELLOW}Models:{RESET}")
    if not check_dir("models"): errors.append("models/")
    if not check_file("models/__init__.py"): errors.append("models/__init__.py")
    if not check_file("models/waha_account.py"): errors.append("models/waha_account.py")
    if not check_file("models/waha_message.py"): errors.append("models/waha_message.py")
    if not check_file("models/waha_template.py"): errors.append("models/waha_template.py")
    if not check_file("models/res_partner.py"): errors.append("models/res_partner.py")
    if not check_file("models/mail_thread.py"): errors.append("models/mail_thread.py")
    
    # Check views
    print(f"\n{YELLOW}Views:{RESET}")
    if not check_dir("views"): errors.append("views/")
    if not check_file("views/waha_account_views.xml"): errors.append("views/waha_account_views.xml")
    if not check_file("views/waha_message_views.xml"): errors.append("views/waha_message_views.xml")
    if not check_file("views/waha_template_views.xml"): errors.append("views/waha_template_views.xml")
    if not check_file("views/waha_menus.xml"): errors.append("views/waha_menus.xml")
    if not check_file("views/res_partner_views.xml"): errors.append("views/res_partner_views.xml")
    
    # Check wizard
    print(f"\n{YELLOW}Wizard:{RESET}")
    if not check_dir("wizard"): errors.append("wizard/")
    if not check_file("wizard/__init__.py"): errors.append("wizard/__init__.py")
    if not check_file("wizard/waha_composer.py"): errors.append("wizard/waha_composer.py")
    if not check_file("wizard/waha_composer_views.xml"): errors.append("wizard/waha_composer_views.xml")
    
    # Check controller
    print(f"\n{YELLOW}Controller:{RESET}")
    if not check_dir("controller"): errors.append("controller/")
    if not check_file("controller/__init__.py"): errors.append("controller/__init__.py")
    if not check_file("controller/webhook.py"): errors.append("controller/webhook.py")
    
    # Check tools
    print(f"\n{YELLOW}Tools:{RESET}")
    if not check_dir("tools"): errors.append("tools/")
    if not check_file("tools/__init__.py"): errors.append("tools/__init__.py")
    if not check_file("tools/waha_api.py"): errors.append("tools/waha_api.py")
    if not check_file("tools/phone_validation.py"): errors.append("tools/phone_validation.py")
    if not check_file("tools/waha_exception.py"): errors.append("tools/waha_exception.py")
    
    # Check security
    print(f"\n{YELLOW}Security:{RESET}")
    if not check_dir("security"): errors.append("security/")
    if not check_file("security/ir.model.access.csv"): errors.append("security/ir.model.access.csv")
    if not check_file("security/ir_rules.xml"): errors.append("security/ir_rules.xml")
    if not check_file("security/res_groups.xml"): errors.append("security/res_groups.xml")
    if not check_file("security/ir_module_category_data.xml"): 
        errors.append("security/ir_module_category_data.xml")
    
    # Check data
    print(f"\n{YELLOW}Data:{RESET}")
    if not check_dir("data"): errors.append("data/")
    if not check_file("data/ir_cron_data.xml"): errors.append("data/ir_cron_data.xml")
    if not check_file("data/ir_actions_server_data.xml"): 
        errors.append("data/ir_actions_server_data.xml")
    check_file("data/waha_demo.xml", required=False)
    
    # Check static
    print(f"\n{YELLOW}Static Files:{RESET}")
    check_dir("static")
    check_dir("static/description")
    check_file("static/description/icon.svg", required=False)
    check_file("static/description/index.html", required=False)
    
    # Summary
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Summary:{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")
    
    if not errors:
        print(f"{GREEN}✓ All required files are present!{RESET}")
        print(f"{GREEN}✓ Module structure is complete!{RESET}")
    else:
        print(f"{RED}✗ {len(errors)} required file(s) missing:{RESET}")
        for error in errors:
            print(f"  - {error}")
    
    if warnings:
        print(f"{YELLOW}⚠ {len(warnings)} warning(s):{RESET}")
        for warning in warnings:
            print(f"  - {warning}")
    
    print(f"\n{BLUE}Next Steps:{RESET}")
    print("1. Copy module to Odoo addons directory")
    print("2. Restart Odoo")
    print("3. Update Apps List")
    print("4. Install 'WAHA Messaging' module")
    print()
    
    # Check Python dependencies
    print(f"{YELLOW}Checking Python dependencies:{RESET}")
    try:
        import phonenumbers
        print(f"  {GREEN}✓{RESET} phonenumbers")
    except ImportError:
        print(f"  {RED}✗{RESET} phonenumbers (install with: pip install phonenumbers)")
        warnings.append("phonenumbers not installed")
    
    try:
        import requests
        print(f"  {GREEN}✓{RESET} requests")
    except ImportError:
        print(f"  {RED}✗{RESET} requests (install with: pip install requests)")
        warnings.append("requests not installed")
    
    print()
    
    # Exit code
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main())
