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

    /**
     * Core `rename()` only persists the name for channel_type "channel"/"group"
     * (via channel_rename) or falls back to a per-user custom name for "chat"
     * (via channel_set_custom_name). "waha" matches neither branch, so renaming
     * a WhatsApp channel from the Discuss UI was silently discarded. Treat it
     * like a regular channel: persist the name for everyone.
     * @param {string} name
     */
    async rename(name) {
        if (this.channel_type !== "waha") {
            return super.rename(...arguments);
        }
        const newName = name.trim();
        if (newName && newName !== this.displayName) {
            this.name = newName;
            await this.store.env.services.orm.call(
                "discuss.channel",
                "channel_rename",
                [[this.id]],
                { name: newName }
            );
        }
    },
});
