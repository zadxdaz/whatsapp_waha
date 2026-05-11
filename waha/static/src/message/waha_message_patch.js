/** @odoo-module **/

import { Message } from "@mail/core/common/message";
import { patch } from "@web/core/utils/patch";
import { WahaMessageStatus } from "./waha_message_status";

patch(Message, {
    components: { ...Message.components, WahaMessageStatus },
});

