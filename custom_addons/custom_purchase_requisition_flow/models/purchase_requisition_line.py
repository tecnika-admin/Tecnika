# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

class PurchaseRequisitionLine(models.Model):
    _inherit = 'purchase.requisition.line'

    # --- Nuevos Campos ---
    # Usaremos nombres descriptivos y una precisión basada en la UoM del producto

    # Campo calculado: Cantidad total ordenada en POs confirmadas
    qty_ordered_calc = fields.Float(
        string="Cantidad Ordenada (Calculada)",
        compute='_compute_qty_ordered_calc',
        store=True, # Almacenar para rendimiento y poder usarlo en constraints/depends
        digits='Product Unit of Measure',
        help="Cantidad total de este producto ordenada en Órdenes de Compra confirmadas relacionadas con este acuerdo."
    )
    # Campo calculado: Cantidad actualmente 'En Fabricación'
    qty_fab = fields.Float(
        string="En Fabricación",
        compute='_compute_qty_fab',
        store=True, # Almacenar para rendimiento y usar en onchange/constraints
        digits='Product Unit of Measure',
        help="Cantidad calculada que aún está en proceso de fabricación (Ordenada - Otras Etapas)."
    )
    # Campo editable: Cantidad en Almacén de la Marca
    qty_almmarc = fields.Float(
        string="Almacén Marca",
        digits='Product Unit ofMeasure',
        copy=False, # No copiar estas cantidades al duplicar
        help="Cantidad actualmente en el almacén de la marca."
    )
    # Campo editable: Cantidad en Almacén del Mayorista
    qty_almmay = fields.Float(
        string="Almacén Mayorista",
        digits='Product Unit of Measure',
        copy=False,
        help="Cantidad actualmente en el almacén del mayorista."
    )
    # Campo calculado: Cantidad recibida en Almacén Tecnika
    qty_almtec = fields.Float(
        string="Almacén Tecnika",
        compute='_compute_qty_almtec',
        store=True, # Almacenar para rendimiento y usar en onchange/constraints
        digits='Product Unit of Measure',
        copy=False,
        help="Cantidad total recibida físicamente en el almacén de Tecnika desde las POs de este acuerdo."
    )
    # Campo editable: Cantidad entregada al Cliente
    qty_cli = fields.Float(
        string="Cliente",
        digits='Product Unit of Measure',
        copy=False,
        help="Cantidad entregada al cliente final."
    )

    # --- Lógica de Cálculo con @api.depends ---

    @api.depends('requisition_id.order_ids.state', 'requisition_id.order_ids.order_line.product_qty', 'requisition_id.order_ids.order_line.product_id')
    def _compute_qty_ordered_calc(self):
        """Calcula la cantidad total ordenada en POs confirmadas."""
        PurchaseOrderLine = self.env['purchase.order.line']
        for line in self:
            if not line.requisition_id or not line.product_id:
                line.qty_ordered_calc = 0.0
                continue

            domain = [
                ('order_id.requisition_id', '=', line.requisition_id.id),
                ('product_id', '=', line.product_id.id),
                ('order_id.state', '=', 'purchase') # Solo POs confirmadas
            ]
            # Usamos read_group para sumar eficientemente
            grouped_data = PurchaseOrderLine.read_group(
                domain=domain,
                fields=['product_qty:sum'],
                groupby=['product_id'] # Agrupamos por producto (aunque solo habrá uno)
            )
            total_ordered = 0.0
            if grouped_data:
                total_ordered = grouped_data[0].get('product_qty', 0.0) or 0.0
            line.qty_ordered_calc = total_ordered

    @api.depends('requisition_id.order_ids.state', 'requisition_id.order_ids.order_line.move_ids.state', 'requisition_id.order_ids.order_line.move_ids.quantity')
    def _compute_qty_almtec(self):
        """Calcula la cantidad total recibida en Tecnika basada en stock.moves."""
        StockMove = self.env['stock.move']
        for line in self:
            if not line.requisition_id or not line.product_id:
                line.qty_almtec = 0.0
                continue

            # Buscar movimientos de stock relevantes
            domain_moves = [
                ('state', '=', 'done'), # Movimientos completados
                ('purchase_line_id.order_id.requisition_id', '=', line.requisition_id.id), # De POs de esta requisición
                ('product_id', '=', line.product_id.id), # Mismo producto
                ('location_dest_id.usage', '=', 'internal') # Destino es un almacén interno (recepción)
                # Podríamos necesitar filtrar por la ubicación específica de Tecnika si hay varias
                # ('location_dest_id', '=', ID_ALMACEN_TECNIKA)
            ]
            
            # Buscar y sumar la cantidad ('quantity')
            found_moves = StockMove.search(domain_moves)
            total_received = sum(m.quantity for m in found_moves)
            line.qty_almtec = total_received

    @api.depends('qty_ordered_calc', 'qty_almmarc', 'qty_almmay', 'qty_almtec', 'qty_cli')
    def _compute_qty_fab(self):
        """Calcula la cantidad 'En Fabricación' como el restante."""
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure') or 3
        for line in self:
            ordered = line.qty_ordered_calc or 0.0
            almmarc = line.qty_almmarc or 0.0
            almmay = line.qty_almmay or 0.0
            almtec = line.qty_almtec or 0.0
            cli = line.qty_cli or 0.0

            fab_calculated = ordered - (almmarc + almmay + almtec + cli)
            
            # Asegurarse de no tener fabricación negativa por errores de redondeo mínimos
            if float_compare(fab_calculated, 0.0, precision_digits=precision) < 0:
                fab_calculated = 0.0 # O lanzar error si preferimos en el constraint

            line.qty_fab = fab_calculated

    # --- Lógica de Resta Automática con @api.onchange ---
    # Nota: Los onchange modifican valores en la UI antes de guardar.
    # Usamos _origin para intentar obtener el valor *antes* del cambio actual.

    @api.onchange('qty_almmarc')
    def _onchange_qty_almmarc(self):
        """Al aumentar Almacén Marca, intentar restar de Fabricación."""
        # Verificar si _origin está disponible y el campo existe
        if hasattr(self, '_origin') and hasattr(self._origin, 'qty_almmarc'):
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure') or 3
            qty_almmarc_new = self.qty_almmarc or 0.0
            qty_almmarc_old = self._origin.qty_almmarc or 0.0
            
            # Calcular el delta (cuánto aumentó)
            delta = qty_almmarc_new - qty_almmarc_old

            # Si aumentó la cantidad en Almacén Marca
            if float_compare(delta, 0.0, precision_digits=precision) > 0:
                qty_fab_current = self.qty_fab or 0.0
                # Verificar si hay suficiente en fabricación para restar
                if float_compare(qty_fab_current, delta, precision_digits=precision) >= 0:
                    # Restar el delta de fabricación (esto es una modificación en caché)
                    # self.qty_fab = qty_fab_current - delta # CUIDADO: Modificar un computed field en onchange es complejo
                    # Es mejor recalcular fab basado en los otros campos o manejarlo en el constraint/write
                    pass # Dejamos que _compute_qty_fab haga el trabajo basado en los nuevos valores
                else:
                    # No hay suficiente en fabricación, lanzar advertencia
                    raise UserError(_(
                        "No se puede mover %.{precision}f a Almacén Marca desde Fabricación porque solo quedan %.{precision}f en Fabricación."
                    ).format(precision=precision) % (delta, qty_fab_current))
        # Si no hay _origin, no podemos calcular delta fácilmente, la validación final @api.constrains se encargará

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
                    # Restar de Almacén Marca (modificación en caché)
                    self.qty_almmarc = qty_almmarc_current - delta
                else:
                    raise UserError(_(
                        "No se puede mover %.{precision}f a Almacén Mayorista desde Almacén Marca porque solo hay %.{precision}f en Almacén Marca."
                    ).format(precision=precision) % (delta, qty_almmarc_current))

    # Onchange para qty_almtec (calculado) - Reajustar Mayorista
    # Esto es más complejo porque almtec se calcula por AA/depends.
    # La resta de almmay debería hacerse idealmente cuando almtec se recalcula.
    # Podríamos intentar un onchange aquí, pero es menos directo.
    # Vamos a confiar en que el usuario ajuste almmay manualmente o
    # que la validación final detecte inconsistencias si almtec aumenta y almmay no baja.
    # O podríamos mover la lógica de ajuste de almmay a _compute_qty_almtec si fuera un campo normal,
    # pero como es computed, es complejo.

    @api.onchange('qty_cli')
    def _onchange_qty_cli(self):
        """Al aumentar Cliente, intentar restar de Almacén Tecnika."""
        if hasattr(self, '_origin') and hasattr(self._origin, 'qty_cli'):
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure') or 3
            qty_cli_new = self.qty_cli or 0.0
            qty_cli_old = self._origin.qty_cli or 0.0
            delta = qty_cli_new - qty_cli_old

            if float_compare(delta, 0.0, precision_digits=precision) > 0:
                qty_almtec_current = self.qty_almtec or 0.0 # Usar el valor calculado actual
                if float_compare(qty_almtec_current, delta, precision_digits=precision) >= 0:
                    # Restar de Almacén Tecnika (modificación en caché)
                    # CUIDADO: qty_almtec es computed. Modificarlo aquí puede ser problemático.
                    # La lógica ideal sería ajustar el campo del que depende almtec (almmay?)
                    # O más bien, el usuario debería ajustar almtec manualmente si quiere mover a cliente?
                    # -> Revisando el flujo: Si almtec se calcula por recepción, ¿cómo se mueve a cliente?
                    # -> Probablemente el usuario edita 'cli' y debe editar 'almtec' hacia abajo.
                    # -> El onchange aquí valida si hay suficiente en almtec.
                    pass # No modificamos almtec directamente, solo validamos si hay suficiente
                else:
                     raise UserError(_(
                        "No se puede mover %.{precision}f a Cliente desde Almacén Tecnika porque solo hay %.{precision}f calculadas en Almacén Tecnika."
                    ).format(precision=precision) % (delta, qty_almtec_current))

    # --- Validación Final con @api.constrains ---
    # Se ejecuta al intentar guardar el registro.

    @api.constrains(
        'qty_ordered_calc', 'qty_fab', 'qty_almmarc',
        'qty_almmay', 'qty_almtec', 'qty_cli'
    )
    def _check_quantities_sum(self):
        """Valida que la suma de las etapas sea igual a lo ordenado y no haya negativos."""
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure') or 3
        for line in self:
            ordered = line.qty_ordered_calc or 0.0
            fab = line.qty_fab or 0.0
            almmarc = line.qty_almmarc or 0.0
            almmay = line.qty_almmay or 0.0
            almtec = line.qty_almtec or 0.0
            cli = line.qty_cli or 0.0

            # 1. Verificar cantidades negativas
            if any(float_compare(qty, 0.0, precision_digits=precision) < 0 for qty in [fab, almmarc, almmay, almtec, cli]):
                 raise ValidationError(_(
                    "Error en línea de producto '%s': Las cantidades en las etapas (Fabricación, Almacén Marca, Mayorista, Tecnika, Cliente) no pueden ser negativas."
                 ) % (line.product_id.display_name))

            # 2. Verificar que la suma total cuadre
            total_sum = fab + almmarc + almmay + almtec + cli
            if float_compare(total_sum, ordered, precision_digits=precision) != 0:
                raise ValidationError(_(
                    "Error de Validación en línea de producto '%(product)s':\n"
                    "La suma de cantidades (%(total_sum).{precision}f) no coincide con la Cantidad Ordenada (%(ordered).{precision}f).\n\n"
                    "Detalle:\n"
                    "- En Fabricación: %(fab).{precision}f\n"
                    "- Almacén Marca: %(almmarc).{precision}f\n"
                    "- Almacén Mayorista: %(almmay).{precision}f\n"
                    "- Almacén Tecnika: %(almtec).{precision}f\n"
                    "- Cliente: %(cli).{precision}f\n\n"
                    "Por favor, ajuste las cantidades."
                ) % { # Usamos formato estilo Python antiguo para traducciones
                    'product': line.product_id.display_name,
                    'total_sum': total_sum,
                    'ordered': ordered,
                    'fab': fab,
                    'almmarc': almmarc,
                    'almmay': almmay,
                    'almtec': almtec,
                    'cli': cli,
                    'precision': precision # Pasamos la precisión para el formato f-string simulado
                })

    # --- Consideración Adicional ---
    # Si 'qty_almtec' aumenta (por la computación basada en stock.move),
    # ¿debería disminuir 'qty_almmay' automáticamente?
    # Hacer esto desde un @api.depends es complejo porque implicaría escribir
    # en otro campo (qty_almmay) lo cual no es la función principal de depends.
    # Podría hacerse en el 'write' o con un onchange inverso si fuera necesario,
    # pero aumenta mucho la complejidad y riesgo de bucles.
    # Por ahora, la validación @api.constrains asegurará que si almtec aumenta,
    # el usuario deberá reducir manualmente almmay (o almmarc o cli) para que la suma cuadre.

