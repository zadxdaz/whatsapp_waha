/* @odoo-module */

import { discussSidebarCategoriesRegistry } from "@mail/discuss/core/web/discuss_sidebar_categories";

discussSidebarCategoriesRegistry.add(
    "waha_whatsapp",
    {
        predicate: (store) => store.discuss.waha_whatsapp.threads.some((thread) => thread?.is_pinned),
        value: (store) => store.discuss.waha_whatsapp,
    },
    { sequence: 25 }
);
