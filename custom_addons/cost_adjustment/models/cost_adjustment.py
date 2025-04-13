# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

import logging # Opcional: para logging si es necesario
_logger = logging.getLogger(__name__) # Opcional: para logging

class CostAdjustment(models.Model):
    """
    Modelo principal para gestionar los ajustes de costo de venta post-facturación.
    Permite seleccionar una factura de cliente timbrada y ajustar el costo
    de una o más de sus líneas.
    Ref: RF01
    """
    _name = 'cost.adjustment'
    _description = 'Ajuste de Costo de Venta'
    _inherit = ['mail.thread', 'mail.activity.mixin'] # Para chatter y actividades
    _order = 'name desc'

    # --- Campos Principales ---
    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('Nuevo')
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('posted', 'Publicado'),
        ('cancel', 'Cancelado')],
        string='Estado',
        required=True,
        default='draft',
        copy=False,
        tracking=True,
    )
    date_adjustment = fields.Date(
        string='Fecha de Ajuste',
        required=True,
        default=fields.Date.context_today,
        copy=False,
        states={'posted': [('readonly', True)], 'cancel': [('readonly', True)]},
        help="Fecha en la que se aplicará contablemente el asiento de ajuste."
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario Contable',
        required=True,
        domain="[('type', '=', 'general')]",
        states={'posted': [('readonly', True)], 'cancel': [('readonly', True)]},
        help="Diario donde se registrará el asiento contable del ajuste."
    )
    reason = fields.Text(
        string='Motivo del Ajuste',
        required=True,
        states={'posted': [('readonly', True)], 'cancel': [('readonly', True)]},
        help="Explicación detallada de por qué se realiza este ajuste de costo."
    )
    original_invoice_id = fields.Many2one(
        'account.move',
        string='Factura Original',
        required=True,
        domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('l10n_mx_edi_cfdi_uuid', '!=', False), ('edi_state', '=', 'sent')]",
        states={'posted': [('readonly', True)], 'cancel': [('readonly', True)]},
        copy=False,
        tracking=True,
        help="Factura de cliente publicada y timbrada cuyas líneas se ajustarán."
    )
    adjustment_move_id = fields.Many2one(
        'account.move',
        string='Asiento de Ajuste',
        readonly=True,
        copy=False,
        help="Asiento contable generado por este ajuste."
    )
    line_ids = fields.One2many(
        'cost.adjustment.line',
        'adjustment_id',
        string='Líneas de Ajuste',
        states={'posted': [('readonly', True)], 'cancel': [('readonly', True)]},
        copy=True, # Permitir copiar líneas al duplicar ajuste? Podría ser útil
    )
    auto_post_entry = fields.Boolean(
        string='¿Publicar Asiento Automáticamente?',
        default=False, # Por defecto, dejar en borrador para revisión
        states={'posted': [('readonly', True)], 'cancel': [('readonly', True)]},
        help="Si se marca, el asiento de ajuste se publicará automáticamente al confirmar. "
             "Si no, quedará en estado borrador."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='journal_id.company_id', # O tomarlo del usuario
        store=True,
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='journal_id.currency_id', # O de la factura original
        store=True,
        readonly=True
    )

    # --- Secuencia para 'name' ---
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                # Idealmente, obtener secuencia por compañía/diario si es necesario
                vals['name'] = self.env['ir.sequence'].next_by_code('cost.adjustment') or _('Nuevo')
        return super(CostAdjustment, self).create(vals_list)

    # --- Acciones de Botones ---
    def action_post(self):
        """
        Valida, crea el asiento contable de ajuste, crea las capas de valoración (SVL)
        y opcionalmente publica el asiento. Cambia el estado del ajuste a 'Publicado'.
        Ref: RF04, RF05, RF08
        """
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("No se puede publicar un ajuste sin líneas."))

        # 1. Validar Periodo Contable (RF08)
        self._check_period_lock_date()

        # 2. Crear Asiento Contable (RF04)
        move = self._create_adjustment_move()
        self.adjustment_move_id = move.id

        # 3. Crear Capas de Valoración (SVL) (RF05)
        self._create_stock_valuation_layers(move)

        # 4. Publicar Asiento (Opcional)
        if self.auto_post_entry:
            move.action_post()

        # 5. Cambiar Estado del Ajuste
        self.write({'state': 'posted'})
        return True

    def action_cancel(self):
        """
        Cancela el ajuste. Si el asiento de ajuste fue creado, intenta reversarlo.
        """
        moves_to_reverse = self.mapped('adjustment_move_id').filtered(lambda m: m.state == 'posted')
        if moves_to_reverse:
            # La lógica de reversión del SVL está en el override de _reverse_moves
            moves_to_reverse._reverse_moves(cancel=True) # Cancel=True para cambiar estado asiento original

        # Cancelar asientos en borrador si existen
        draft_moves = self.mapped('adjustment_move_id').filtered(lambda m: m.state == 'draft')
        if draft_moves:
            draft_moves.button_cancel() # O button_draft -> button_cancel si es necesario

        self.write({'state': 'cancel'})
        return True

    def action_draft(self):
        """ Pasa el ajuste de nuevo a borrador (si está cancelado) """
        self.ensure_one()
        if self.adjustment_move_id:
             raise UserError(_("No puede pasar a borrador un ajuste que ya generó un asiento contable. Cancele el asiento primero si es necesario."))
        self.write({'state': 'draft'})
        return True

    # --- Métodos de Ayuda ---
    def _check_period_lock_date(self):
        """ Valida si la fecha del ajuste cae en un periodo bloqueado. Ref: RF08 """
        self.ensure_one()
        # Simular valores para usar la validación estándar de account.move
        move_vals = {
            'journal_id': self.journal_id.id,
            'date': self.date_adjustment,
            'company_id': self.company_id.id,
        }
        try:
            # Usar el método de validación de account.move
            # Necesitamos instanciar temporalmente o llamar a un helper si es un @api.model
            # Aquí asumimos que podemos llamarlo así (puede requerir ajustes)
            self.env['account.move']._check_fiscalyear_lock_date(move_vals)
        except UserError as e:
            # Si lanza UserError por fecha bloqueada, relanzarla
            raise UserError(_("Error en el ajuste {}: {}").format(self.name, e.args[0]))
        return True

    def _prepare_adjustment_move_vals(self):
        """ Prepara los valores para crear el asiento contable de ajuste. Ref: RF04 """
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
            'move_type': 'entry', # Es un asiento genérico
            'cost_adjustment_origin_id': self.id, # Trazabilidad (RF07)
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'line_ids': [], # Se añadirán después
        }

    def _create_adjustment_move(self):
        """ Crea el asiento contable (account.move) y sus líneas. Ref: RF04 """
        self.ensure_one()
        move_vals = self._prepare_adjustment_move_vals()
        move_lines_vals = []

        for line in self.line_ids:
            if abs(line.adjustment_amount) < 1e-6 : # O usar company_currency.is_zero
                continue # No crear apuntes si el ajuste es cero

            line_vals = line._prepare_adjustment_move_lines_vals()
            move_lines_vals.extend(line_vals)

        if not move_lines_vals:
             raise UserError(_("No se generaron líneas de asiento para el ajuste {}.").format(self.name))

        move_vals['line_ids'] = [(0, 0, vals) for vals in move_lines_vals]
        move = self.env['account.move'].create(move_vals)
        return move

    def _create_stock_valuation_layers(self, adjustment_move):
        """ Crea las capas de valoración (SVL) para cada línea de ajuste. Ref: RF05 """
        self.ensure_one()
        svl_obj = self.env['stock.valuation.layer']
        svl_vals_list = []

        for line in self.line_ids:
             if abs(line.adjustment_amount) < 1e-6:
                 continue
             svl_vals = line._prepare_stock_valuation_layer_vals(adjustment_move)
             if svl_vals: # Solo si se pudo preparar (ej. se encontró stock.move)
                 svl_vals_list.append(svl_vals)
             else:
                 # Opcional: Log o advertencia si no se pudo crear SVL para una línea
                 _logger.warning(f"No se pudo preparar SVL para la línea de ajuste {line.id} (Ajuste: {self.name})")


        if svl_vals_list:
            svl_obj.create(svl_vals_list)

        return True


