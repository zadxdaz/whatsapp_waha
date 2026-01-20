/* @odoo-module */

import { reactive } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class WahaCoreWeb {
    constructor(env, services) {
        this.busService = services.bus_service;
        this.messagingService = services["mail.messaging"];
        this.store = services["mail.store"];
    }

    setup() {
        this.messagingService.isReady.then((data) => {
            if (data.current_user_settings?.is_discuss_sidebar_category_waha_whatsapp_open) {
                this.store.discuss.waha_whatsapp.isOpen = true;
            }
            this.busService.subscribe("res.users.settings", (payload) => {
                if (payload) {
                    this.store.discuss.waha_whatsapp.isOpen =
                        payload.is_discuss_sidebar_category_waha_whatsapp_open ??
                        this.store.discuss.waha_whatsapp.isOpen;
                }
            });
        });
    }
}

export const wahaCoreWeb = {
    dependencies: ["bus_service", "mail.messaging", "mail.store"],
    start(env, services) {
        const wahaCoreWeb = reactive(new WahaCoreWeb(env, services));
        wahaCoreWeb.setup();
        return wahaCoreWeb;
    },
};

registry.category("services").add("waha.core.web", wahaCoreWeb);
