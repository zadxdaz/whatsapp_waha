# Delta: waha-odoo18-compatibility

## Modified Requirements

### Requirement: Odoo 18 module metadata
The module MUST declare an Odoo 18-compatible version and remain installable with the existing WAHA dependencies.

#### Scenario: Module manifest is read by Odoo 18
- Given an Odoo 18 server loads the addon path
- When the module manifest is evaluated
- Then the version MUST start with `18.0.`
- And `installable` MUST be true

### Requirement: Odoo 18 list views
XML views and window actions MUST use Odoo 18 list-view terminology instead of legacy tree terminology.

#### Scenario: Views are validated during module install or upgrade
- Given Odoo 18 imports the addon XML files
- When list view records and window actions are validated
- Then list view architecture MUST use `<list>` tags
- And action `view_mode` values MUST use `list` instead of `tree`
- And server action binding view types MUST use `list` instead of `tree`
