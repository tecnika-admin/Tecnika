# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero, float_compare

import logging
_logger = logging.getLogger(__name__)

# ==============================================================================
# Herencia de Product Template/Product para añadir campos helper
# ==============================================================================
class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_kit = fields.Boolean(
        string="Es un Kit (Fantasma)",
        compute='_compute_is_kit',
        store=True,
        help="Indica si el producto tiene una Lista de Materiales activa de tipo 'Kit (Fantasma)'."
    )
    is_storable = fields.Boolean(
        string="Es Almacenable (Campo)",
        compute='_compute_is_storable',
        store=True,
        help="Técnico: Verdadero si el tipo de producto es 'Almacenable'."
    )

    @api.depends('bom_ids', 'bom_ids.active', 'bom_ids.type')
    def _compute_is_kit(self):
        """ Calcula si el producto es un Kit (tiene una LdM activa de tipo phantom). """
        for template in self:
            has_active_phantom_bom = self.env['mrp.bom'].search_count([
                ('product_tmpl_id', '=', template.id),
                ('active', '=', True),
                ('type', '=', 'phantom')
            ]) > 0
            template.is_kit = has_active_phantom_bom

    @api.depends('type')
    def _compute_is_storable(self):
        """ Campo helper para saber si el producto es de tipo 'product' """
        for template in self:
            # Definición estándar: solo 'product' es storable.
            # Si la definición del usuario es diferente ('consu' + flag), se necesitaría sobreescribir.
            template.is_storable = template.type == 'product'


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # Campos relacionados para fácil acceso en la lógica y vistas
    is_kit = fields.Boolean(related='product_tmpl_id.is_kit', store=True, readonly=True)
    is_storable = fields.Boolean(related='product_tmpl_id.is_storable', store=True, readonly=True) # Campo related añadido
    product_type = fields.Selection(related='type', store=True, readonly=True)
    product_valuation = fields.Selection(related='valuation', store=True, readonly=True)


