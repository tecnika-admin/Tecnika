# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
# Importar float_compare directamente si está disponible globalmente o desde tools
try:
    from odoo.tools import float_compare
except ImportError:
    # Fallback simple si no se encuentra (menos preciso)
    def float_compare(val1, val2, precision_digits=3):
        epsilon = 10**(-precision_digits)
        if val1 > val2 + epsilon: return 1
        elif val1 < val2 - epsilon: return -1
        else: return 0

class PurchaseRequisitionLine(models.Model):
    _inherit = 'purchase.requisition.line'

    # --- Nuevos Campos ---
    qty_ordered_calc = fields.Float(
        string="Cantidad Ordenada (Calculada)",
        compute='_compute_qty_ordered_calc',
        store=True,
        digits='Product Unit of Measure',
        help="Cantidad total de este producto ordenada en Órdenes de Compra confirmadas relacionadas con este acuerdo."
    )
    qty_fab = fields.Float(
        string="En Fabricación",
        compute='_compute_qty_fab',
        store=True,
        digits='Product Unit of Measure',
        help="Cantidad calculada que aún está en proceso de fabricación (Ordenada - Otras Etapas)."
    )
    qty_almmarc = fields.Float(
        string="Almacén Marca",
        digits='Product Unit of Measure',
        copy=False,
        help="Cantidad actualmente en el almacén de la marca."
    )
    qty_almmay = fields.Float(
        string="Almacén Mayorista",
        digits='Product Unit of Measure',
        copy=False,
        help="Cantidad actualmente en el almacén del mayorista."
    )
    qty_almtec = fields.Float(
        string="Almacén Tecnika",
        compute='_compute_qty_almtec',
        store=True,
        digits='Product Unit of Measure',
        copy=False,
        help="Cantidad total recibida físicamente en el almacén de Tecnika desde las POs de este acuerdo."
    )
    qty_cli = fields.Float(
        string="Cliente",
        digits='Product Unit of Measure',
        copy=False,
        help="Cantidad entregada al cliente final."
    )

    # --- Lógica de Cálculo con @api.depends ---

    @api.depends('requisition_id.purchase_ids.state', 'requisition_id.purchase_ids.order_line.product_qty', 'requisition_id.purchase_ids.order_line.product_id')
    def _compute_qty_ordered_calc(self):
        """Calcula la cantidad total ordenada en POs confirmadas."""
        PurchaseOrderLine = self.env['purchase.order.line']
        for line in self:
            # --- Inicio: Lógica duplicada para usar en constraint ---
            # (Se podría refactorizar a un método helper si se prefiere)
            ordered_val = 0.0
            if line.requisition_id and line.product_id:
                po_ids = line.requisition_id.purchase_ids.ids
                if po_ids:
                    domain = [
                        ('order_id', 'in', po_ids),
                        ('product_id', '=', line.product_id.id),
                        ('order_id.state', '=', 'purchase')
                    ]
                    grouped_data = PurchaseOrderLine.read_group(
                        domain=domain,
                        fields=['product_qty:sum'],
                        groupby=['product_id']
                    )
                    if grouped_data:
                        ordered_val = grouped_data[0].get('product_qty', 0.0) or 0.0
            # --- Fin: Lógica duplicada ---
            line.qty_ordered_calc = ordered_val

    @api.depends('requisition_id.purchase_ids.order_line.move_ids.state', 'requisition_id.purchase_ids.order_line.move_ids.quantity')
    def _compute_qty_almtec(self):
        """Calcula la cantidad total recibida en Tecnika basada en stock.moves."""
        StockMove = self.env['stock.move']
        for line in self:
            # --- Inicio: Lógica duplicada para usar en constraint ---
            received_val = 0.0
            if line.requisition_id and line.product_id:
                relevant_po_lines = self.env['purchase.order.line'].search([
                    ('order_id.requisition_id', '=', line.requisition_id.id),
                    ('product_id', '=', line.product_id.id),
                    ('order_id.state', 'in', ['purchase', 'done'])
                ])
                if relevant_po_lines:
                    domain_moves = [
                        ('state', '=', 'done'),
                        ('purchase_line_id', 'in', relevant_po_lines.ids),
                        ('product_id', '=', line.product_id.id),
                        ('location_dest_id.usage', '=', 'internal')
                    ]
                    found_moves = StockMove.search(domain_moves)
                    received_val = sum(m.quantity for m in found_moves)
            # --- Fin: Lógica duplicada ---
            line.qty_almtec = received_val

    @api.depends('qty_ordered_calc', 'qty_almmarc', 'qty_almmay', 'qty_almtec', 'qty_cli')
    def _compute_qty_fab(self):
        """Calcula la cantidad 'En Fabricación' como el restante."""
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure') or 3
        for line in self:
            # --- Inicio: Lógica duplicada para usar en constraint ---
            ordered = line.qty_ordered_calc or 0.0
            almmarc = line.qty_almmarc or 0.0
            almmay = line.qty_almmay or 0.0
            almtec = line.qty_almtec or 0.0
            cli = line.qty_cli or 0.0
            fab_calculated = ordered - (almmarc + almmay + almtec + cli)
            if float_compare(fab_calculated, 0.0, precision_digits=precision) < 0:
                fab_calculated = 0.0
            # --- Fin: Lógica duplicada ---
            line.qty_fab = fab_calculated

    # --- Lógica de Resta Automática con @api.onchange ---
    # (Se mantienen igual que antes)
    @api.onchange('qty_almmarc')
    def _onchange_qty_almmarc(self):
        """Al aumentar Almacén Marca, intentar restar de Fabricación."""
        if hasattr(self, '_origin') and hasattr(self._origin, 'qty_almmarc'):
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure') or 3
            qty_almmarc_new = self.qty_almmarc or 0.0
            qty_almmarc_old = self._origin.qty_almmarc or 0.0
            delta = qty_almmarc_new - qty_almmarc_old
            if float_compare(delta, 0.0, precision_digits=precision) > 0:
                pass # Confiamos en la validación final

    @api.onchange('qty_almmay')
    def _onchange_qty_almmay(self):
        """Al aumentar Almacén Mayorista, intentar restar de Almacén Marca."""
        if hasattr(self, '_origin') and hasattr(self._origin, 'qty_almmay'):
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure') or 3
            qty_almmay_new = self.qty_almmay or 0.0
            qty_almmay_old = self._origin.qty_almmay or 0.0
            delta = qty_almmay_new - qty_almmay_old
            if float_compare(delta, 0.0, precision_digits=precision) > 0:
                qty_almmarc_current = self.qty_almmarc or 0.0
                if float_compare(qty_almmarc_current, delta, precision_digits=precision) >= 0:
                    self.qty_almmarc = qty_almmarc_current - delta
                else:
                    self.qty_almmay = qty_almmay_old
                    raise UserError(_(
                        "No se puede mover %.{precision}f a Almacén Mayorista desde Almacén Marca porque solo hay %.{precision}f en Almacén Marca."
                    ).format(precision=precision) % (delta, qty_almmarc_current))

    @api.onchange('qty_cli')
    def _onchange_qty_cli(self):
        """Al aumentar Cliente, validar si hay suficiente en Almacén Tecnika."""
        if hasattr(self, '_origin') and hasattr(self._origin, 'qty_cli'):
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure') or 3
            qty_cli_new = self.qty_cli or 0.0
            qty_cli_old = self._origin.qty_cli or 0.0
            delta = qty_cli_new - qty_cli_old
            if float_compare(delta, 0.0, precision_digits=precision) > 0:
                qty_almtec_current = self.qty_almtec or 0.0
                if float_compare(qty_almtec_current, delta, precision_digits=precision) < 0:
                    self.qty_cli = qty_cli_old
                    raise UserError(_(
                        "No se puede mover %.{precision}f a Cliente porque solo hay %.{precision}f calculadas en Almacén Tecnika. Ajuste los pasos anteriores."
                    ).format(precision=precision) % (delta, qty_almtec_current))

    # --- Validación Final con @api.constrains ---
    # CORREGIDO: Recalcular valores dentro de la validación
    @api.constrains(
        'qty_almmarc', 'qty_almmay', 'qty_cli', # Depende principalmente de los manuales
        'requisition_id', 'product_id' # Y de lo necesario para recalcular los otros
        # Quitar dependencia explícita de los campos calculados para evitar problemas de timing
    )
    def _check_quantities_sum(self):
        """Valida que la suma de las etapas sea igual a lo ordenado y no haya negativos."""
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure') or 3
        PurchaseOrderLine = self.env['purchase.order.line'] # Necesario para recalcular 'ordered'
        # StockMove = self.env['stock.move'] # Necesario para recalcular 'almtec' (si se hace aquí)

        for line in self:
            # --- RECALCULAR VALORES DENTRO DEL CONSTRAINT ---

            # 1. Recalcular 'ordered'
            ordered_check = 0.0
            if line.requisition_id and line.product_id:
                po_ids = line.requisition_id.purchase_ids.ids
                if po_ids:
                    domain_ord = [
                        ('order_id', 'in', po_ids),
                        ('product_id', '=', line.product_id.id),
                        ('order_id.state', '=', 'purchase')
                    ]
                    grouped_data_ord = PurchaseOrderLine.read_group(domain_ord, ['product_qty:sum'], ['product_id'])
                    if grouped_data_ord:
                        ordered_check = grouped_data_ord[0].get('product_qty', 0.0) or 0.0

            # 2. Obtener valores manuales y 'almtec' (usamos el valor almacenado de almtec,
            #    asumiendo que su @api.depends se disparó correctamente antes o es independiente)
            almmarc = line.qty_almmarc or 0.0
            almmay = line.qty_almmay or 0.0
            almtec = line.qty_almtec or 0.0 # Usamos el valor almacenado/calculado
            cli = line.qty_cli or 0.0

            # 3. Recalcular 'fab' basado en los valores recalculados/obtenidos AHORA
            fab_check = ordered_check - (almmarc + almmay + almtec + cli)

            # --- VALIDACIONES USANDO VALORES RECALCULADOS/ACTUALES ---

            # 4. Verificar cantidades negativas (manuales y fab recalculado)
            if any(float_compare(qty, 0.0, precision_digits=precision) < 0 for qty in [almmarc, almmay, almtec, cli]):
                 raise ValidationError(_(
                    "Error en línea de producto '%s': Las cantidades en las etapas (Almacén Marca, Mayorista, Tecnika, Cliente) no pueden ser negativas."
                 ) % (line.product_id.display_name))
            if float_compare(fab_check, 0.0, precision_digits=precision) < 0:
                 raise ValidationError(_(
                    "Error en línea de producto '%s': La cantidad 'En Fabricación' calculada es negativa (%.{precision}f), indica que la suma de las otras etapas (%.{precision}f) excede lo ordenado (%.{precision}f)."
                 ).format(precision=precision) % (line.product_id.display_name, fab_check, (almmarc + almmay + almtec + cli), ordered_check))

            # 5. Verificar que la suma total cuadre (usando fab_check y ordered_check)
            total_sum_check = fab_check + almmarc + almmay + almtec + cli
            if float_compare(total_sum_check, ordered_check, precision_digits=precision) != 0:
                # Formatear números a string ANTES de pasarlos a %
                err_total_sum_str = f"{total_sum_check:.{precision}f}"
                err_ordered_str = f"{ordered_check:.{precision}f}"
                err_fab_str = f"{fab_check:.{precision}f}"
                err_almmarc_str = f"{almmarc:.{precision}f}"
                err_almmay_str = f"{almmay:.{precision}f}"
                err_almtec_str = f"{almtec:.{precision}f}"
                err_cli_str = f"{cli:.{precision}f}"

                raise ValidationError(_(
                    "Error de Validación en línea de producto '%(product)s':\n"
                    "La suma de cantidades (%(total_sum)s) no coincide con la Cantidad Ordenada (%(ordered)s).\n\n"
                    "Detalle (valores recalculados para validación):\n"
                    "- En Fabricación: %(fab)s\n"
                    "- Almacén Marca: %(almmarc)s\n"
                    "- Almacén Mayorista: %(almmay)s\n"
                    "- Almacén Tecnika: %(almtec)s\n" # Valor almacenado
                    "- Cliente: %(cli)s\n"
                    "--------------------\n"
                    "Suma Actual: %(total_sum)s\n"
                    "Cantidad Ordenada: %(ordered)s\n\n"
                    "Por favor, ajuste las cantidades."
                ) % {
                    'product': line.product_id.display_name,
                    'total_sum': err_total_sum_str,
                    'ordered': err_ordered_str,
                    'fab': err_fab_str,
                    'almmarc': err_almmarc_str,
                    'almmay': err_almmay_str,
                    'almtec': err_almtec_str,
                    'cli': err_cli_str,
                })

    # --- Consideración Adicional ---
    # (Sin cambios)

