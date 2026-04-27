# waha-odoo18-compatibility Specification

## Purpose
Ensure the WAHA Messaging addon installs and preserves its WhatsApp/discuss integration behavior on Odoo 18.

## Requirements

### Requirement: Odoo 18 module metadata
The module MUST declare an Odoo 18-compatible version and remain installable with the existing WAHA dependencies.

#### Scenario: Module manifest is read by Odoo 18
- Given an Odoo 18 server loads the addon path
- When the module manifest is evaluated
- Then the version MUST use an Odoo 18-compatible version prefix
- And the module MUST remain installable

### Requirement: Odoo 18 list views
XML views and window actions MUST use Odoo 18 list-view terminology instead of legacy tree terminology.

#### Scenario: Views are validated during module install or upgrade
- Given Odoo 18 imports the addon XML files
- When list view records and window actions are validated
- Then list view architecture MUST use `<list>` tags
- And action `view_mode` values MUST use `list` instead of `tree`

### Requirement: Existing WAHA behavior remains covered
Existing WAHA account, chat, message, partner, template, webhook, and composer behaviors SHOULD remain covered by module tests.

#### Scenario: Test suite is available for Odoo 18
- Given an Odoo 18 test database can install the module
- When the module tests are executed
- Then existing behavioral tests SHOULD run without real WAHA HTTP calls
