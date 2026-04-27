# Part of Odoo. See LICENSE file for full copyright and licensing details.

from unittest.mock import patch, MagicMock

from .common import WahaTestCommon

_API = 'odoo.addons.waha.models.waha_partner.WahaApi'


class TestComputeLid(WahaTestCommon):
    """_compute_lid — pure lookup, no API calls."""

    def test_no_api_call_when_no_lid(self):
        """Creating a partner without a LID must NOT trigger an API call."""
        with patch(_API) as MockApi:
            self.make_waha_partner(phone='5491100006001')
        MockApi.return_value.get_lid_by_phone.assert_not_called()

    def test_existing_lid_preserved(self):
        """A partner with an existing LID must keep it after recompute."""
        wp = self.make_waha_partner(phone='5491100006002', lid='existing_lid_001')
        wp._compute_lid()
        self.assertEqual(wp.lid, 'existing_lid_001')

    def test_no_lid_remains_false_without_api(self):
        wp = self.make_waha_partner(phone='5491100006003')
        with patch(_API) as MockApi:
            wp._compute_lid()
        MockApi.return_value.get_lid_by_phone.assert_not_called()
        self.assertFalse(wp.lid)


class TestNormalizePhone(WahaTestCommon):
    """_normalize_phone — various input formats."""

    def _norm(self, phone):
        dummy_acc = self.account
        return self.env['waha.partner']._normalize_phone(phone, dummy_acc)

    def test_strips_plus_sign(self):
        result = self._norm('+5491112345678')
        self.assertEqual(result, '5491112345678')

    def test_strips_c_us_suffix(self):
        result = self._norm('5491112345678@c.us')
        self.assertEqual(result, '5491112345678')

    def test_strips_lid_suffix(self):
        result = self._norm('5491112345678@lid')
        self.assertEqual(result, '5491112345678')

    def test_strips_dashes_and_spaces(self):
        result = self._norm('+54 9 11 1234-5678')
        self.assertIsNotNone(result)
        self.assertTrue(result.isdigit())

    def test_empty_string_returns_false(self):
        self.assertFalse(self._norm(''))

    def test_none_returns_false(self):
        self.assertFalse(self._norm(None))

    def test_digits_only_passthrough(self):
        result = self._norm('5491112345678')
        self.assertEqual(result, '5491112345678')


