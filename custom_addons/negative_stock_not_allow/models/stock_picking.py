
from odoo import models, _
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        """Override to validate stock availability before validating moves."""
        outgoing = self.filtered(
            lambda picking: picking.picking_type_code not in ('incoming', 'dropship')
        )
        if outgoing:
            # Group and validate moves to prevent stock negatives from duplicates
            outgoing._validate_outgoing_stock_availability()

        return super().button_validate()

    def _validate_outgoing_stock_availability(self):
        """Validate stock availability for outgoing transfers."""
        move_groups = {}

        # Group moves by product, location and lot
        for move in self.move_ids:
            if move.product_id.allow_negative_stock_mrp or not move.product_id.is_storable:
                continue
                
            self._group_move(move, move_groups)
                
        # Validate all grouped moves
        self._validate_all_groups(move_groups)

    def _add_to_move_groups(self, move_groups, product, location, lot, quantity):
        """Add quantity to move groups with appropriate key."""
        if quantity <= 0:
            return
            
        key = (product.id, location.id, lot.id if lot else None)
        if key not in move_groups:
            move_groups[key] = {
                'product': product,
                'location': location,
                'lot': lot,
                'total_quantity': 0
            }
        move_groups[key]['total_quantity'] += quantity

    def _group_move(self, move, move_groups):
        """Group move by location and lot, handling both with and without move lines."""
        if move.move_line_ids:
            # Process move lines
            for line in move.move_line_ids:
                self._add_to_move_groups(
                    move_groups, 
                    move.product_id, 
                    line.location_id, 
                    line.lot_id, 
                    line.quantity
                )
        else:
            # Process move without lines
            self._add_to_move_groups(
                move_groups,
                move.product_id,
                move.location_id,
                None,
                move.quantity
            )

    def _validate_all_groups(self, move_groups):
        """Validate stock for all grouped moves."""
        for group_data in move_groups.values():
            total_quantity = group_data['total_quantity']
            
            # Skip validation for non-positive quantities
            if total_quantity <= 0:
                continue
                
            # Check if there's enough available stock
            available_qty = self._get_available_stock(group_data)
            if total_quantity > available_qty:
                self._raise_stock_error(group_data, available_qty)

    def _get_available_stock(self, group_data):
        """Get available stock for the group."""
        domain = [
            ('product_id', '=', group_data['product'].id),
            ('location_id', '=', group_data['location'].id)
        ]
        
        if group_data['lot']:
            domain.append(('lot_id', '=', group_data['lot'].id))
            
        quants = self.env['stock.quant'].search(domain)
        return sum(quants.mapped('quantity'))

    def _raise_stock_error(self, group_data, available_qty):
        """Raise appropriate stock validation error."""
        product = group_data['product']
        location = group_data['location']
        lot = group_data['lot']
        total_quantity = group_data['total_quantity']
        
        if lot:
            raise ValidationError(_(
                "No se puede validar la entrega porque no hay suficiente stock del producto '%s' "
                "con lote '%s' en la ubicación '%s'.\n\n"
                "📦 Stock disponible del lote: %.2f\n"
                "⚠️ Cantidad total solicitada: %.2f\n\n"
                "Por favor, verifique el inventario del lote o transfiera más stock antes de continuar."
            ) % (product.display_name, lot.name, location.display_name, available_qty, total_quantity))
        else:
            raise ValidationError(_(
                "No se puede validar la entrega porque no hay suficiente stock del producto '%s' "
                "en la ubicación '%s'.\n\n"
                "📦 Stock disponible: %.2f\n"
                "⚠️ Cantidad total solicitada: %.2f\n\n"
                "Por favor, verifique el inventario o transfiera más stock a esta ubicación antes de continuar."
            ) % (product.display_name, location.display_name, available_qty, total_quantity))