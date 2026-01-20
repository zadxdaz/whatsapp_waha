/* @odoo-module */

import { DiscussApp } from "@mail/core/common/discuss_app_model";
import { Record } from "@mail/core/common/record";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

patch(DiscussApp, {
    new(data) {
        const res = super.new(data);
        res.waha_whatsapp = {
            extraClass: "o-mail-DiscussSidebarCategory-waha-whatsapp",
            id: "waha_whatsapp",
            name: _t("WhatsApp"),
            isOpen: false,
            canView: false,
            canAdd: false,
            serverStateKey: "is_discuss_sidebar_category_waha_whatsapp_open",
        };
        return res;
    },
});

patch(DiscussApp.prototype, {
    setup(env) {
        super.setup(env);
        this.waha_whatsapp = Record.one("DiscussAppCategory");
    },
});
