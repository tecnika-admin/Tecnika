# -*- coding: utf-8 -*-

from odoo import models, fields

class AccountMove(models.Model):
    """Hereda de account.move para añadir la relación inversa."""
    _inherit = 'account.move'

    # Campo Many2one para la relación inversa con purchase.requisition
    x_requisition_id = fields.Many2one(
        comodel_name='purchase.requisition',
        string='Acuerdo de Compra (Relacionado)',
        index=True, # Indexar para búsquedas más rápidas
        copy=False, # No copiar esta relación al duplicar facturas
        help="Acuerdo de compra al que está relacionada esta factura."
    )
