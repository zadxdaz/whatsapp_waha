# Tasks: Fix WhatsApp Reply Parent Link in Discuss

## Phase 1: Reproduction and Safety

- [x] 1.1 Add `waha/tests/test_waha_message.py` coverage for an inbound WAHA reply whose `reply_to_message_id` points to an outbound `waha.message` without `mail_message_id`; assert the created `mail.message` has `parent_id`.
- [x] 1.2 Add `waha/tests/test_webhook.py` coverage from the log shape: `replyTo.id`/`quotedStanzaID` resolves message `22`, but Discuss must still render the inbound message as a reply.

## Phase 2: Parent Mail Resolution

- [x] 2.1 Add a helper in `waha/models/waha_message.py` that resolves a reply parent’s `mail.message` by existing `mail_message_id` first, then by safe channel/body/date/author lookup.
- [x] 2.2 Update `_compute_mail_message_id()` in `waha/models/waha_message.py` to use the helper instead of forcing parent `_compute_mail_message_id()` for outbound parents.
- [x] 2.3 Ensure the helper never auto-creates duplicate outbound Discuss messages when the parent `waha.message` has no `mail_message_id`.

## Phase 3: Data Repair Path

- [x] 3.1 Add a small repair method in `waha/models/waha_account.py` or `waha/models/waha_message.py` to backfill missing outbound `mail_message_id` links from the chat’s Discuss channel.
- [x] 3.2 Expose or reuse the repair from the existing sync action only for safe unique matches; log ambiguous parents without changing them.

## Phase 4: Verification

- [ ] 4.1 Run targeted Odoo tests for `waha.tests.test_waha_message` and `waha.tests.test_webhook` with an Odoo 18 database.
- [ ] 4.2 Verify manually with the provided log scenario: inbound message `703` must call `message_post` with `parent_id` set, not only `body`/`author_id`.
