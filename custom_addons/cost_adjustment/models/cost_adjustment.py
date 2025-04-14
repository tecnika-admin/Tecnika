# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero, float_compare

import logging
_logger = logging.getLogger(__name__)

# ==============================================================================
# Herencia de Product Template/Product para identificar Kits
# ==============================================================================
class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_kit = fields.Boolean(
        string="Es un Kit (Fantasma)",
        compute='_compute_is_kit',
        store=True, # Almacenar para usar en dominios de búsqueda/vistas
        help="Indica si el producto tiene una Lista de Materiales activa de tipo 'Kit (Fantasma)'."
    )

    @api.depends('bom_ids', 'bom_ids.active', 'bom_ids.type')
    def _compute_is_kit(self):
        """ Calcula si el producto es un Kit (tiene una LdM activa de tipo phantom). """
        # Asegurarse de que bom_ids no sea None
        for template in self:
            template.is_kit = any(
                bom.active and bom.type == 'phantom' for bom in template.bom_ids if bom
            ) if template.bom_ids else False


class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_kit = fields.Boolean(related='product_tmpl_id.is_kit', store=True)


# ==============================================================================
# Modelo Principal de Ajuste de Costo
# ==============================================================================
class CostAdjustment(models.Model):
    _name = 'cost.adjustment'
    _description = 'Ajuste de Costo de Venta'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    # --- Campos Principales ---
    name = fields.Char(
        string='Referencia', required=True, copy=False, readonly=True, index=True, default=lambda self: _('Nuevo')
    )
    state = fields.Selection([
        ('draft', 'Borrador'), ('posted', 'Publicado'), ('cancel', 'Cancelado')],
        string='Estado', required=True, default='draft', copy=False, tracking=True,
    )
    date_adjustment = fields.Date(
        string='Fecha de Ajuste', required=True, default=fields.Date.context_today, copy=False, readonly="state != 'draft'",
        help="Fecha en la que se aplicará contablemente el asiento de ajuste."
    )
    journal_id = fields.Many2one(
        'account.journal', string='Diario Contable', required=True, domain="[('type', '=', 'general')]", readonly="state != 'draft'",
        help="Diario donde se registrará el asiento contable del ajuste."
    )
    reason = fields.Text(
        string='Motivo del Ajuste', required=True, readonly="state != 'draft'",
        help="Explicación detallada de por qué se realiza este ajuste de costo."
    )
    original_invoice_id = fields.Many2one(
        'account.move', string='Factura Original', required=True,
        domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('l10n_mx_edi_cfdi_uuid', '!=', False)]",
        readonly="state != 'draft'", copy=False, tracking=True,
        help="Factura de cliente publicada y timbrada cuyas líneas se ajustarán."
    )
    adjustment_move_id = fields.Many2one(
        'account.move', string='Asiento de Ajuste', readonly=True, copy=False,
        help="Asiento contable generado por este ajuste."
    )
    line_ids = fields.One2many(
        'cost.adjustment.line', 'adjustment_id', string='Líneas de Ajuste', readonly="state != 'draft'", copy=True,
    )
    auto_post_entry = fields.Boolean(
        string='¿Publicar Asiento Automáticamente?', default=False, readonly="state != 'draft'",
        help="Si se marca, el asiento de ajuste se publicará automáticamente al confirmar. Si no, quedará en estado borrador."
    )
    company_id = fields.Many2one(
        'res.company', string='Compañía', related='journal_id.company_id', store=True, readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', related='journal_id.currency_id', store=True, readonly=True
    )

    # --- Secuencia para 'name' ---
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('cost.adjustment') or _('Nuevo')
        return super(CostAdjustment, self).create(vals_list)

    # --- Acciones de Botones ---
    def action_post(self):
        """
        Valida, crea el asiento contable de ajuste, crea las capas de valoración (SVL)
        y opcionalmente publica el asiento. Cambia el estado del ajuste a 'Publicado'.
        La validación de fecha bloqueada la hará el método _post del asiento.
        Ref: RF04, RF05, RF08
        """
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("No se puede publicar un ajuste sin líneas."))

        # Ya no llamamos a _check_period_lock_date() aquí

        # Crear Asiento Contable (RF04)
        move = self._create_adjustment_move()
        self.adjustment_move_id = move.id

        # Crear Capas de Valoración (SVL) condicionalmente (RF05)
        self._create_stock_valuation_layers_conditionally(move)

        # Publicar Asiento (Opcional) - Aquí se validará la fecha bloqueada
        if self.auto_post_entry:
            move._post(soft=False) # Lanza UserError si la fecha está bloqueada

        # Cambiar Estado del Ajuste (Solo si _post no lanzó error o si no se auto-publicó)
        self.write({'state': 'posted'})
        return True

    def action_cancel(self):
        # La lógica de reversión en account.move ahora maneja Kits
        moves_to_reverse = self.mapped('adjustment_move_id').filtered(lambda m: m.state == 'posted')
        if moves_to_reverse:
            moves_to_reverse._reverse_moves(cancel=True)
        draft_moves = self.mapped('adjustment_move_id').filtered(lambda m: m.state == 'draft')
        if draft_moves:
            draft_moves.button_draft()
            draft_moves.button_cancel()
        self.filtered(lambda adj: adj.state != 'cancel').write({'state': 'cancel'})
        return True

    def action_draft(self):
        self.ensure_one()
        if self.adjustment_move_id and self.adjustment_move_id.state != 'cancel':
             raise UserError(_("No puede pasar a borrador un ajuste cuyo asiento contable no está cancelado."))
        self.write({'state': 'draft'})
        return True

    # --- Métodos de Ayuda ---

    # ELIMINADO: def _check_period_lock_date(self): ...

    def _prepare_adjustment_move_vals(self):
        self.ensure_one()
        ref = _("Ajuste Costo Fact: {} - Ajuste: {} - Motivo: {}").format(
            self.original_invoice_id.name,
            self.name,
            self.reason or ''
        )
        return {
            'journal_id': self.journal_id.id,
            'date': self.date_adjustment,
            'ref': ref,
            'move_type': 'entry',
            'cost_adjustment_origin_id': self.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'line_ids': [],
        }

    def _create_adjustment_move(self):
        self.ensure_one()
        move_vals = self._prepare_adjustment_move_vals()
        move_lines_vals = []
        company_currency = self.company_id.currency_id

        for line in self.line_ids:
            line._compute_costs_and_adjustment()
            if float_is_zero(line.adjustment_amount, precision_rounding=company_currency.rounding):
                continue
            line_vals = line._prepare_adjustment_move_lines_vals()
            move_lines_vals.extend(line_vals)

        if not move_lines_vals:
             raise UserError(_("No se generaron líneas de asiento válidas para el ajuste {} (verifique costos y diferencias).").format(self.name))

        move_vals['line_ids'] = [(0, 0, vals) for vals in move_lines_vals]
        move = self.env['account.move'].create(move_vals)
        return move

    def _create_stock_valuation_layers_conditionally(self, adjustment_move):
        """
        Crea las capas de valoración (SVL) para cada línea de ajuste.
        - Productos Estándar: Crea un SVL si se encuentra el stock.move original.
        - Kits: Compara valoración original de componentes vs costo actual del kit.
                Crea SVLs para componentes SOLO si hay diferencia significativa.
        Ref: RF05 (Modificado para Kits v2)
        """
        self.ensure_one()
        svl_obj = self.env['stock.valuation.layer']
        svl_vals_list = []
        company_currency = self.company_id.currency_id

        for line in self.line_ids:
            line._compute_costs_and_adjustment()
            if float_is_zero(line.adjustment_amount, precision_rounding=company_currency.rounding):
                continue

            if line.product_id.is_kit:
                # --- Lógica para Kits ---
                component_moves = line._find_kit_component_moves()
                if not component_moves:
                    _logger.warning(f"Kit {line.product_id.name}: No se encontraron movimientos de componentes para el ajuste {self.name}. No se crearán SVLs.")
                    continue

                original_svls = svl_obj.search([('stock_move_id', 'in', component_moves.ids)])
                actual_component_valuation = abs(sum(original_svls.mapped('value')))
                # Usamos el costo calculado en la línea (que es el costo total del kit para la cantidad)
                current_kit_total_cost = line.current_average_cost * line.quantity # Asume current_average_cost es unitario para kit? NO, debe ser el total. Revisar compute.
                # Recalculemos el costo total actual aquí para asegurar
                current_kit_total_cost = line.product_id.standard_price * line.quantity # Usar standard_price del kit * cantidad

                actual_comp_val_comp_curr = line.currency_id._convert(
                    actual_component_valuation, company_currency, self.company_id, self.date_adjustment)
                current_kit_total_cost_comp_curr = line.currency_id._convert(
                    current_kit_total_cost, company_currency, self.company_id, self.date_adjustment)

                # Comparar usando float_compare para mayor precisión
                comparison = float_compare(current_kit_total_cost_comp_curr, actual_comp_val_comp_curr, precision_rounding=company_currency.rounding)

                if comparison != 0:
                    # Hay diferencia -> Crear SVLs de ajuste para componentes
                    _logger.info(f"Kit {line.product_id.name}: Valoración original componentes ({actual_comp_val_comp_curr}) difiere del costo actual kit ({current_kit_total_cost_comp_curr}). Creando SVLs de ajuste.")
                    component_svl_vals = line._prepare_kit_component_svl_vals(adjustment_move, component_moves)
                    svl_vals_list.extend(component_svl_vals)
                else:
                     _logger.info(f"Kit {line.product_id.name}: Valoración original componentes ({actual_comp_val_comp_curr}) coincide con costo actual kit ({current_kit_total_cost_comp_curr}). No se crearán SVLs de ajuste.")

            else:
                # --- Lógica para Productos Estándar ---
                standard_svl_vals = line._prepare_standard_product_svl_vals(adjustment_move)
                if standard_svl_vals:
                    svl_vals_list.append(standard_svl_vals)
                else:
                    _logger.warning(f"No se pudo preparar SVL estándar para la línea {line.id} (Ajuste: {self.name})")

        if svl_vals_list:
            svl_obj.create(svl_vals_list)

        return True