class CostAdjustmentLine(models.Model):
    """ Líneas del ajuste de costo, cada una corresponde a una línea de factura original. """
    _name = 'cost.adjustment.line'
    _description = 'Línea de Ajuste de Costo de Venta'

    adjustment_id = fields.Many2one(
        'cost.adjustment',
        string='Ajuste de Costo',
        required=True,
        ondelete='cascade'
    )
    original_invoice_line_id = fields.Many2one(
        'account.move.line',
        string='Línea de Factura Original',
        required=True,
        # El dominio se aplica mejor en la vista XML usando context/parent
        # domain="[('move_id', '=', parent.original_invoice_id), ('display_type', '=', False), ('product_id', '!=', False), ('product_id.valuation', '=', 'real_time')]",
        help="Línea específica de la factura original cuyo costo se ajustará."
    )
    # Campos relacionados/calculados (se calculan al seleccionar original_invoice_line_id)
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        related='original_invoice_line_id.product_id',
        store=True,
        readonly=True
    )
    quantity = fields.Float(
        string='Cantidad Facturada',
        related='original_invoice_line_id.quantity',
        store=True, # Guardar para cálculos
        readonly=True
    )
    # Campos de Costo y Ajuste (calculados)
    original_cost_total = fields.Monetary(
        string='Costo Original Registrado (Total)',
        compute='_compute_costs_and_adjustment',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help="Costo total que se registró en valoración para esta línea al momento de la factura original (basado en SVL)."
    )
    current_average_cost = fields.Monetary(
        string='Costo Promedio Actual (Unitario)',
        compute='_compute_costs_and_adjustment',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help="Costo estándar/promedio del producto al momento de crear/calcular el ajuste."
    )
    adjustment_amount = fields.Monetary(
        string='Importe del Ajuste',
        compute='_compute_costs_and_adjustment',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help="Diferencia calculada: (Costo Promedio Actual * Cantidad) - Costo Original Registrado."
    )
    # Campos para Asiento Contable
    analytic_distribution = fields.Json(
        string='Distribución Analítica',
        compute='_compute_analytic_distribution',
        store=True,
        readonly=True,
        help="Distribución analítica heredada de la línea de factura original (si existe)."
    )
    # Campos Técnicos / Relacionados
    company_id = fields.Many2one(
        'res.company',
        related='adjustment_id.company_id',
        store=True,
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='adjustment_id.currency_id',
        store=True,
        readonly=True
    )
    # Campos para mostrar cuentas (opcional, mejora UI)
    computed_account_cogs_id = fields.Many2one(
        'account.account',
        string='Cuenta COGS/Gasto (Calculada)',
        compute='_compute_accounts',
        store=False, # No necesario almacenar, solo para UI
        readonly=True
    )
    computed_account_valuation_id = fields.Many2one(
        'account.account',
        string='Cuenta Valoración/Salida (Calculada)',
        compute='_compute_accounts',
        store=False, # No necesario almacenar, solo para UI
        readonly=True
    )

    # --- Métodos Compute ---
    @api.depends('original_invoice_line_id', 'adjustment_id.date_adjustment')
    def _compute_costs_and_adjustment(self):
        """
        Calcula el costo original (buscando SVL), el costo actual (standard_price)
        y el importe del ajuste.
        Ref: RF01 (Campos), RF03 (Cálculo)
        """
        svl_obj = self.env['stock.valuation.layer']
        for line in self:
            original_cost = 0.0
            current_cost = 0.0
            adjustment = 0.0

            if line.original_invoice_line_id and line.product_id:
                # 1. Obtener Costo Original (desde SVL asociado al stock.move)
                stock_move = line._find_original_stock_move()
                if stock_move:
                    # Buscar el SVL creado por ese stock_move
                    # Considerar la compañía y el producto
                    domain = [
                        ('stock_move_id', '=', stock_move.id),
                        ('product_id', '=', line.product_id.id),
                        ('company_id', '=', line.company_id.id),
                        ('account_move_id', '=', line.original_invoice_line_id.move_id.id) # Filtro adicional por asiento original?
                    ]
                    # Podría haber más de uno si hay correcciones previas? Tomar el más relevante.
                    # Sumar 'value' podría ser lo correcto si hay varios SVL para el mismo move? Revisar lógica AVCO.
                    # Por simplicidad inicial, buscamos uno y tomamos su valor.
                    svl = svl_obj.search(domain, limit=1)
                    if svl:
                        # El valor en SVL para salidas suele ser negativo
                        original_cost = abs(svl.value)

                # 2. Obtener Costo Promedio Actual (standard_price)
                # Considerar la fecha del ajuste para obtener el costo histórico si es necesario?
                # Por simplicidad y según requerimiento, usamos el costo actual.
                current_cost = line.product_id.standard_price # Costo unitario

                # 3. Calcular Ajuste
                # adjustment = (current_cost * line.quantity) - original_cost
                # Corrección: current_cost es unitario, original_cost es total
                cost_total_actual = current_cost * line.quantity
                adjustment = cost_total_actual - original_cost

            line.original_cost_total = original_cost
            line.current_average_cost = current_cost
            line.adjustment_amount = adjustment

    @api.depends('original_invoice_line_id')
    def _compute_analytic_distribution(self):
        """ Copia la distribución analítica de la línea de factura original. Ref: RF06 """
        for line in self:
            line.analytic_distribution = line.original_invoice_line_id.analytic_distribution or False

    @api.depends('product_id', 'company_id')
    def _compute_accounts(self):
        """ Calcula y muestra las cuentas que se usarán en el asiento. Ref: RF03 """
        for line in self:
            accounts = {'expense': False, 'stock_output': False}
            if line.product_id and line.company_id:
                 # Usar método estándar para obtener cuentas
                 accounts_dict = line.product_id._get_product_accounts()
                 line.computed_account_cogs_id = accounts_dict.get('expense')
                 line.computed_account_valuation_id = accounts_dict.get('stock_output')
            else:
                 line.computed_account_cogs_id = False
                 line.computed_account_valuation_id = False


    # --- Métodos de Ayuda ---
    def _find_original_stock_move(self):
        """
        Encuentra el stock.move original asociado a la línea de factura.
        Depende de la trazabilidad SO -> Factura -> Stock Move.
        Ref: RF05 (Paso 1)
        """
        self.ensure_one()
        if not self.original_invoice_line_id or not self.product_id:
            return False

        # Intentar vía sale_line_ids (método más común)
        # Nota: sale_line_ids es M2M, puede haber varias si se agrupan facturas, etc.
        # Necesitamos filtrar por producto y posiblemente cantidad para ser más precisos.
        sale_lines = self.original_invoice_line_id.sale_line_ids
        if not sale_lines:
            _logger.info(f"Línea de factura {self.original_invoice_line_id.id} no tiene líneas de venta asociadas.")
            return False # No se puede trazar sin SO

        # Buscar movimientos de stock asociados a CUALQUIERA de esas líneas de venta
        # que sean del mismo producto y compañía.
        # Filtrar por movimientos de salida (picking_code == 'OUT' o location_dest_usage == 'customer')
        domain = [
            ('sale_line_id', 'in', sale_lines.ids),
            ('product_id', '=', self.product_id.id),
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'done'), # Solo movimientos hechos
            # ('picking_code', '=', 'OUT') # Si aplica
        ]
        # Podrían salir varios si la SO tuvo varios pickings.
        # ¿Cómo identificar el correcto? Quizás por cantidad o fecha?
        # Por ahora, tomamos el primero que coincida (puede requerir ajuste)
        stock_move = self.env['stock.move'].search(domain, limit=1, order='date desc')

        if not stock_move:
             _logger.warning(f"No se encontró stock.move para la línea de factura {self.original_invoice_line_id.id} (Producto: {self.product_id.name})")
             # Aquí se podría intentar otra lógica de búsqueda si es necesario
             return False

        return stock_move

    def _get_adjustment_accounts(self):
        """ Obtiene las cuentas COGS y Valoración para el asiento. Ref: RF03 """
        self.ensure_one()
        if not self.product_id:
            raise UserError(_("No se puede determinar cuentas sin un producto en la línea {}.").format(self.id))

        accounts = self.product_id._get_product_accounts()
        acc_cogs = accounts.get('expense')
        acc_valuation = accounts.get('stock_output')

        if not acc_cogs or not acc_valuation:
            # Intentar obtener de la categoría si falta alguno (fallback, aunque _get_product_accounts debería hacerlo)
            categ = self.product_id.categ_id
            if not acc_cogs:
                acc_cogs = categ.property_account_expense_categ_id
            if not acc_valuation:
                acc_valuation = categ.property_stock_account_output_categ_id

            # Validar si se encontraron ambas cuentas
            if not acc_cogs or not acc_valuation:
                 raise UserError(_("No se pudieron determinar las cuentas de Costo de Venta y/o Salida de Stock para el producto '{}' (Categoría: {}). Verifique la configuración contable.").format(self.product_id.display_name, categ.display_name))

        return acc_cogs, acc_valuation


    def _prepare_adjustment_move_lines_vals(self):
        """ Prepara los valores para las DOS líneas del asiento contable. Ref: RF04 """
        self.ensure_one()
        vals_list = []
        amount = self.adjustment_amount
        acc_cogs, acc_valuation = self._get_adjustment_accounts()
        partner_id = self.adjustment_id.original_invoice_id.partner_id.id

        # Determinar débito/crédito
        debit_cogs, credit_cogs, debit_val, credit_val = 0.0, 0.0, 0.0, 0.0
        if amount > 0: # Costo real > original -> Aumentar COGS (Débito), Crédito Valoración
            debit_cogs = amount
            credit_val = amount
        else: # Costo real < original -> Disminuir COGS (Crédito), Débito Valoración
            credit_cogs = abs(amount)
            debit_val = abs(amount)

        # Línea COGS
        vals_cogs = {
            'name': _("Ajuste Costo: {}").format(self.product_id.display_name),
            'account_id': acc_cogs.id,
            'debit': debit_cogs,
            'credit': credit_cogs,
            'analytic_distribution': self.analytic_distribution or False, # RF06
            'partner_id': partner_id,
            'product_id': self.product_id.id,
            'quantity': self.quantity, # Informativo
            'currency_id': self.currency_id.id,
        }
        vals_list.append(vals_cogs)

        # Línea Valoración
        vals_valuation = {
            'name': _("Ajuste Costo: {}").format(self.product_id.display_name),
            'account_id': acc_valuation.id,
            'debit': debit_val,
            'credit': credit_val,
            'analytic_distribution': False, # Analítica no aplica aquí (RF06)
            'partner_id': partner_id,
            'product_id': self.product_id.id,
            'quantity': self.quantity, # Informativo
            'currency_id': self.currency_id.id,
        }
        vals_list.append(vals_valuation)

        return vals_list

    def _prepare_stock_valuation_layer_vals(self, adjustment_move):
         """ Prepara los valores para crear el SVL de ajuste. Ref: RF05 """
         self.ensure_one()
         stock_move = self._find_original_stock_move()
         if not stock_move:
             # No se puede crear SVL sin el movimiento original
             return {}

         description = _("Ajuste Costo - Fact: {} - Ajuste: {}").format(
             self.adjustment_id.original_invoice_id.name,
             self.adjustment_id.name
         )

         return {
             'create_date': self.adjustment_id.date_adjustment, # Fecha del ajuste (RF05)
             'stock_move_id': stock_move.id,
             'product_id': self.product_id.id,
             'quantity': 0, # Ajuste solo de valor (RF05)
             'uom_id': self.product_id.uom_id.id,
             'unit_cost': 0, # El valor está en 'value'
             'value': self.adjustment_amount, # Valor del ajuste (RF05)
             'remaining_qty': 0,
             'remaining_value': self.adjustment_amount,
             'description': description,
             'account_move_id': adjustment_move.id, # Asiento que justifica este SVL (RF05)
             'company_id': self.company_id.id,
         }


