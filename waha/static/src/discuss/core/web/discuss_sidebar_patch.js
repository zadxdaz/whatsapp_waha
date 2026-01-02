/** @odoo-module **/

import { Discuss } from "@mail/core/web/discuss";
import { patch } from "@web/core/utils/patch";

patch(Discuss.prototype, {
    /**
     * @override
     * Filter threads by category including whatsapp
     */
    getThreads(category) {
        if (category === "whatsapp") {
            return this.store.threads.filter(
                (thread) => thread.channel_type === "whatsapp" && thread.displayToSelf
            ).sort((a, b) => {
                // Sort by last message date
                const dateA = a.lastInterestDt || a.create_date;
                const dateB = b.lastInterestDt || b.create_date;
                return dateB - dateA;
            });
        }
        // Filter out whatsapp from regular channels
        if (category === "channels") {
            const channels = super.getThreads(category);
            return channels.filter(thread => thread.channel_type !== "whatsapp");
        }
        return super.getThreads(category);
    },
});