# ==============================================================================
# Modelo Principal de Ajuste de Costo
# ==============================================================================
class CostAdjustment(models.Model):
    _name = 'cost.adjustment'
    _description = 'Ajuste de Costo de Venta'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    # --- Campos Principales ---
    # (Sin cambios)
    name = fields.Char(string='Referencia', required=True, copy=False, readonly=True, index=True, default=lambda self: _('Nuevo'))
    state = fields.Selection([('draft', 'Borrador'), ('posted', 'Publicado'), ('cancel', 'Cancelado')], string='Estado', required=True, default='draft', copy=False, tracking=True)
    date_adjustment = fields.Date(string='Fecha de Ajuste', required=True, default=fields.Date.context_today, copy=False, readonly="state != 'draft'")
    journal_id = fields.Many2one('account.journal', string='Diario Contable', required=True, domain="[('type', '=', 'general')]", readonly="state != 'draft'")
    reason = fields.Text(string='Motivo del Ajuste', required=True, readonly="state != 'draft'")
    original_invoice_id = fields.Many2one('account.move', string='Factura Original', required=True, domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('l10n_mx_edi_cfdi_uuid', '!=', False)]", readonly="state != 'draft'", copy=False, tracking=True)
    adjustment_move_id = fields.Many2one('account.move', string='Asiento de Ajuste', readonly=True, copy=False)
    line_ids = fields.One2many('cost.adjustment.line', 'adjustment_id', string='Líneas de Ajuste', readonly="state != 'draft'", copy=True)
    auto_post_entry = fields.Boolean(string='¿Publicar Asiento Automáticamente?', default=False, readonly="state != 'draft'")
    company_id = fields.Many2one('res.company', string='Compañía', related='journal_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', compute='_compute_currency_id', store=True, readonly=True)

    @api.depends('journal_id', 'journal_id.currency_id', 'company_id', 'company_id.currency_id')
    def _compute_currency_id(self):
        # (Sin cambios)
        for rec in self:
            rec.currency_id = rec.journal_id.currency_id or rec.company_id.currency_id

    # --- Secuencia para 'name' ---
    @api.model_create_multi
    def create(self, vals_list):
        # (Sin cambios)
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('cost.adjustment') or _('Nuevo')
            if 'company_id' not in vals:
                if vals.get('journal_id'):
                    journal = self.env['account.journal'].browse(vals['journal_id'])
                    vals['company_id'] = journal.company_id.id
                else:
                    vals['company_id'] = self.env.company.id
        return super(CostAdjustment, self).create(vals_list)

    # --- Acciones de Botones ---
    def action_post(self):
        """
        Acción principal: Crea asiento, SVL (condicional) y archiva productos mal configurados.
        """
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("No se puede publicar un ajuste sin líneas."))

        # 1. Crear Asiento Contable
        move = self._create_adjustment_move()
        self.adjustment_move_id = move.id

        # 2. Crear Capas de Valoración (SVL) condicionalmente
        self._create_stock_valuation_layers_conditionally(move)

        # 3. Publicar Asiento (Opcional)
        if self.auto_post_entry:
            move._post(soft=False) # Validará fechas bloqueadas

        # 4. Archivar productos "Almacenables Mal Configurados" ajustados
        products_to_archive = self.env['product.product']
        for line in self.line_ids:
            product = line.product_id
            # Condición específica para "Almacenable Mal Configurado" según definición del usuario
            # (type='consu', valuation='real_time', is_storable=False)
            if product.product_type == 'consu' and product.product_valuation == 'real_time' and not product.is_storable:
                 products_to_archive |= product

        if products_to_archive:
            products_to_archive = products_to_archive.filtered(lambda p: p.active)
            if products_to_archive:
                _logger.info(f"Ajuste {self.name}: Archivando productos 'Almacenables Mal Configurados' ajustados: {products_to_archive.mapped('display_name')}")
                try:
                    products_to_archive.action_archive()
                    self.message_post(body=_("Se han archivado los siguientes productos (detectados como almacenables mal configurados) ajustados: {}").format(
                        ", ".join(products_to_archive.mapped('display_name'))
                    ))
                except Exception as e:
                    _logger.error(f"Error al intentar archivar productos para el ajuste {self.name}: {e}")
                    self.message_post(body=_("Error al intentar archivar productos mal configurados ajustados. Revise los logs."))

        # 5. Cambiar Estado del Ajuste
        self.write({'state': 'posted'})
        return True

    def action_cancel(self):
        # (Sin cambios)
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
        # (Sin cambios)
        self.ensure_one()
        if self.adjustment_move_id and self.adjustment_move_id.state != 'cancel':
             raise UserError(_("No puede pasar a borrador un ajuste cuyo asiento contable no está cancelado."))
        self.write({'state': 'draft'})
        return True

    # --- Métodos de Ayuda ---
    def _prepare_adjustment_move_vals(self):
        # (Sin cambios)
        self.ensure_one()
        if not self.journal_id:
            raise UserError(_("Debe seleccionar un Diario Contable."))
        move_currency = self.currency_id
        if not move_currency:
             raise UserError(_("No se pudo determinar la moneda. Verifique la configuración del diario ({}) y la compañía ({}).").format(self.journal_id.name, self.company_id.name))

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
            'currency_id': move_currency.id,
            'line_ids': [],
        }

    def _create_adjustment_move(self):
        # (Sin cambios)
        self.ensure_one()
        move_vals = self._prepare_adjustment_move_vals()
        move_lines_vals = []
        move_currency = self.env['res.currency'].browse(move_vals['currency_id'])

        for line in self.line_ids:
            line._compute_costs_and_adjustment()
            if float_is_zero(line.adjustment_amount, precision_rounding=move_currency.rounding):
                continue
            # Llama a _prepare_adjustment_move_lines_vals que usa _get_adjustment_accounts actualizado
            line_vals = line._prepare_adjustment_move_lines_vals(move_currency)
            move_lines_vals.extend(line_vals)

        if not move_lines_vals:
             raise UserError(_("No se generaron líneas de asiento válidas para el ajuste {} (verifique costos y diferencias).").format(self.name))

        move_vals['line_ids'] = [(0, 0, vals) for vals in move_lines_vals]
        move = self.env['account.move'].create(move_vals)
        return move

    # Actualizado para usar la lógica final de SVL
    def _create_stock_valuation_layers_conditionally(self, adjustment_move):
        """
        Crea las capas de valoración (SVL) condicionalmente.
        - Productos con valoración 'real_time': Aplica lógica estándar o de kit.
        - Productos con valoración 'manual': NO crea SVL.
        """
        self.ensure_one()
        svl_obj = self.env['stock.valuation.layer']
        svl_vals_list = []
        company_currency = self.company_id.currency_id

        for line in self.line_ids:
            product = line.product_id
            # Solo intentar crear SVL para productos con valoración 'real_time'
            if product.product_valuation != 'real_time':
                _logger.info(f"[Ajuste {self.name}] Producto {product.name} (Val: {product.product_valuation}) - Omitiendo SVL.")
                continue

            # --- Lógica solo para productos con valuation='real_time' ---
            line._compute_costs_and_adjustment()
            adjustment_amount_comp_curr = line.currency_id._convert(
                line.adjustment_amount, company_currency, line.company_id, line.adjustment_id.date_adjustment
            )
            if float_is_zero(adjustment_amount_comp_curr, precision_rounding=company_currency.rounding):
                continue

            # Diferenciar entre Kit y Estándar (ambos con valuation='real_time')
            if product.is_kit:
                # --- Lógica para Kits (Almacenables) ---
                component_moves = line._find_kit_component_moves()
                if not component_moves:
                    _logger.warning(f"[Ajuste {self.name}] Kit {product.name}: No se encontraron movimientos de componentes. No se crearán SVLs.")
                    continue

                original_svls = svl_obj.search([('stock_move_id', 'in', component_moves.ids)])
                actual_component_valuation = abs(sum(original_svls.mapped('value')))
                current_kit_total_cost = product.standard_price * line.quantity
                current_kit_total_cost_comp_curr = line.currency_id._convert(
                    current_kit_total_cost, company_currency, line.company_id, line.adjustment_id.date_adjustment)

                comparison = float_compare(current_kit_total_cost_comp_curr, actual_component_valuation, precision_rounding=company_currency.rounding)

                # Crear SVLs para componentes SOLO si la valoración original difiere del costo actual
                if comparison != 0:
                    _logger.info(f"[Ajuste {self.name}] Kit {product.name}: Valoración original componentes ({actual_component_valuation}) difiere del costo actual kit ({current_kit_total_cost_comp_curr}). Creando SVLs de ajuste.")
                    component_svl_vals = line._prepare_kit_component_svl_vals(adjustment_move, component_moves, adjustment_amount_comp_curr)
                    svl_vals_list.extend(component_svl_vals)
                else:
                     _logger.info(f"[Ajuste {self.name}] Kit {product.name}: Valoración original componentes ({actual_component_valuation}) coincide con costo actual kit ({current_kit_total_cost_comp_curr}). No se crearán SVLs de ajuste.")
            else:
                # --- Lógica para Productos Estándar (Almacenables, no Kit) ---
                # Solo si es tipo 'product' (Almacenable Correcto Estándar)
                if product.product_type == 'product':
                    standard_svl_vals = line._prepare_standard_product_svl_vals(adjustment_move, adjustment_amount_comp_curr)
                    if standard_svl_vals:
                        svl_vals_list.append(standard_svl_vals)
                    else:
                        _logger.warning(f"[Ajuste {self.name}] No se pudo preparar SVL estándar para la línea {line.id}")
                # Si es 'consu' pero 'real_time' y no 'is_storable', es "Mal Configurado", no crea SVL aquí.
                elif product.product_type == 'consu' and not product.is_storable:
                     _logger.info(f"[Ajuste {self.name}] Producto {product.name} es 'Mal Configurado'. Omitiendo SVL.")
                else:
                     _logger.warning(f"[Ajuste {self.name}] Producto {product.name} (tipo {product.product_type}, val {product.product_valuation}) no es Kit ni tipo 'product' estándar. No se crea SVL.")

        if svl_vals_list:
            svl_obj.create(svl_vals_list)
        return True