# ==============================================================================
# Modelo de Línea de Ajuste de Costo (con lógica para Kits)
# ==============================================================================
class CostAdjustmentLine(models.Model):
    _name = 'cost.adjustment.line'
    _description = 'Línea de Ajuste de Costo de Venta'

    # --- Campos ---
    adjustment_id = fields.Many2one('cost.adjustment', string='Ajuste de Costo', required=True, ondelete='cascade')
    original_invoice_line_id = fields.Many2one('account.move.line', string='Línea de Factura Original', required=True, help="Línea específica de la factura original cuyo costo se ajustará.")
    product_id = fields.Many2one('product.product', string='Producto', related='original_invoice_line_id.product_id', store=True, readonly=True)
    is_kit = fields.Boolean(related='product_id.is_kit', string="Es Kit", store=True, readonly=True)
    quantity = fields.Float(string='Cantidad Facturada', related='original_invoice_line_id.quantity', store=True, readonly=True)
    original_cost_total = fields.Monetary(string='Costo Original Registrado (Total)', compute='_compute_costs_and_adjustment', store=True, readonly=True, currency_field='currency_id', help="Costo total registrado originalmente (desde SVL o asiento COGS).")
    current_average_cost = fields.Monetary(string='Costo Actual (Unitario/Kit)', compute='_compute_costs_and_adjustment', store=True, readonly=True, currency_field='currency_id', help="Costo estándar/promedio actual del producto o costo unitario actual del kit.") # Aclarado help
    adjustment_amount = fields.Monetary(string='Importe del Ajuste', compute='_compute_costs_and_adjustment', store=True, readonly=True, currency_field='currency_id', help="Diferencia calculada: (Costo Actual Total) - Costo Original Registrado.")
    analytic_distribution = fields.Json(string='Distribución Analítica', readonly=True, copy=False, help="Distribución analítica heredada de la línea de factura original (si existe).")
    company_id = fields.Many2one('res.company', related='adjustment_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', related='adjustment_id.currency_id', store=True, readonly=True)
    computed_account_cogs_id = fields.Many2one('account.account', string='Cuenta COGS/Gasto (Calculada)', compute='_compute_accounts', store=False, readonly=True)
    computed_account_valuation_id = fields.Many2one('account.account', string='Cuenta Valoración/Salida (Calculada)', compute='_compute_accounts', store=False, readonly=True)

    # --- Onchange ---
    @api.onchange('original_invoice_line_id')
    def _onchange_original_invoice_line_id(self):
        if self.original_invoice_line_id:
            self.analytic_distribution = self.original_invoice_line_id.analytic_distribution
            self._compute_costs_and_adjustment()
            self._compute_accounts()
        else:
            self.analytic_distribution = False
            self.original_cost_total = 0.0
            self.current_average_cost = 0.0
            self.adjustment_amount = 0.0
            self.computed_account_cogs_id = False
            self.computed_account_valuation_id = False

    # --- Compute Principal (Modificado para Kits) ---
    @api.depends('original_invoice_line_id', 'product_id', 'quantity', 'adjustment_id.date_adjustment')
    def _compute_costs_and_adjustment(self):
        """
        Calcula costos y ajuste, diferenciando entre productos estándar y Kits.
        """
        # Pre-cargar datos necesarios para eficiencia
        invoice_line_ids = self.mapped('original_invoice_line_id')
        if not invoice_line_ids:
            for line in self:
                line.original_cost_total = 0.0
                line.current_average_cost = 0.0
                line.adjustment_amount = 0.0
            return

        # Buscar líneas de asiento COGS para todos los kits de una vez
        kit_lines = self.filtered(lambda l: l.product_id.is_kit and l.original_invoice_line_id)
        cogs_lines_dict = {}
        if kit_lines:
            kit_products = kit_lines.mapped('product_id')
            cogs_account_ids = kit_products.mapped('categ_id.property_account_expense_categ_id').ids
            invoice_ids = kit_lines.mapped('original_invoice_line_id.move_id').ids
            if invoice_ids and cogs_account_ids: # Solo buscar si hay IDs
                cogs_move_lines = self.env['account.move.line'].search([
                    ('move_id', 'in', invoice_ids),
                    ('product_id', 'in', kit_products.ids),
                    ('account_id', 'in', cogs_account_ids),
                    ('parent_state', '=', 'posted')
                ])
                for ml in cogs_move_lines:
                    # Usamos la línea de factura original como clave, ya que puede haber varias líneas del mismo producto en una factura
                    key = ml.id # Usar el ID de la account.move.line original como clave
                    if key not in cogs_lines_dict:
                         cogs_lines_dict[key] = 0.0
                    # El costo de venta es el débito en la cuenta de gasto
                    cogs_lines_dict[key] += ml.debit

        # Buscar SVLs para todos los productos estándar de una vez
        std_lines = self.filtered(lambda l: not l.product_id.is_kit and l.original_invoice_line_id)
        original_svl_costs = {}
        if std_lines:
            # Optimización: Buscar todos los moves de una vez
            sale_line_ids = std_lines.mapped('original_invoice_line_id.sale_line_ids').ids
            if sale_line_ids:
                stock_moves = self.env['stock.move'].search([
                    ('sale_line_id', 'in', sale_line_ids),
                    ('product_id', 'in', std_lines.mapped('product_id').ids),
                    ('company_id', 'in', std_lines.mapped('company_id').ids),
                    ('state', '=', 'done'),
                    ('location_dest_id.usage', '=', 'customer'),
                ])
                # Crear un mapeo de aml.id a stock_move.id (asumiendo 1-1 o el más relevante)
                map_aml_to_move = {
                    aml.id: moves[0].id
                    for aml in std_lines if (moves := stock_moves.filtered(lambda m: aml.sale_line_ids & m.sale_line_id and m.product_id == aml.product_id))
                }
                move_ids_to_search_svl = list(map_aml_to_move.values())

                if move_ids_to_search_svl:
                    svls = self.env['stock.valuation.layer'].search([
                        ('stock_move_id', 'in', move_ids_to_search_svl),
                        ('company_id', 'in', std_lines.mapped('company_id').ids),
                    ])
                    for svl in svls:
                        original_svl_costs[svl.stock_move_id.id] = abs(svl.value)


        for line in self:
            original_cost = 0.0
            current_cost_total = 0.0
            current_cost_unit = 0.0
            adjustment = 0.0
            product = line.product_id
            invoice_line = line.original_invoice_line_id

            if invoice_line and product:
                company_currency = line.company_id.currency_id or self.env.company.currency_id

                if product.is_kit:
                    # --- Lógica para Kits ---
                    # 1. Costo Original: Leer del asiento COGS pre-buscado usando el ID de la línea original
                    original_cost = cogs_lines_dict.get(invoice_line.id, 0.0)

                    # 2. Costo Actual: Usar standard_price del Kit (unitario)
                    current_cost_unit = product.standard_price
                    current_cost_total = current_cost_unit * line.quantity

                else:
                    # --- Lógica para Productos Estándar ---
                    # 1. Costo Original: Leer del SVL pre-buscado
                    move_id = map_aml_to_move.get(invoice_line.id)
                    if move_id:
                        original_cost = original_svl_costs.get(move_id, 0.0)

                    # 2. Costo Actual: Leer standard_price (unitario)
                    current_cost_unit = product.standard_price
                    current_cost_total = current_cost_unit * line.quantity

                # 3. Calcular Ajuste
                adjustment = current_cost_total - original_cost

            line.original_cost_total = company_currency.round(original_cost)
            line.current_average_cost = company_currency.round(current_cost_unit) # Guardamos costo unitario
            line.adjustment_amount = company_currency.round(adjustment)


    # --- Compute Cuentas (Sin cambios) ---
    @api.depends('product_id', 'company_id')
    def _compute_accounts(self):
        for line in self:
            accounts = {'expense': False, 'stock_output': False}
            if line.product_id and line.company_id:
                 accounts_dict = line.product_id.with_company(line.company_id)._get_product_accounts()
                 line.computed_account_cogs_id = accounts_dict.get('expense')
                 line.computed_account_valuation_id = accounts_dict.get('stock_output')
            else:
                 line.computed_account_cogs_id = False
                 line.computed_account_valuation_id = False

    # --- Métodos de Ayuda ---
    # _find_original_stock_move (sin cambios)
    def _find_original_stock_move(self):
        self.ensure_one()
        if not self.original_invoice_line_id or not self.product_id or self.product_id.is_kit:
            return self.env['stock.move']
        aml = self.original_invoice_line_id
        stock_moves = self.env['stock.move']
        if aml.sale_line_ids:
            domain = [
                ('sale_line_id', 'in', aml.sale_line_ids.ids),
                ('product_id', '=', self.product_id.id),
                ('company_id', '=', self.company_id.id),
                ('state', '=', 'done'),
                ('location_dest_id.usage', '=', 'customer'),
            ]
            stock_moves = self.env['stock.move'].search(domain, order='date desc', limit=1)
        if not stock_moves:
             _logger.warning(f"No se encontró stock.move para la línea de factura {aml.id} (Producto Estándar: {self.product_id.name})")
        return stock_moves

    # _find_kit_component_moves (sin cambios)
    def _find_kit_component_moves(self):
        self.ensure_one()
        if not self.original_invoice_line_id or not self.product_id or not self.product_id.is_kit:
            return self.env['stock.move']
        aml = self.original_invoice_line_id
        if not aml.sale_line_ids:
            _logger.warning(f"Línea de factura {aml.id} (Kit: {self.product_id.name}) no tiene líneas de venta asociadas.")
            return self.env['stock.move']
        bom = self.env['mrp.bom']._bom_find(products=self.product_id, bom_type='phantom', company_id=self.company_id.id)[self.product_id]
        if not bom:
             _logger.warning(f"No se encontró LdM tipo Phantom para el Kit {self.product_id.name}.")
             return self.env['stock.move']
        component_ids = bom.bom_line_ids.mapped('product_id').ids
        domain = [
            ('sale_line_id', 'in', aml.sale_line_ids.ids),
            ('product_id', 'in', component_ids),
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'done'),
            ('location_dest_id.usage', '=', 'customer'),
        ]
        component_moves = self.env['stock.move'].search(domain)
        if not component_moves:
             _logger.warning(f"No se encontraron stock.move de componentes para la línea de factura {aml.id} (Kit: {self.product_id.name})")
        return component_moves

    # _get_adjustment_accounts (sin cambios)
    def _get_adjustment_accounts(self):
        self.ensure_one()
        if not self.product_id:
            raise UserError(_("No se puede determinar cuentas sin un producto en la línea {}.").format(self.id))
        product_in_company = self.product_id.with_company(self.company_id)
        accounts = product_in_company._get_product_accounts()
        acc_cogs = accounts.get('expense')
        acc_valuation = accounts.get('stock_output')
        if not acc_cogs or not acc_valuation:
             categ = product_in_company.categ_id
             raise UserError(
                 _("No se pudieron determinar las cuentas de Costo de Venta (Gasto: {}) y/o Salida de Stock (Valoración: {}) para el producto '{}' (Categoría: {}). Verifique la configuración contable.")
                 .format(acc_cogs.code if acc_cogs else 'N/A',
                         acc_valuation.code if acc_valuation else 'N/A',
                         product_in_company.display_name,
                         categ.display_name)
             )
        return acc_cogs, acc_valuation

    # _prepare_adjustment_move_lines_vals (sin cambios)
    def _prepare_adjustment_move_lines_vals(self):
        self.ensure_one()
        vals_list = []
        company_currency = self.company_id.currency_id
        if float_is_zero(self.adjustment_amount, precision_rounding=company_currency.rounding):
             return []
        amount = self.adjustment_amount
        acc_cogs, acc_valuation = self._get_adjustment_accounts()
        partner_id = self.adjustment_id.original_invoice_id.partner_id.id
        name = _("Ajuste Costo: {}").format(self.product_id.display_name)
        debit_cogs, credit_cogs, debit_val, credit_val = 0.0, 0.0, 0.0, 0.0
        if float_compare(amount, 0.0, precision_rounding=company_currency.rounding) > 0:
            debit_cogs = amount
            credit_val = amount
        else:
            credit_cogs = abs(amount)
            debit_val = abs(amount)
        vals_cogs = {
            'name': name, 'account_id': acc_cogs.id, 'debit': debit_cogs, 'credit': credit_cogs,
            'analytic_distribution': self.analytic_distribution or False, 'partner_id': partner_id,
            'product_id': self.product_id.id, 'quantity': self.quantity, 'currency_id': self.currency_id.id,
        }
        vals_list.append(vals_cogs)
        vals_valuation = {
            'name': name, 'account_id': acc_valuation.id, 'debit': debit_val, 'credit': credit_val,
            'analytic_distribution': False, 'partner_id': partner_id,
            'product_id': self.product_id.id, 'quantity': self.quantity, 'currency_id': self.currency_id.id,
        }
        vals_list.append(vals_valuation)
        return vals_list

    # _prepare_standard_product_svl_vals (sin cambios)
    def _prepare_standard_product_svl_vals(self, adjustment_move):
         self.ensure_one()
         stock_move = self._find_original_stock_move()
         if not stock_move:
             _logger.warning(f"No se creará SVL estándar para la línea {self.id} (Producto: {self.product_id.name}) porque no se encontró el stock.move original.")
             return {}
         description = _("Ajuste Costo - Fact: {} - Ajuste: {}").format(
             self.adjustment_id.original_invoice_id.name,
             self.adjustment_id.name
         )
         company_currency = self.company_id.currency_id
         value_in_company_currency = self.currency_id._convert(
             self.adjustment_amount, company_currency, self.company_id, self.adjustment_id.date_adjustment
         )
         return {
             'create_date': self.adjustment_id.date_adjustment,
             'stock_move_id': stock_move.id,
             'product_id': self.product_id.id,
             'quantity': 0,
             'uom_id': self.product_id.uom_id.id,
             'unit_cost': 0,
             'value': value_in_company_currency,
             'remaining_qty': 0,
             'remaining_value': value_in_company_currency,
             'description': description,
             'account_move_id': adjustment_move.id,
             'company_id': self.company_id.id,
         }

    # _prepare_kit_component_svl_vals (sin cambios funcionales, solo recibe component_moves)
    def _prepare_kit_component_svl_vals(self, adjustment_move, component_moves):
        """
        Prepara los valores para crear los SVL de ajuste para los COMPONENTES de un Kit,
        distribuyendo el ajuste total del kit.
        Recibe los component_moves ya encontrados.
        """
        self.ensure_one()
        kit_adjustment_total = self.adjustment_amount
        company_currency = self.company_id.currency_id
        if float_is_zero(kit_adjustment_total, precision_rounding=company_currency.rounding):
            return []
        if not component_moves:
            return []

        total_current_component_cost = 0
        component_data = []
        for move in component_moves:
            # Usar quantity_done que representa la cantidad real movida
            comp_cost = move.product_id.standard_price * move.quantity_done
            total_current_component_cost += comp_cost
            component_data.append({'move': move, 'current_cost': comp_cost})

        if float_is_zero(total_current_component_cost, precision_rounding=company_currency.rounding):
            _logger.warning(f"El costo total actual de los componentes para el Kit {self.product_id.name} (Ajuste: {self.adjustment_id.name}) es cero. No se puede distribuir el ajuste.")
            return []

        svl_vals_list = []
        kit_adjustment_total_comp_curr = self.currency_id._convert(
             kit_adjustment_total, company_currency, self.company_id, self.adjustment_id.date_adjustment
         )
        accumulated_adjustment = 0.0

        for i, data in enumerate(component_data):
            move = data['move']
            comp_cost = data['current_cost']
            ratio = comp_cost / total_current_component_cost if total_current_component_cost else 0
            comp_adjustment_value = company_currency.round(kit_adjustment_total_comp_curr * ratio)

            if i == len(component_data) - 1:
                comp_adjustment_value = kit_adjustment_total_comp_curr - accumulated_adjustment

            if company_currency.is_zero(comp_adjustment_value):
                continue

            accumulated_adjustment += comp_adjustment_value
            description = _("Ajuste Costo Kit ({}) - Comp: {} - Fact: {} - Ajuste: {}").format(
                self.product_id.name, move.product_id.name,
                self.adjustment_id.original_invoice_id.name, self.adjustment_id.name
            )
            svl_vals = {
                'create_date': self.adjustment_id.date_adjustment,
                'stock_move_id': move.id,
                'product_id': move.product_id.id,
                'quantity': 0,
                'uom_id': move.product_uom.id,
                'unit_cost': 0,
                'value': comp_adjustment_value,
                'remaining_qty': 0,
                'remaining_value': comp_adjustment_value,
                'description': description,
                'account_move_id': adjustment_move.id,
                'company_id': self.company_id.id,
            }
            svl_vals_list.append(svl_vals)

        final_sum = sum(v['value'] for v in svl_vals_list)
        if not float_is_zero(final_sum - kit_adjustment_total_comp_curr, precision_rounding=company_currency.rounding):
            _logger.error(f"Error de redondeo en distribución SVL para Kit {self.product_id.name} (Ajuste: {self.adjustment_id.name}). Total Distribuido: {final_sum}, Total Esperado: {kit_adjustment_total_comp_curr}")

        return svl_vals_list