class TestFindOrCreateByLidOrPhone(WahaTestCommon):
    """find_or_create_by_lid_or_phone — lookup → update → create logic."""

    def test_finds_existing_by_lid(self):
        wp = self.make_waha_partner(phone='5491100007001', lid='lid_search_001')
        result = self.env['waha.partner'].find_or_create_by_lid_or_phone(
            lid='lid_search_001',
            wa_account=self.account,
            auto_enrich=False,
        )
        self.assertEqual(result.id, wp.id)

    def test_finds_existing_by_phone(self):
        wp = self.make_waha_partner(phone='5491100007002')
        result = self.env['waha.partner'].find_or_create_by_lid_or_phone(
            phone='5491100007002',
            wa_account=self.account,
            auto_enrich=False,
        )
        self.assertEqual(result.id, wp.id)

    def test_found_by_lid_updates_missing_phone(self):
        """If partner is found by LID but has no phone, the phone should be added."""
        new_partner = self.env['res.partner'].create({'name': 'No Phone Partner'})
        wp = self.env['waha.partner'].create({
            'partner_id': new_partner.id,
            'wa_account_id': self.account.id,
            'lid': 'lid_upd_phone_001',
        })
        self.assertFalse(wp.phone_number)
        with patch(_API) as MockApi:
            MockApi.return_value.get_phone_by_lid.return_value = {'pn': '5491100007010'}
            MockApi.return_value.get_lid_by_phone.return_value = {}
            self.env['waha.partner'].find_or_create_by_lid_or_phone(
                lid='lid_upd_phone_001',
                phone='5491100007010',
                wa_account=self.account,
                auto_enrich=False,
            )
        self.assertEqual(wp.phone_number, '5491100007010')

    def test_found_by_phone_updates_missing_lid(self):
        """If partner is found by phone but has no LID, the LID should be added."""
        new_partner = self.env['res.partner'].create({'name': 'No LID Partner'})
        wp = self.env['waha.partner'].create({
            'partner_id': new_partner.id,
            'wa_account_id': self.account.id,
            'phone_number': '5491100007011',
        })
        self.assertFalse(wp.lid)
        with patch(_API) as MockApi:
            MockApi.return_value.get_lid_by_phone.return_value = {'lid': 'lid_new_001'}
            MockApi.return_value.get_phone_by_lid.return_value = {}
            self.env['waha.partner'].find_or_create_by_lid_or_phone(
                lid='lid_new_001',
                phone='5491100007011',
                wa_account=self.account,
                auto_enrich=False,
            )
        self.assertEqual(wp.lid, 'lid_new_001')

    def test_no_identifiers_returns_empty_recordset(self):
        result = self.env['waha.partner'].find_or_create_by_lid_or_phone(
            wa_account=self.account,
            auto_enrich=False,
        )
        self.assertFalse(result)

    def test_group_id_returns_empty_recordset(self):
        result = self.env['waha.partner'].find_or_create_by_lid_or_phone(
            phone='120363000000@g.us',
            wa_account=self.account,
            auto_enrich=False,
        )
        self.assertFalse(result)

    def test_creates_new_res_partner_when_not_found(self):
        """A completely new phone must create a res.partner and waha.partner."""
        partner_count_before = self.env['res.partner'].search_count([])
        with patch(_API) as MockApi:
            MockApi.return_value.get_lid_by_phone.return_value = {}
            MockApi.return_value.get_phone_by_lid.return_value = {}
            MockApi.return_value.get_contact.return_value = None
            result = self.env['waha.partner'].find_or_create_by_lid_or_phone(
                phone='5491100007099',
                wa_account=self.account,
                auto_enrich=False,
            )
        self.assertTrue(result)
        self.assertTrue(result.partner_id)
        partner_count_after = self.env['res.partner'].search_count([])
        self.assertGreater(partner_count_after, partner_count_before)

    def test_does_not_duplicate_existing_res_partner(self):
        """If res.partner with the same phone exists, reuse it."""
        new_partner = self.env['res.partner'].create({
            'name': 'Existing Phone Partner',
            'mobile': '+5491100007098',
        })
        with patch(_API) as MockApi:
            MockApi.return_value.get_lid_by_phone.return_value = {}
            MockApi.return_value.get_phone_by_lid.return_value = {}
            MockApi.return_value.get_contact.return_value = None
            result = self.env['waha.partner'].find_or_create_by_lid_or_phone(
                phone='5491100007098',
                wa_account=self.account,
                auto_enrich=False,
            )
        self.assertEqual(result.partner_id.id, new_partner.id)


class TestExtractContactName(WahaTestCommon):
    """_extract_contact_name — name priority logic."""

    def _extract(self, contact_info):
        return self.env['waha.partner']._extract_contact_name(contact_info)

    def test_name_has_highest_priority(self):
        info = {'name': 'Alice', 'pushname': 'Bob', 'verifiedName': 'Carol'}
        self.assertEqual(self._extract(info), 'Alice')

    def test_pushname_used_when_no_name(self):
        info = {'pushname': 'Bob', 'verifiedName': 'Carol'}
        self.assertEqual(self._extract(info), 'Bob')

    def test_pushName_camel_case_fallback(self):
        info = {'pushName': 'Dave'}
        self.assertEqual(self._extract(info), 'Dave')

    def test_verified_name_last_resort(self):
        info = {'verifiedName': 'Eve'}
        self.assertEqual(self._extract(info), 'Eve')

    def test_empty_dict_returns_none(self):
        self.assertIsNone(self._extract({}))

    def test_all_empty_values_returns_none(self):
        info = {'name': '', 'pushname': '', 'verifiedName': ''}
        self.assertIsNone(self._extract(info))
