/** @odoo-module **/

import { Thread } from "@mail/core/common/thread_model";
import { patch } from "@web/core/utils/patch";

patch(Thread.prototype, {
    get channelTypeLabel() {
        if (this.channel_type === "whatsapp") {
            return "WhatsApp";
        }
        return super.channelTypeLabel;
    },
    
    get displayToSelf() {
        // WhatsApp channels should always be visible in sidebar
        if (this.channel_type === "whatsapp") {
            return true;
        }
        return super.displayToSelf;
    },
    
    get is_channel() {
        // Treat WhatsApp channels as regular channels for sidebar display
        if (this.channel_type === "whatsapp") {
            return true;
        }
        return super.is_channel;
    },
});
