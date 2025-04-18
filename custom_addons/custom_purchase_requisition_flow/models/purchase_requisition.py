# -*- coding: utf-8 -*-

from odoo import models, fields

class PurchaseRequisition(models.Model):
    """Hereda de purchase.requisition para añadir campos personalizados."""
    _inherit = 'purchase.requisition'

    # CORREGIDO: Cambiar a Many2many para facilitar selección de existentes
    invoice_ids = fields.Many2many(
        comodel_name='account.move',
        # No se necesita relation, inverse_name, column1, column2 (Odoo los genera)
        string="Facturas de Venta Relacionadas",
        domain=[('move_type', '=', 'out_invoice'), ('state', '=', 'posted')], # Sugerir solo facturas de cliente posteadas
        help="Facturas de venta asociadas a este acuerdo de compra. Use 'Añadir' para seleccionar facturas existentes."
    )

