# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    # --- Campo añadido para relacionar ajustes con la factura origen ---
    # Este campo se establecerá en los asientos de AJUSTE (inventario y COGS)
    # apuntando a la factura original que se está ajustando.
    source_invoice_id = fields.Many2one(
        'account.move',
        string='Factura Origen del Ajuste',
        index=True,
        readonly=True,
        copy=False,
        help="Factura original que generó este asiento de ajuste de costo/inventario."
    )

    # --- Acción para abrir el wizard (sin cambios respecto a la versión anterior) ---
    def action_open_cogs_adjustment_wizard(self):
        """
        Abre el wizard para ajustar el costo de venta.
        """
        self.ensure_one()

        if self.state != 'posted' or not self.is_invoice(include_receipts=True):
             raise UserError(_("Solo puedes ajustar costos en facturas de cliente o proveedor que estén publicadas."))

        # Usar los criterios de filtrado confirmados por el usuario
        valid_lines = self.line_ids.filtered(
            lambda line: line.product_id and \
                         line.product_id.type == 'consu' and \
                         line.product_id.is_storable and \
                         line.product_id.valuation == 'real_time' and \
                         not line.display_type # Excluir secciones, notas, etc.
        )

        if not valid_lines:
            raise UserError(_("Esta factura no contiene líneas de producto (Consumible Almacenable con Valoración Automatizada) que puedan ser ajustadas."))

        action = self.env['ir.actions.act_window']._for_xml_id('custom_cogs_adjustment.action_cogs_adjustment_wizard')
        action['context'] = {
            'default_invoice_id': self.id,
            'active_id': self.id, # Asegurar que active_id esté presente para default_get
            'active_ids': self.ids,
        }
        return action