# ==============================================================================
# Herencia de Account Move (Modificada para Reversión de Kits)
# ==============================================================================
class AccountMove(models.Model):
    _inherit = 'account.move'

    cost_adjustment_ids = fields.One2many(
        'cost.adjustment', 'original_invoice_id', string='Ajustes de Costo Relacionados',
        readonly=True, copy=False
    )
    cost_adjustment_origin_id = fields.Many2one(
        'cost.adjustment', string='Origen Ajuste de Costo', readonly=True, index=True, copy=False
    )

    def _reverse_moves(self, default_values_list=None, cancel=False):
        """
        Hereda para añadir la reversión de SVL (estándar y de componentes de kit).
        Ref: RF09 (Modificado para Kits v2)
        """
        default_values_list = default_values_list or [{} for _ in self]
        # Asegurar que cancel se pasa correctamente si es True
        reversed_moves = super(AccountMove, self)._reverse_moves(default_values_list=default_values_list, cancel=cancel)


        svl_obj = self.env['stock.valuation.layer']
        adjustment_obj = self.env['cost.adjustment']
        svl_to_create = []
        adjustments_to_cancel = adjustment_obj

        map_original_to_reversed = {rev.reversed_entry_id.id: rev for rev in reversed_moves if rev.reversed_entry_id}

        for move in self.filtered(lambda m: m.cost_adjustment_origin_id):
            adjustment = move.cost_adjustment_origin_id
            # Solo intentar cancelar ajustes que estén actualmente publicados
            if adjustment.state == 'posted':
                adjustments_to_cancel |= adjustment

            reversed_move = map_original_to_reversed.get(move.id)
            if not reversed_move:
                _logger.error(f"No se encontró el asiento reverso para el ajuste {move.name} durante la reversión del SVL.")
                continue

            # Buscar TODOS los SVL creados por el asiento de ajuste original 'move'
            original_svls = svl_obj.search([('account_move_id', '=', move.id)])

            for svl in original_svls:
                description = _("Reversión Ajuste Costo - Ref Orig: {} - Ref Rev: {}").format(
                    move.name,
                    reversed_move.name
                )
                value_in_company_currency = -svl.value

                if float_is_zero(value_in_company_currency, precision_rounding=svl.company_id.currency_id.rounding):
                    continue

                svl_vals = {
                     'create_date': reversed_move.date,
                     'stock_move_id': svl.stock_move_id.id,
                     'product_id': svl.product_id.id,
                     'quantity': 0,
                     'uom_id': svl.uom_id.id,
                     'unit_cost': 0,
                     'value': value_in_company_currency,
                     'remaining_qty': 0,
                     'remaining_value': value_in_company_currency,
                     'description': description,
                     'account_move_id': reversed_move.id,
                     'company_id': svl.company_id.id,
                 }
                svl_to_create.append(svl_vals)

        if svl_to_create:
            svl_obj.create(svl_to_create)

        # Cancelar los registros de ajuste originales que estaban posteados
        if adjustments_to_cancel:
            adjustments_to_cancel.write({'state': 'cancel'})

        return reversed_moves

