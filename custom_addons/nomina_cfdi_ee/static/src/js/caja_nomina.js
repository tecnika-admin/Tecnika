/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

export class CustomListControllerCaja extends ListController {

    async _onClickEntregaFondoCaja (event) {
        event.stopPropagation();
        var self = this;
        return this.model.action.doAction({
            name: "Altas y Bajas",
            type: 'ir.actions.act_window',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
            res_model: 'entrega.fondo.caja'
        });
    }
}

CustomListControllerCaja.template = "nomina_cfdi_ee.ListViewCaja.Buttons";

const listControllerViewCaja = {
    ...listView,
    Controller: CustomListControllerCaja,
};

registry.category("views").add("caja_nomina_list", listControllerViewCaja);