# ==============================================================================
# Modelo de Línea de Ajuste de Costo
# ==============================================================================
class CostAdjustmentLine(models.Model):
    _name = 'cost.adjustment.line'
    _description = 'Línea de Ajuste de Costo de Venta'

    # --- Campos ---
    adjustment_id = fields.Many2one('cost.adjustment', string='Ajuste de Costo', required=True, ondelete='cascade')
    original_invoice_line_id = fields.Many2one('account.move.line', string='Línea de Factura Original', required=True, help="Línea específica de la factura original cuyo costo se ajustará.")
    product_id = fields.Many2one('product.product', string='Producto', related='original_invoice_line_id.product_id', store=True, readonly=True)
    is_kit = fields.Boolean(related='product_id.is_kit', string="Es Kit", store=True, readonly=True)
    is_storable_product = fields.Boolean(string="Es Almacenable (Tipo)", compute='_compute_is_storable_product', store=True, readonly=True)
    product_type = fields.Selection(related='product_id.type', store=True, readonly=True)
    product_valuation = fields.Selection(related='product_id.valuation', store=True, readonly=True)
    product_is_storable = fields.Boolean(related='product_id.is_storable', string="Es Almacenable (Campo)", store=True, readonly=True) # Campo related añadido

    quantity = fields.Float(string='Cantidad Facturada', related='original_invoice_line_id.quantity', store=True, readonly=True)
    original_cost_total = fields.Monetary(string='Costo Original Registrado (Total)', compute='_compute_costs_and_adjustment', store=True, readonly=True, currency_field='currency_id', help="Costo total registrado originalmente en el asiento de COGS de la factura.")
    current_average_cost = fields.Monetary(string='Costo Actual (Unitario/Kit)', compute='_compute_costs_and_adjustment', store=True, readonly=True, currency_field='currency_id', help="Costo estándar/promedio actual del producto o costo unitario actual del kit.")
    adjustment_amount = fields.Monetary(string='Importe del Ajuste', compute='_compute_costs_and_adjustment', store=True, readonly=True, currency_field='currency_id', help="Diferencia calculada: (Costo Actual Total) - Costo Original Registrado.")
    analytic_distribution = fields.Json(string='Distribución Analítica', readonly=True, copy=False, help="Distribución analítica heredada de la línea de factura original (si existe).")
    company_id = fields.Many2one('res.company', related='adjustment_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', related='adjustment_id.currency_id', store=True, readonly=True)
    computed_account_cogs_id = fields.Many2one('account.account', string='Cuenta COGS/Gasto (Calculada)', compute='_compute_accounts', store=False, readonly=True)
    computed_account_contra_id = fields.Many2one('account.account', string='Cuenta Contrapartida (Calculada)', compute='_compute_accounts', store=False, readonly=True)

    @api.depends('product_id.type')
    def _compute_is_storable_product(self):
        """ Campo helper para saber si el producto es de tipo 'product' """
        for line in self:
            line.is_storable_product = line.product_id.type == 'product'

    # --- Onchange ---
    @api.onchange('original_invoice_line_id')
    def _onchange_original_invoice_line_id(self):
        # (Sin cambios)
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
            self.computed_account_contra_id = False

    # --- Compute Principal (Refinado para buscar COGS línea por línea) ---
    @api.depends('original_invoice_line_id', 'product_id', 'quantity', 'adjustment_id.date_adjustment', 'currency_id')
    def _compute_costs_and_adjustment(self):
        """
        Calcula costos y ajuste.
        - Costo Original: Busca la línea de COGS específica en la factura original.
        - Costo Actual: Desde standard_price del producto.
        """
        # Cache para cuentas COGS por categoría/compañía
        cogs_accounts_cache = {}

        for line in self:
            # Inicializar valores
            original_cost = 0.0
            current_cost_total = 0.0
            current_cost_unit = 0.0
            adjustment = 0.0
            product = line.product_id
            invoice_line = line.original_invoice_line_id
            company = line.company_id
            line_currency = line.currency_id or company.currency_id # Moneda del ajuste

            if invoice_line and product and line_currency:
                # --- Calcular Costo Actual ---
                current_cost_unit = product.standard_price
                current_cost_total = current_cost_unit * line.quantity

                # --- Calcular Costo Original (Buscando línea COGS específica) ---
                # Obtener cuenta COGS para este producto/compañía (cacheado)
                cache_key = (product.categ_id.id, company.id)
                cogs_account_id = cogs_accounts_cache.get(cache_key)
                if cogs_account_id is None: # None indica que no se ha buscado aún
                    accounts = product.with_company(company)._get_product_accounts()
                    cogs_account = accounts.get('expense') or product.categ_id.property_account_expense_categ_id
                    cogs_account_id = cogs_account.id if cogs_account else False # False si no se encuentra
                    cogs_accounts_cache[cache_key] = cogs_account_id

                if cogs_account_id:
                    # Buscar la línea de COGS específica para esta línea de factura y producto
                    # Asumimos que la línea de COGS tiene el mismo producto y está en el mismo asiento
                    cogs_move_line = self.env['account.move.line'].search([
                        ('move_id', '=', invoice_line.move_id.id),
                        ('product_id', '=', product.id),
                        ('account_id', '=', cogs_account_id),
                        ('parent_state', '=', 'posted'),
                        # Excluir la propia línea de factura por si acaso usa la misma cuenta
                        ('id', '!=', invoice_line.id),
                    ], limit=1) # Asumir que solo hay una línea COGS por producto en el asiento

                    if cogs_move_line:
                        original_cost = cogs_move_line.debit # El costo es el débito
                        _logger.debug(f"Ajuste Línea {line.id}, Factura Línea {invoice_line.id}, Producto {product.name}: Encontrada línea COGS {cogs_move_line.id} con débito {original_cost}")
                    else:
                         _logger.debug(f"Ajuste Línea {line.id}, Factura Línea {invoice_line.id}, Producto {product.name}: No se encontró línea COGS.")
                else:
                    _logger.warning(f"Ajuste Línea {line.id}: No se pudo determinar la cuenta COGS para el producto {product.name}.")


                # Convertir costo original (que está en moneda compañía) a moneda de la línea/ajuste
                company_currency = company.currency_id
                if company_currency != line_currency and not company_currency.is_zero(original_cost):
                     original_cost = company_currency._convert(original_cost, line_currency, company, line.adjustment_id.date_adjustment)

                # --- Calcular Ajuste ---
                adjustment = current_cost_total - original_cost
                # _logger.debug(f"Line {line.id}: Current Total={current_cost_total}, Original Conv={original_cost}, Adjustment={adjustment} (Currency: {line_currency.name})")

            # --- Asignar Valores ---
            line.original_cost_total = line_currency.round(original_cost) if line_currency else 0.0
            line.current_average_cost = line_currency.round(current_cost_unit) if line_currency else 0.0
            line.adjustment_amount = line_currency.round(adjustment) if line_currency else 0.0


    # --- Compute Cuentas (Modificado para lógica final) ---
    @api.depends('product_id', 'company_id', 'product_type', 'product_valuation', 'product_is_storable')
    def _compute_accounts(self):
        """ Calcula y muestra las cuentas que se usarán en el asiento. """
        for line in self:
            # Llamar al método helper que contiene la lógica
            acc_cogs, acc_contra = line._get_adjustment_accounts()
            line.computed_account_cogs_id = acc_cogs
            line.computed_account_contra_id = acc_contra


    # --- Métodos de Ayuda ---
    def _find_original_stock_move(self):
        # Solo busca para productos con valoración real_time y no kits
        # (Sin cambios)
        self.ensure_one()
        if not self.original_invoice_line_id or not self.product_id or self.product_id.product_valuation != 'real_time' or self.product_id.is_kit:
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
             _logger.warning(f"No se encontró stock.move para la línea de factura {aml.id} (Producto: {self.product_id.name}, Valoración: {self.product_id.product_valuation})")
        return stock_moves

    def _find_kit_component_moves(self):
        # Solo busca si es un kit con valoración real_time
        # (Sin cambios)
        self.ensure_one()
        if not self.original_invoice_line_id or not self.product_id or not self.product_id.is_kit or self.product_id.product_valuation != 'real_time':
            return self.env['stock.move']
        aml = self.original_invoice_line_id
        if not aml.sale_line_ids:
            _logger.warning(f"Línea de factura {aml.id} (Kit: {self.product_id.name}) no tiene líneas de venta asociadas.")
            return self.env['stock.move']
        bom = self.env['mrp.bom']._bom_find(products=self.product_id, bom_type='phantom', company_id=self.company_id.id).get(self.product_id)
        if not bom:
             _logger.warning(f"No se encontró LdM tipo Phantom para el Kit {self.product_id.name}.")
             return self.env['stock.move']
        components, dummy = bom.explode(self.product_id, self.quantity)
        component_ids = [c[0].id for c in components if c[0].type != 'phantom']
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

    # Modificado para implementar la lógica final y precisa
    def _get_adjustment_accounts(self):
        """
        Obtiene las cuentas COGS y la contrapartida correcta según el tipo/configuración del producto.
        - Almacenable Correcto (Std/Kit, val=real_time): COGS vs Salida Stock
        - Almacenable Mal Configurado (type=consu, val=real_time, storable=False): COGS vs Valoración Inventario
        """
        self.ensure_one()
        if not self.product_id:
            return self.env['account.account'], self.env['account.account']

        product = self.product_id.with_company(self.company_id)
        accounts = product._get_product_accounts()
        acc_cogs = accounts.get('expense')
        acc_output = accounts.get('stock_output')
        acc_valuation = accounts.get('stock_valuation')
        acc_contra = False # Cuenta contrapartida a determinar

        prod_type = product.product_type
        prod_valuation = product.product_valuation
        prod_is_storable = product.is_storable # Campo related

        _logger.debug(f"Get Accounts - Prod: {product.name}, Type: {prod_type}, Valuation: {prod_valuation}, IsStorable: {prod_is_storable}")

        # Lógica final basada en definiciones del usuario:
        # 1. Almacenable Mal Configurado: type='consu', valuation='real_time', is_storable=False
        if prod_type == 'consu' and prod_valuation == 'real_time' and not prod_is_storable:
            acc_contra = acc_valuation
            _logger.debug(f"  -> Caso: Mal Configurado -> Contrapartida = Valoración ({acc_contra.code if acc_contra else 'N/A'})")
        # 2. Almacenable Correcto: valuation='real_time' (y no es el caso anterior)
        elif prod_valuation == 'real_time':
            acc_contra = acc_output
            _logger.debug(f"  -> Caso: Almacenable Correcto -> Contrapartida = Salida ({acc_contra.code if acc_contra else 'N/A'})")
        # 3. Consumible Correcto: type='consu', valuation='manual'
        #    Estos no deberían ser seleccionables por el domain de la vista.
        #    Si por alguna razón se selecciona, definimos un comportamiento (ej. error o usar valoración)
        elif prod_type == 'consu' and prod_valuation == 'manual':
             _logger.error(f"  -> Caso: Consumible Correcto (valoración manual) seleccionado para ajuste. Esto no debería ocurrir.")
             # Lanzar error o asignar una cuenta por defecto? Lanzar error es más seguro.
             raise UserError(_("Los productos consumibles con valoración manual no deben ser ajustados mediante esta herramienta."))
        else:
             # Otros casos (ej. servicio)
             _logger.error(f"  -> Combinación de Tipo/Valoración no esperada para ajuste: {prod_type}/{prod_valuation}")
             raise UserError(_("El tipo de producto seleccionado no es válido para el ajuste de costo."))


        # Fallback a la categoría si falta alguna cuenta (solo si la lógica principal no la encontró)
        categ = product.categ_id
        if not acc_cogs:
            acc_cogs = categ.property_account_expense_categ_id
            _logger.debug(f"  -> Usando COGS de Categoría: {acc_cogs.code if acc_cogs else 'N/A'}")
        if not acc_contra:
            _logger.debug(f"  -> Buscando contrapartida fallback en categoría...")
            if prod_type == 'consu' and prod_valuation == 'real_time' and not prod_is_storable:
                acc_contra = categ.property_stock_valuation_account_id
            elif prod_valuation == 'real_time':
                acc_contra = categ.property_stock_account_output_categ_id
            elif prod_type == 'consu' and prod_valuation == 'manual':
                 # Si llegamos aquí para un consumible, usamos valoración como fallback antes del error
                 acc_contra = categ.property_stock_valuation_account_id
            _logger.debug(f"  -> Contrapartida Fallback: {acc_contra.code if acc_contra else 'N/A'}")

        # Validación final
        if not acc_cogs or not acc_contra:
             error_msg = _("No se pudieron determinar las cuentas requeridas para el ajuste del producto '{}' (Categoría: {}). ".format(product.display_name, categ.display_name))
             if not acc_cogs: error_msg += _("Falta cuenta de Gasto/COGS. ")
             if not acc_contra: error_msg += _("Falta cuenta de Contrapartida (Salida/Valoración). ")
             error_msg += _("Verifique la configuración contable del producto/categoría.")
             _logger.error(f"Error Cuentas Ajuste: {error_msg}")
             raise UserError(error_msg)

        _logger.debug(f"  -> Cuentas Finales: COGS={acc_cogs.code}, Contrapartida={acc_contra.code}")
        return acc_cogs, acc_contra

    # Usa _get_adjustment_accounts que ahora devuelve la cuenta correcta
    def _prepare_adjustment_move_lines_vals(self, move_currency):
        """ Prepara las DOS líneas del asiento contable. """
        # (Sin cambios)
        self.ensure_one()
        vals_list = []
        if float_is_zero(self.adjustment_amount, precision_rounding=move_currency.rounding):
             return []
        amount = self.currency_id._convert(self.adjustment_amount, move_currency, self.company_id, self.adjustment_id.date_adjustment)
        acc_cogs, acc_contrapartida = self._get_adjustment_accounts()
        partner_id = self.adjustment_id.original_invoice_id.partner_id.id
        name = _("Ajuste Costo: {}").format(self.product_id.display_name)
        debit_cogs, credit_cogs, debit_contra, credit_contra = 0.0, 0.0, 0.0, 0.0
        if float_compare(amount, 0.0, precision_rounding=move_currency.rounding) > 0:
            debit_cogs = amount
            credit_contra = amount
        else:
            credit_cogs = abs(amount)
            debit_contra = abs(amount)
        vals_cogs = {
            'name': name, 'account_id': acc_cogs.id, 'debit': debit_cogs, 'credit': credit_cogs,
            'analytic_distribution': self.analytic_distribution or False, 'partner_id': partner_id,
            'product_id': self.product_id.id, 'quantity': self.quantity, 'currency_id': move_currency.id,
        }
        vals_list.append(vals_cogs)
        vals_contrapartida = {
            'name': name, 'account_id': acc_contrapartida.id, 'debit': debit_contra, 'credit': credit_contra,
            'analytic_distribution': False, 'partner_id': partner_id,
            'product_id': self.product_id.id, 'quantity': self.quantity, 'currency_id': move_currency.id,
        }
        vals_list.append(vals_contrapartida)
        return vals_list

    def _prepare_standard_product_svl_vals(self, adjustment_move, adjustment_amount_comp_curr):
         # Solo aplica a productos con valoración real_time y no kits
         # (Sin cambios)
         self.ensure_one()
         if self.product_id.product_valuation != 'real_time' or self.product_id.is_kit: return {}
         stock_move = self._find_original_stock_move()
         if not stock_move:
             _logger.warning(f"No se creará SVL estándar para la línea {self.id} (Producto: {self.product_id.name}) porque no se encontró el stock.move original.")
             return {}
         description = _("Ajuste Costo - Fact: {} - Ajuste: {}").format(
             self.adjustment_id.original_invoice_id.name,
             self.adjustment_id.name
         )
         value_in_company_currency = adjustment_amount_comp_curr
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

    def _prepare_kit_component_svl_vals(self, adjustment_move, component_moves, kit_adjustment_total_comp_curr):
        # Solo aplica a kits con valoración real_time
        # (Sin cambios)
        self.ensure_one()
        if not self.product_id.is_kit or self.product_id.product_valuation != 'real_time': return []

        company_currency = self.company_id.currency_id
        if float_is_zero(kit_adjustment_total_comp_curr, precision_rounding=company_currency.rounding):
            return []
        if not component_moves:
            return []

        total_current_component_cost_comp_curr = 0
        component_data = []
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for move in component_moves:
            quantity_moved = move.quantity # Usando move.quantity
            if float_is_zero(quantity_moved, precision_digits=precision):
                 continue

            comp_cost = move.product_id.with_company(self.company_id).standard_price * quantity_moved
            total_current_component_cost_comp_curr += comp_cost
            component_data.append({'move': move, 'current_cost_comp_curr': comp_cost})

        if float_is_zero(total_current_component_cost_comp_curr, precision_rounding=company_currency.rounding):
            _logger.warning(f"El costo total actual (moneda compañía) de los componentes para el Kit {self.product_id.name} (Ajuste: {self.adjustment_id.name}) es cero. No se puede distribuir el ajuste.")
            return []

        svl_vals_list = []
        accumulated_adjustment = 0.0

        for i, data in enumerate(component_data):
            move = data['move']
            comp_cost_comp_curr = data['current_cost_comp_curr']
            ratio = comp_cost_comp_curr / total_current_component_cost_comp_curr if total_current_component_cost_comp_curr else 0
            comp_adjustment_value = company_currency.round(kit_adjustment_total_comp_curr * ratio)

            if len(component_data) > 1 and i == len(component_data) - 1:
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
            if svl_vals_list and abs(kit_adjustment_total_comp_curr - final_sum) < company_currency.rounding * 2:
                 diff = kit_adjustment_total_comp_curr - final_sum
                 svl_vals_list[-1]['value'] += diff
                 svl_vals_list[-1]['remaining_value'] += diff
                 _logger.warning(f"Ajuste de redondeo aplicado a la última línea SVL: {diff}")

        return svl_vals_list


# ==============================================================================
# Herencia de Account Move
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
        # (Sin cambios)
        default_values_list = default_values_list or [{} for _ in self]
        reversed_moves = super(AccountMove, self)._reverse_moves(default_values_list=default_values_list, cancel=cancel)

        svl_obj = self.env['stock.valuation.layer']
        adjustment_obj = self.env['cost.adjustment']
        svl_to_create = []
        adjustments_to_cancel = adjustment_obj.browse()

        map_original_to_reversed = {rev.reversed_entry_id.id: rev for rev in reversed_moves if rev.reversed_entry_id}

        for move in self.filtered(lambda m: m.cost_adjustment_origin_id):
            adjustment = move.cost_adjustment_origin_id
            if adjustment.state == 'posted':
                adjustments_to_cancel |= adjustment

            reversed_move = map_original_to_reversed.get(move.id)
            if not reversed_move:
                _logger.error(f"No se encontró el asiento reverso para el ajuste {move.name} durante la reversión del SVL.")
                continue

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

        if adjustments_to_cancel:
            adjustments_to_cancel.write({'state': 'cancel'})

        return reversed_moves
