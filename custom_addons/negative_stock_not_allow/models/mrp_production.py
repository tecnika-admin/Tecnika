
from odoo import models, _
from odoo.exceptions import ValidationError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def button_mark_done(self):
        """Override to validate stock availability before marking production as done."""
        for production in self:
            production._validate_raw_material_availability()

        return super().button_mark_done()

    def _validate_raw_material_availability(self):
        """Validate that every raw move of this production has enough stock."""
        self.ensure_one()

        # Group consumption by product to handle multiple lines of the same product
        product_consumption = {}

        # Calculate total consumption per product
        for move in self.move_raw_ids:
            product = move.product_id

            # Skip validation for products that allow negative stock
            if product.allow_negative_stock_mrp:
                continue

            # Skip validation for virtual locations
            if self.location_src_id.usage in ('production', 'inventory'):
                continue

            # Calculate quantity to consume for this move
            if move.move_line_ids:
                quantity_to_consume = sum(move.move_line_ids.mapped('quantity'))
            else:
                quantity_to_consume = move.quantity if move.quantity > 0 else 0

            # Only consider if there's quantity to consume
            if quantity_to_consume <= 0:
                continue

            # Add to total consumption for this product
            if product.id not in product_consumption:
                product_consumption[product.id] = {
                    'product': product,
                    'total_quantity': 0,
                    'location': self.location_src_id
                }
            product_consumption[product.id]['total_quantity'] += quantity_to_consume

        # Validate stock availability for each product (grouped consumption)
        for product_data in product_consumption.values():
            product = product_data['product']
            total_quantity_to_consume = product_data['total_quantity']
            location = product_data['location']
            
            # Get available quantity in source location
            quant = self.env['stock.quant'].search([
                ('product_id', '=', product.id),
                ('location_id', '=', location.id)
            ], limit=1)
            available_qty = quant.quantity if quant else 0.0
            
            # Validate stock availability
            if total_quantity_to_consume > available_qty:
                raise ValidationError(_(
                    "No se puede completar la orden de producción porque no hay suficiente stock del producto '%s' "
                    "en la ubicación %s.\n\n"
                    "📦 Stock disponible: %.2f\n"
                    "⚠️ Cantidad total requerida: %.2f\n\n"
                    "Por favor, verifique el inventario o transfiera más stock a la ubicación %s antes de continuar."
                ) % (
                    product.display_name,
                    location.display_name,
                    available_qty,
                    total_quantity_to_consume,
                    location.display_name
                ))
