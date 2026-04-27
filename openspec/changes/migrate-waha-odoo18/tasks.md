# Tasks: Migrate WAHA Messaging to Odoo 18

## 1. SDD setup
- [x] 1.1 Create SDD config and baseline compatibility spec.
- [x] 1.2 Create migration proposal.

## 2. Implementation
- [x] 2.1 Update manifest version to Odoo 18.
- [x] 2.2 Convert XML list view architectures from `<tree>` to `<list>`.
- [x] 2.3 Convert action `view_mode` and binding view types from `tree` to `list`.
- [x] 2.4 Remove generated Python bytecode from the addon tree.

## 3. Verification
- [x] 3.1 Run grep/static checks for legacy `tree` view declarations.
- [x] 3.2 Compile Python files.
- [ ] 3.3 Run Odoo 18 module tests if runtime is available.

## 4. Completion
- [ ] 4.1 Commit the migration branch with a conventional commit.

## Verification Notes
- Static XML parsing passed for all module XML files.
- Python syntax compilation passed for all module Python files.
- Odoo runtime tests were not executed because the local Docker compose service is currently `gauchocode/docker-odoo-ee:17.0`; full validation requires an Odoo 18 runtime/database.
