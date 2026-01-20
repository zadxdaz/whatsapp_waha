/* @odoo-module */

import { Thread } from "@mail/core/common/thread_model";
import { patch } from "@web/core/utils/patch";
import { assignDefined } from "@mail/utils/common/misc";

patch(Thread.prototype, {
    update(data) {
        super.update(data);
        if (this.type === "whatsapp") {
            assignDefined(this, data, ["whatsapp_channel_valid_until"]);
            if (!this._store.discuss.waha_whatsapp.threads.includes(this)) {
                this._store.discuss.waha_whatsapp.threads.push(this);
            }
        }
    },
});
