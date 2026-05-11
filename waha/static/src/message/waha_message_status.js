/** @odoo-module **/

import { Component } from "@odoo/owl";

export class WahaMessageStatus extends Component {
    static template = "waha.WahaMessageStatus";
    static props = {
        message: Object,
    };

    get statusInfo() {
        const state = this.props.message.waha_delivery_state;
        switch (state) {
            case "outgoing":
                return { icon: "fa-clock-o", colorClass: "text-muted", title: "Sending…" };
            case "sent":
                return { icon: "fa-check", colorClass: "text-muted", title: "Sent" };
            case "delivered":
                return { icon: "fa-check", colorClass: "text-muted", title: "Delivered" };
            case "read":
                return { icon: "fa-check", colorClass: "text-success", title: "Read" };
            case "error":
                return { icon: "fa-times", colorClass: "text-danger", title: "Failed to send" };
            default:
                return null;
        }
    }
}
