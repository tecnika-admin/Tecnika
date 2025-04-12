# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class CostCorrectionBatch(models.Model):
    _name = 'cost.correction.batch'
    _description = 'Cost Correction Batch'
    _inherit = ['mail.thread', 'mail.activity.mixin'] # Para chatter y actividades
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Batch Reference',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New')
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('loaded', 'Lines Loaded'),
        ('done', 'Processed'),
        ('cancel', 'Cancelled'),
        ], string='Status', default='draft', tracking=True, copy=False)

    invoice_ids = fields.Many2many(
        'account.move',
        string='Vendor Bills',
        required=True,
        copy=False,
        domain="[('move_type', 'in', ('in_invoice', 'in_refund')), ('state', '=', 'posted')]",
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    line_ids = fields.One2many(
        'cost.correction.batch.line',
        'batch_id',
        string='Lines to Correct',
        copy=False,
        readonly=True,
        states={'draft': [('readonly', False)], 'loaded': [('readonly', False)]} # Permitir editar costo en loaded
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    create_date = fields.Datetime(readonly=True)
    create_uid = fields.Many2one('res.users', string='Created by', readonly=True)

    # --- Sequence ---
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('cost.correction.batch') or _('New')
        return super().create(vals_list)

    # --- Actions ---
    def action_load_lines(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Lines can only be loaded in draft state."))
        if not self.invoice_ids:
            raise UserError(_("Please select at least one Vendor Bill."))

        BatchLine = self.env['cost.correction.batch.line']
        existing_lines = self.line_ids
        if existing_lines:
            # Opción 1: Borrar existentes y recargar (más simple)
            existing_lines.unlink()
            # Opción 2: Intentar hacer merge (más complejo, no implementado aquí)

        lines_to_create = []
        for invoice in self.invoice_ids:
            eligible_lines = invoice.line_ids.filtered(
                 lambda line: line.display_type == 'product' and \
                               line.product_id and \
                               line.product_id.type == 'product' and \
                               line.product_id.cost_method in ('fifo', 'average') # Ejemplo: Solo stockables FIFO/AVCO
                               # TODO: Añadir más filtros si es necesario (ej: no ya corregidos)
            )
            for line in eligible_lines:
                # Crear diccionario de valores para la línea del lote
                # Nota: El costo original real podría necesitar lógica más compleja
                lines_to_create.append({
                    'batch_id': self.id,
                    'invoice_line_id': line.id,
                    'correct_unit_cost': line.price_unit, # Pre-llenar con precio unitario como base? O 0.0?
                })

        if not lines_to_create:
            raise UserError(_("No eligible product lines found in the selected vendor bills."))

        BatchLine.create(lines_to_create)
        self.state = 'loaded'
        return True # Opcional: devolver acción para refrescar

    def action_apply_corrections(self):
        self.ensure_one()
        if self.state != 'loaded':
             raise UserError(_("Corrections can only be applied when lines are loaded."))

        lines_to_process = self.line_ids.filtered(lambda l: l.correct_unit_cost != l.original_cost) # Solo las que cambiaron
        if not lines_to_process:
             raise UserError(_("No lines with cost changes found."))

        if any(line.correct_unit_cost < 0 for line in lines_to_process):
            raise ValidationError(_("Correct unit cost cannot be negative."))

        # --- INICIO DE LA LÓGICA DE CORRECCIÓN ---
        # Placeholder: Aquí iría la lógica contable detallada
        # que es compleja y depende de la configuración de Odoo (Anglo-Saxon, etc.)
        # Se necesitaría:
        # 1. Identificar las cuentas (COGS, Stock Valuation, Stock Input/Output)
        # 2. Encontrar los asientos de valoración originales (stock.valuation.layer -> account.move)
        # 3. Calcular las diferencias de costo.
        # 4. Crear los asientos de ajuste en la valoración de inventario.
        # 5. Crear los asientos de ajuste en la factura (si aplica, depende del flujo).
        # 6. Marcar líneas como procesadas o con error.
        # -----------------------------------------
        print(f"--- Simulating Cost Correction for Batch {self.name} ---")
        for line in lines_to_process:
             print(f"  - Processing Invoice Line ID: {line.invoice_line_id.id}, "
                   f"Product: {line.product_id.display_name}, "
                   f"Qty: {line.quantity}, "
                   f"Original Cost: {line.original_cost}, "
                   f"New Cost: {line.correct_unit_cost}")
             # TODO: Implementar lógica real aquí
             pass # Marcar línea como procesada (necesitaría un campo 'state' en la línea)

        print(f"--- End Simulation ---")
        # -----------------------------------------

        self.state = 'done'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Corrections Applied'),
                'message': _('Cost corrections have been processed for batch %s.', self.name),
                'sticky': False,
            }
        }

    def action_cancel(self):
        # Podría necesitar lógica adicional para revertir algo si es necesario
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.write({'state': 'draft'})


class CostCorrectionBatchLine(models.Model):
    _name = 'cost.correction.batch.line'
    _description = 'Cost Correction Batch Line'
    _order = 'batch_id, invoice_id, id'

    batch_id = fields.Many2one(
        'cost.correction.batch',
        string='Batch',
        required=True,
        ondelete='cascade',
        index=True,
    )
    invoice_line_id = fields.Many2one(
        'account.move.line',
        string='Invoice Line',
        required=True,
        readonly=True,
        index=True,
    )
    # Campos relacionados para fácil acceso y visualización
    invoice_id = fields.Many2one(
        related='invoice_line_id.move_id',
        string='Vendor Bill',
        store=True, # Store=True para poder agrupar/ordenar por factura
        readonly=True
    )
    product_id = fields.Many2one(
        related='invoice_line_id.product_id',
        string='Product',
        store=True, # Store=True para poder agrupar/ordenar
        readonly=True
    )
    quantity = fields.Float(
        related='invoice_line_id.quantity',
        string='Quantity',
        readonly=True
    )
    currency_id = fields.Many2one(
        related='batch_id.company_id.currency_id', # O related='invoice_id.currency_id' si pueden diferir
        store=True, # Necesario para campos Monetary
        string='Currency'
    )

    # Campos de Costo
    original_cost = fields.Float(
        string='Original Unit Cost',
        compute='_compute_original_cost',
        store=True, # Calcular una vez al cargar
        readonly=True,
        digits='Product Price',
        help="Original unit cost derived from stock valuation layers or invoice line."
    )
    correct_unit_cost = fields.Float(
        string='Correct Unit Cost',
        required=True,
        default=0.0,
        digits='Product Price',
        copy=False,
    )
    adjustment_value = fields.Monetary(
        string='Adjustment Value',
        compute='_compute_adjustment_value',
        store=True,
        readonly=True,
        help="Total value adjustment for this line (Quantity * (Correct Cost - Original Cost))"
    )

    # --- Compute Methods ---
    @api.depends('invoice_line_id') # Dependencia simplificada, puede necesitar más
    def _compute_original_cost(self):
        # Placeholder: La lógica real es compleja. Depende de encontrar
        # el costo en las capas de valoración (stock.valuation.layer)
        # asociadas al movimiento de stock de esta línea de factura.
        # Como fallback simple, podríamos usar el price_unit, pero NO es el costo real.
        for line in self:
            # Lógica MUY SIMPLIFICADA - ¡REEMPLAZAR CON LÓGICA REAL DE COSTO!
            # Buscar stock.move asociado a invoice_line_id
            # Buscar stock.valuation.layer asociado a stock.move
            # Obtener unit_cost de la capa de valoración
            # Si no hay capa, ¿qué costo usar? ¿price_unit? ¿0?
            related_svl = self.env['stock.valuation.layer'].search([
                 ('stock_move_id.account_move_line_ids', '=', line.invoice_line_id.id)
                ], limit=1, order='create_date desc') # Asumiendo 1 SVL por linea AML

            if related_svl:
                 line.original_cost = related_svl.unit_cost
            else:
                 # Fallback MUY básico - ¡PELIGROSO USAR PRICE UNIT COMO COSTO!
                 line.original_cost = line.invoice_line_id.price_unit # ¡NO RECOMENDADO PARA COSTO REAL!


    @api.depends('quantity', 'original_cost', 'correct_unit_cost')
    def _compute_adjustment_value(self):
        for line in self:
            line.adjustment_value = line.quantity * (line.correct_unit_cost - line.original_cost)