/** @odoo-module **/

import { DiscussSidebarCategories } from "@mail/core/web/discuss_sidebar_categories";
import { patch } from "@web/core/utils/patch";

patch(DiscussSidebarCategories.prototype, {
    setup() {
        super.setup(...arguments);
    },

    /**
     * @override
     * Add WhatsApp category to sidebar
     */
    get discussSidebarCategories() {
        const categories = super.discussSidebarCategories;
        
        // Add WhatsApp category after Channels
        const channelIndex = categories.findIndex(cat => cat.id === "channels");
        if (channelIndex !== -1) {
            categories.splice(channelIndex + 1, 0, {
                id: "whatsapp",
                label: this.env._t("WHATSAPP"),
                canView: true,
                canAdd: false,
                serverStateKey: false,
                collapsed: false,
            });
        }
        
        return categories;
    },
});
