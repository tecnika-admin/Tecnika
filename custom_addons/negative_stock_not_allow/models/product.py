
from odoo import fields, models


class ProductTemplate(models.Model):
    """Inherit Product Template Model"""
    _inherit = "product.template"

    allow_negative_stock_mrp = fields.Boolean(
        string="Permitir Stock Negativo",
        help="Si esta opción no está activa en este producto y el producto "
             "es almacenable, entonces la validación de los movimientos de stock "
             "relacionados será bloqueada si el nivel de stock se vuelve negativo "
             "con el movimiento de stock.",
    )
