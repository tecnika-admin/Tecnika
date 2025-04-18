# -*- coding: utf-8 -*-

from odoo import models, fields

class PurchaseRequisition(models.Model):
    """Hereda de purchase.requisition para añadir campos personalizados."""
    _inherit = 'purchase.requisition'

    # Campo para relacionar facturas de venta (tipo 'out_invoice')
    invoice_ids = fields.One2many(
        comodel_name='account.move',
        inverse_name='x_requisition_id', # Nombre del campo Many2one en account.move
        string="Facturas de Venta Relacionadas",
        # Dominio para sugerir solo facturas de cliente (opcional, se puede refinar)
        domain=[('move_type', '=', 'out_invoice')],
        help="Facturas de venta asociadas a este acuerdo de compra."
    )

