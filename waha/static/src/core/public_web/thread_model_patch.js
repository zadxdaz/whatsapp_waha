/* @odoo-module */

import { Thread } from "@mail/core/common/thread_model";
import { patch } from "@web/core/utils/patch";

patch(Thread.prototype, {
    _computeDiscussAppCategory() {
        if (this.channel_type === "waha") {
            return this.store.discuss.waha_whatsapp;
        }
        return super._computeDiscussAppCategory();
    },
});
