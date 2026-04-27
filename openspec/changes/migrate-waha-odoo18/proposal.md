# Proposal: Migrate WAHA Messaging to Odoo 18

## Intent
Move the WAHA Messaging addon from Odoo 17 metadata/view conventions to Odoo 18 so it can install and run on an Odoo 18 database.

## Scope

### In Scope
- Update manifest metadata for Odoo 18 compatibility.
- Convert XML/Python action view modes and list view tags to Odoo 18 `list` terminology.
- Keep existing WAHA behavior and tests intact.
- Document SDD requirements and implementation tasks.

### Out of Scope
- Changing the parent Docker environment from Odoo 17 to Odoo 18.
- Functional redesign of WAHA API synchronization.
- Live validation against a remote WAHA server.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `waha-odoo18-compatibility`: Odoo version compatibility requirements for manifest and views.

## Approach
Apply the minimal Odoo 18 compatibility changes: bump the addon version to `18.0.*`, replace legacy `tree` view declarations with `list`, and update action `view_mode`/binding declarations accordingly. Preserve existing Python behavior unless Odoo 18 validation requires code changes.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `waha/__manifest__.py` | Modified | Odoo 18-compatible module version. |
| `waha/views/*.xml` | Modified | List/tree terminology migration. |
| `waha/data/*.xml` | Modified | Server action binding view types. |
| `waha/models/*.py`, `waha/wizard/*.py` | Modified | Action dictionaries using list view modes. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Mail/discuss OWL internals differ in Odoo 18 | Medium | Keep JS integration minimal and verify against Odoo 18 runtime when available. |
| Parent environment still runs Odoo 17 | Medium | Do not edit parent `.env` unless explicitly requested; module migration is separate. |
| Existing uncommitted changes predate this migration branch | Medium | Preserve and build on current worktree instead of reverting it. |

## Rollback Plan
Revert the migration commit or switch back to `main`. No irreversible data migration is introduced by this change.

## Dependencies
- Odoo 18 runtime for full install/test verification.
- Python dependencies already declared by the module: `phonenumbers`, `requests`.

## Success Criteria
- [ ] Manifest declares Odoo 18-compatible version.
- [ ] No legacy `<tree>` architecture tags remain in addon XML views.
- [ ] No `view_mode` or binding declarations use `tree` for list views.
- [ ] Static XML/Python checks pass locally.
- [ ] Odoo tests are documented or run when an Odoo 18 runtime is available.