# --- Herencia para añadir campos y lógica a modelos existentes ---

class AccountMove(models.Model):
    """ Herencia para añadir trazabilidad desde/hacia ajustes de costo. Ref: RF07 """
    _inherit = 'account.move'

    # Campo para ver ajustes desde la factura original
    cost_adjustment_ids = fields.One2many(
        'cost.adjustment',
        'original_invoice_id',
        string='Ajustes de Costo Relacionados',
        readonly=True,
        copy=False,
        help="Muestra los ajustes de costo que se han aplicado a esta factura."
    )
    # Campo para ver el origen desde el asiento de ajuste
    cost_adjustment_origin_id = fields.Many2one(
        'cost.adjustment',
        string='Origen Ajuste de Costo',
        readonly=True,
        index=True,
        copy=False,
        help="El registro de ajuste de costo que generó este asiento contable."
    )

    def _reverse_moves(self, default_values_list=None, cancel=False):
        """
        Hereda la función de reversión para añadir la creación del SVL inverso
        y cancelar el registro de ajuste original.
        Ref: RF09
        """
        # Ejecutar lógica estándar primero
        reversed_moves = super(AccountMove, self)._reverse_moves(default_values_list, cancel)

        svl_obj = self.env['stock.valuation.layer']
        adjustment_obj = self.env['cost.adjustment']
        svl_to_create = []
        adjustments_to_cancel = adjustment_obj # Vacío inicialmente

        for move in self.filtered(lambda m: m.cost_adjustment_origin_id):
            # Este 'move' es el asiento de ajuste ORIGINAL que se está reversando
            adjustment = move.cost_adjustment_origin_id
            adjustments_to_cancel |= adjustment # Acumular ajustes a cancelar

            # Buscar los SVL creados por este asiento de ajuste original
            original_svls = svl_obj.search([('account_move_id', '=', move.id)])

            # Encontrar el asiento reverso correspondiente a 'move'
            # reversed_moves es un recordset, buscar el que reversa a 'move'
            # La relación suele estar en reversed_moves.reversed_entry_id = move.id
            current_reversed_move = reversed_moves.filtered(lambda r: r.reversed_entry_id == move)
            if not current_reversed_move:
                 _logger.error(f"No se encontró el asiento reverso para el ajuste {move.name} durante la reversión del SVL.")
                 continue # Saltar al siguiente asiento original

            for svl in original_svls:
                # Preparar SVL inverso
                description = _("Reversión Ajuste Costo - Fact: {} - Ajuste: {} - Ref Rev: {}").format(
                    adjustment.original_invoice_id.name,
                    adjustment.name,
                    current_reversed_move.name
                )
                svl_vals = {
                     'create_date': current_reversed_move.date, # Fecha del asiento reverso
                     'stock_move_id': svl.stock_move_id.id, # Mismo stock_move original
                     'product_id': svl.product_id.id,
                     'quantity': 0,
                     'uom_id': svl.uom_id.id,
                     'unit_cost': 0,
                     'value': -svl.value, # Valor inverso
                     'remaining_qty': 0,
                     'remaining_value': -svl.value,
                     'description': description,
                     'account_move_id': current_reversed_move.id, # Asiento REVERSO
                     'company_id': svl.company_id.id,
                 }
                svl_to_create.append(svl_vals)

        # Crear todos los SVL inversos
        if svl_to_create:
            svl_obj.create(svl_to_create)

        # Cancelar los registros de ajuste originales
        if adjustments_to_cancel:
            adjustments_to_cancel.filtered(lambda adj: adj.state == 'posted').write({'state': 'cancel'})

        return reversed_moves

