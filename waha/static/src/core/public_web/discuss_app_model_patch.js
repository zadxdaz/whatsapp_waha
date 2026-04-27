/* @odoo-module */

import { DiscussApp } from "@mail/core/public_web/discuss_app_model";
import { Record } from "@mail/core/common/record";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

patch(DiscussApp.prototype, {
    setup(env) {
        super.setup(env);
        this.waha_whatsapp = Record.one("DiscussAppCategory", {
            compute() {
                return {
                    extraClass: "o-mail-DiscussSidebarCategory-waha-whatsapp",
                    id: "waha_whatsapp",
                    name: _t("WhatsApp"),
                    hideWhenEmpty: true,
                    sequence: 25,
                    serverStateKey: "is_discuss_sidebar_category_waha_whatsapp_open",
                };
            },
        });
    },
});
