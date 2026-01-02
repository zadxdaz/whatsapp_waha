/** @odoo-module **/

import { Discuss } from "@mail/core/web/discuss";
import { patch } from "@web/core/utils/patch";

patch(Discuss.prototype, {
    setup() {
        super.setup();
        // Register WhatsApp as a valid channel type
        if (!this.discussCoreCommonService.CHANNEL_TYPES) {
            this.discussCoreCommonService.CHANNEL_TYPES = [];
        }
        if (!this.discussCoreCommonService.CHANNEL_TYPES.includes("whatsapp")) {
            this.discussCoreCommonService.CHANNEL_TYPES.push("whatsapp");
        }
    },
});
