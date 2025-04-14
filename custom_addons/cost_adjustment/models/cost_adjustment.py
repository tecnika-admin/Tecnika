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
        readonly="state != 'draft'", # v18 syntax
        help="Fecha en la que se aplicará contablemente el asiento de ajuste."
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario Contable',
        required=True,
        domain="[('type', '=', 'general')]",
        readonly="state != 'draft'", # v18 syntax
        help="Diario donde se registrará el asiento contable del ajuste."
    )
    reason = fields.Text(
        string='Motivo del Ajuste',
        required=True,
        readonly="state != 'draft'", # v18 syntax
        help="Explicación detallada de por qué se realiza este ajuste de costo."
    )
    original_invoice_id = fields.Many2one(
        'account.move',
        string='Factura Original',
        required=True,
        # Dominio actualizado: quitado edi_state (RF02 Modificado)
        domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('l10n_mx_edi_cfdi_uuid', '!=', False)]",
        readonly="state != 'draft'", # v18 syntax
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
        readonly="state != 'draft'", # v18 syntax
        copy=True,
    )
    auto_post_entry = fields.Boolean(
        string='¿Publicar Asiento Automáticamente?',
        default=False,
        readonly="state != 'draft'", # v18 syntax
        help="Si se marca, el asiento de ajuste se publicará automáticamente al confirmar. "
             "Si no, quedará en estado borrador."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='journal_id.company_id',
        store=True,
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='journal_id.currency_id',
        store=True,
        readonly=True
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
        # Es importante crear el SVL *después* de crear el asiento de ajuste
        # pero *antes* de publicarlo, para que el SVL pueda referenciar el asiento.
        self._create_stock_valuation_layers(move)

        # 4. Publicar Asiento (Opcional)
        if self.auto_post_entry:
            # Validar asiento antes de publicar
            move._post(soft=False) # Usar _post en lugar de action_post si se requiere validación interna

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
            # Usamos cancel=True para que el asiento original también se marque como reversado si es posible
            moves_to_reverse._reverse_moves(cancel=True)

        # Cancelar asientos en borrador si existen
        draft_moves = self.mapped('adjustment_move_id').filtered(lambda m: m.state == 'draft')
        if draft_moves:
            # Usar button_cancel podría requerir que esté en modo borrador primero
            draft_moves.button_draft() # Asegurar que está en borrador
            draft_moves.button_cancel()

        self.write({'state': 'cancel'})
        return True

    def action_draft(self):
        """ Pasa el ajuste de nuevo a borrador (si está cancelado) """
        self.ensure_one()
        if self.adjustment_move_id and self.adjustment_move_id.state != 'cancel':
             raise UserError(_("No puede pasar a borrador un ajuste cuyo asiento contable no está cancelado."))
        # Opcional: ¿Deberíamos eliminar/cancelar el asiento de ajuste si existe?
        # Por seguridad, es mejor requerir que se cancele manualmente primero.
        self.write({'state': 'draft'})
        return True

    # --- Métodos de Ayuda ---
    def _check_period_lock_date(self):
        """ Valida si la fecha del ajuste cae en un periodo bloqueado. Ref: RF08 """
        self.ensure_one()
        # Crear un diccionario con los valores mínimos para la validación
        move_vals = {
            'journal_id': self.journal_id.id,
            'date': self.date_adjustment,
            'company_id': self.company_id.id,
        }
        # Instanciar un asiento temporal para llamar al método de validación
        move_for_check = self.env['account.move'].new(move_vals)
        try:
            # Llamar a la validación (puede variar ligeramente el método exacto en v18)
            move_for_check._check_fiscalyear_lock_date()
            # O directamente:
            # self.env['account.move']._check_balanced(move_for_check) # Esto incluye la validación de fecha
            # self.env['account.move']._check_lock_dates(move_for_check) # Método más específico
        except UserError as e:
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
            'move_type': 'entry',
            'cost_adjustment_origin_id': self.id, # Trazabilidad (RF07)
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'line_ids': [],
        }

    def _create_adjustment_move(self):
        """ Crea el asiento contable (account.move) y sus líneas. Ref: RF04 """
        self.ensure_one()
        move_vals = self._prepare_adjustment_move_vals()
        move_lines_vals = []

        for line in self.line_ids:
            # Re-evaluar el amount por si acaso
            line._compute_costs_and_adjustment()
            if self.currency_id.is_zero(line.adjustment_amount):
                continue # No crear apuntes si el ajuste es cero

            line_vals = line._prepare_adjustment_move_lines_vals()
            move_lines_vals.extend(line_vals)

        if not move_lines_vals:
             raise UserError(_("No se generaron líneas de asiento válidas para el ajuste {} (verifique costos).").format(self.name))

        move_vals['line_ids'] = [(0, 0, vals) for vals in move_lines_vals]
        move = self.env['account.move'].create(move_vals)
        return move

    def _create_stock_valuation_layers(self, adjustment_move):
        """ Crea las capas de valoración (SVL) para cada línea de ajuste. Ref: RF05 """
        self.ensure_one()
        svl_obj = self.env['stock.valuation.layer']
        svl_vals_list = []

        for line in self.line_ids:
             if self.currency_id.is_zero(line.adjustment_amount):
                 continue
             svl_vals = line._prepare_stock_valuation_layer_vals(adjustment_move)
             if svl_vals:
                 svl_vals_list.append(svl_vals)
             else:
                 _logger.warning(f"No se pudo preparar SVL para la línea de ajuste {line.id} (Ajuste: {self.name}) - Posiblemente no se encontró el stock.move original.")
                 # Considerar si lanzar un error o permitir continuar sin SVL
                 # raise UserError(_("No se pudo encontrar el movimiento de stock original para el producto {} en la línea de ajuste. No se puede crear la capa de valoración.").format(line.product_id.display_name))


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
        # El dominio se aplica en la vista XML
        help="Línea específica de la factura original cuyo costo se ajustará."
    )
    # Campos relacionados/calculados
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
    # Modificado: Quitado compute y store, se asigna por onchange
    analytic_distribution = fields.Json(
        string='Distribución Analítica',
        readonly=True, # Se asigna al cambiar la línea original
        copy=False, # Evitar copiarla directamente si se duplica el ajuste
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
        store=False,
        readonly=True
    )
    computed_account_valuation_id = fields.Many2one(
        'account.account',
        string='Cuenta Valoración/Salida (Calculada)',
        compute='_compute_accounts',
        store=False,
        readonly=True
    )

    # --- Onchange para copiar analítica ---
    @api.onchange('original_invoice_line_id')
    def _onchange_original_invoice_line_id(self):
        """ Al cambiar la línea de factura original, copia su distribución analítica. """
        if self.original_invoice_line_id:
            # Copia la distribución analítica
            self.analytic_distribution = self.original_invoice_line_id.analytic_distribution
            # Recalcula costos (aunque ya hay un compute, el onchange asegura la actualización inmediata en UI)
            self._compute_costs_and_adjustment()
            self._compute_accounts()
        else:
            self.analytic_distribution = False
            self.original_cost_total = 0.0
            self.current_average_cost = 0.0
            self.adjustment_amount = 0.0
            self.computed_account_cogs_id = False
            self.computed_account_valuation_id = False


    # --- Métodos Compute ---
    # Se mantiene el compute por si hay cambios en el producto o fecha del ajuste
    @api.depends('original_invoice_line_id', 'product_id', 'quantity', 'adjustment_id.date_adjustment')
    def _compute_costs_and_adjustment(self):
        """
        Calcula el costo original (buscando SVL), el costo actual (standard_price)
        y el importe del ajuste.
        Ref: RF01 (Campos), RF03 (Cálculo)
        """
        svl_obj = self.env['stock.valuation.layer']
        # Usar la fecha del ajuste para obtener el costo histórico del producto
        adjustment_date = self.adjustment_id.date_adjustment or fields.Date.context_today(self)

        for line in self:
            original_cost = 0.0
            current_cost = 0.0
            adjustment = 0.0
            product = line.product_id

            if line.original_invoice_line_id and product:
                # 1. Obtener Costo Original (desde SVL asociado al stock.move)
                stock_move = line._find_original_stock_move()
                if stock_move:
                    domain = [
                        ('stock_move_id', '=', stock_move.id),
                        ('product_id', '=', product.id),
                        ('company_id', '=', line.company_id.id),
                    ]
                    # Sumar todos los SVL de ese movimiento por si hubiera correcciones previas
                    svls = svl_obj.search(domain)
                    original_cost = abs(sum(svls.mapped('value'))) # Suma y valor absoluto

                # 2. Obtener Costo Promedio en la fecha del ajuste
                # Usamos standard_price como fallback, pero intentamos obtener costo histórico si es posible/necesario
                # Para AVCO, standard_price suele reflejar el costo actual.
                # Si se necesitara el costo exacto al momento de la factura original, la lógica sería más compleja.
                # Mantenemos la lógica original del requerimiento: usar costo actual.
                # Podríamos usar product.with_context(to_date=adjustment_date).standard_price si la lógica lo soportara
                current_cost = product.standard_price # Costo unitario actual

                # 3. Calcular Ajuste
                cost_total_actual = current_cost * line.quantity
                adjustment = cost_total_actual - original_cost

            line.original_cost_total = original_cost
            line.current_average_cost = current_cost
            line.adjustment_amount = adjustment

    # Eliminado compute para analytic_distribution, se usa onchange

    @api.depends('product_id', 'company_id')
    def _compute_accounts(self):
        """ Calcula y muestra las cuentas que se usarán en el asiento. Ref: RF03 """
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
    def _find_original_stock_move(self):
        """
        Encuentra el stock.move original asociado a la línea de factura.
        Depende de la trazabilidad SO -> Factura -> Stock Move.
        Ref: RF05 (Paso 1)
        """
        self.ensure_one()
        aml = self.original_invoice_line_id
        if not aml or not self.product_id:
            return self.env['stock.move'] # Devuelve recordset vacío

        # Buscar movimientos de stock cuyas líneas de asiento contengan esta línea de factura
        # Esta es una relación M2M inversa en stock.move ('account_move_line_ids')
        # O buscar a través de la línea de venta
        stock_moves = self.env['stock.move']
        if aml.sale_line_ids:
            # Es más fiable buscar los movimientos de las líneas de venta asociadas
            domain = [
                ('sale_line_id', 'in', aml.sale_line_ids.ids),
                ('product_id', '=', self.product_id.id),
                ('company_id', '=', self.company_id.id),
                ('state', '=', 'done'),
                # Filtrar por movimientos de salida de clientes
                ('location_dest_id.usage', '=', 'customer'),
            ]
            # Puede haber varios (ej. backorders). ¿Cómo elegir? El más reciente? El que cuadre cantidad?
            # Por ahora, si hay varios, podríamos tener problemas para identificar el SVL correcto.
            # Idealmente, la relación debería ser más directa o única.
            # Consideremos sumarizar si hay varios movimientos para la misma línea de venta?
            stock_moves = self.env['stock.move'].search(domain, order='date desc') # Ordenar por fecha puede ayudar
            if len(stock_moves) > 1:
                 _logger.warning(f"Múltiples stock.move encontrados para la línea de factura {aml.id} (Producto: {self.product_id.name}). Se usará el más reciente: {stock_moves[0].name}")
                 return stock_moves[0] # Devolver el más reciente como heurística
            elif stock_moves:
                 return stock_moves # Devolver el único encontrado

        # Si no se encontró por línea de venta, intentar buscar por 'account_move_line_ids' (menos común)
        # Esta relación puede no existir o no ser fiable
        # stock_moves = self.env['stock.move'].search([
        #     ('account_move_line_ids', 'in', aml.id),
        #     ('product_id', '=', self.product_id.id),
        #     ('company_id', '=', self.company_id.id),
        #     ('state', '=', 'done'),
        # ])

        if not stock_moves:
             _logger.warning(f"No se encontró stock.move para la línea de factura {aml.id} (Producto: {self.product_id.name})")
             return self.env['stock.move'] # Devuelve recordset vacío

        # Debería ser solo uno en este caso si la relación existe
        return stock_moves[0] if stock_moves else self.env['stock.move']


    def _get_adjustment_accounts(self):
        """ Obtiene las cuentas COGS y Valoración para el asiento. Ref: RF03 """
        self.ensure_one()
        if not self.product_id:
            raise UserError(_("No se puede determinar cuentas sin un producto en la línea {}.").format(self.id))

        # Asegurar que se obtienen las cuentas para la compañía correcta
        product_in_company = self.product_id.with_company(self.company_id)
        accounts = product_in_company._get_product_accounts()
        acc_cogs = accounts.get('expense')
        acc_valuation = accounts.get('stock_output')

        if not acc_cogs or not acc_valuation:
             categ = product_in_company.categ_id
             raise UserError(
                 _("No se pudieron determinar las cuentas de Costo de Venta (Gasto: {}) y/o Salida de Stock (Valoración: {}) para el producto '{}' (Categoría: {}). Verifique la configuración contable de la categoría del producto.")
                 .format(acc_cogs.code if acc_cogs else 'N/A',
                         acc_valuation.code if acc_valuation else 'N/A',
                         product_in_company.display_name,
                         categ.display_name)
             )

        return acc_cogs, acc_valuation


    def _prepare_adjustment_move_lines_vals(self):
        """ Prepara los valores para las DOS líneas del asiento contable. Ref: RF04 """
        self.ensure_one()
        vals_list = []
        # Usar la moneda de la compañía para comparar con cero
        company_currency = self.company_id.currency_id
        if company_currency.is_zero(self.adjustment_amount):
             return [] # No generar líneas si el ajuste es cero

        amount = self.adjustment_amount
        acc_cogs, acc_valuation = self._get_adjustment_accounts()
        partner_id = self.adjustment_id.original_invoice_id.partner_id.id
        name = _("Ajuste Costo: {}").format(self.product_id.display_name)

        # Determinar débito/crédito
        debit_cogs, credit_cogs, debit_val, credit_val = 0.0, 0.0, 0.0, 0.0
        if not company_currency.is_zero(amount): # Doble chequeo por si acaso
            if amount > 0: # Costo real > original -> Aumentar COGS (Débito), Crédito Valoración
                debit_cogs = amount
                credit_val = amount
            else: # Costo real < original -> Disminuir COGS (Crédito), Débito Valoración
                credit_cogs = abs(amount)
                debit_val = abs(amount)

            # Línea COGS
            vals_cogs = {
                'name': name,
                'account_id': acc_cogs.id,
                'debit': debit_cogs,
                'credit': credit_cogs,
                'analytic_distribution': self.analytic_distribution or False, # RF06
                'partner_id': partner_id,
                'product_id': self.product_id.id,
                'quantity': self.quantity,
                'currency_id': self.currency_id.id, # Asegurar moneda
            }
            vals_list.append(vals_cogs)

            # Línea Valoración
            vals_valuation = {
                'name': name,
                'account_id': acc_valuation.id,
                'debit': debit_val,
                'credit': credit_val,
                'analytic_distribution': False, # Analítica no aplica aquí (RF06)
                'partner_id': partner_id,
                'product_id': self.product_id.id,
                'quantity': self.quantity,
                'currency_id': self.currency_id.id, # Asegurar moneda
            }
            vals_list.append(vals_valuation)

        return vals_list

    def _prepare_stock_valuation_layer_vals(self, adjustment_move):
         """ Prepara los valores para crear el SVL de ajuste. Ref: RF05 """
         self.ensure_one()
         stock_move = self._find_original_stock_move()
         if not stock_move:
             _logger.warning(f"No se creará SVL para la línea de ajuste {self.id} (Producto: {self.product_id.name}) porque no se encontró el stock.move original.")
             return {} # No se puede crear SVL sin el movimiento original

         description = _("Ajuste Costo - Fact: {} - Ajuste: {}").format(
             self.adjustment_id.original_invoice_id.name,
             self.adjustment_id.name
         )

         # El valor debe estar en la moneda de la compañía
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
             'value': value_in_company_currency, # Usar valor en moneda de compañía
             'remaining_qty': 0,
             'remaining_value': value_in_company_currency,
             'description': description,
             'account_move_id': adjustment_move.id,
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
        # Asegurarse de que default_values_list sea una lista si es None
        default_values_list = default_values_list or [{} for _ in self]
        reversed_moves = super(AccountMove, self)._reverse_moves(default_values_list, cancel=cancel)

        svl_obj = self.env['stock.valuation.layer']
        adjustment_obj = self.env['cost.adjustment']
        svl_to_create = []
        adjustments_to_cancel = adjustment_obj # Vacío inicialmente

        # Iterar sobre los asientos originales que se están reversando (self)
        # y encontrar su correspondiente asiento reverso en reversed_moves
        for move, reversed_move in zip(self, reversed_moves):
            if move.cost_adjustment_origin_id:
                # Este 'move' es el asiento de ajuste ORIGINAL que se está reversando
                adjustment = move.cost_adjustment_origin_id
                adjustments_to_cancel |= adjustment # Acumular ajustes a cancelar

                # Buscar los SVL creados por este asiento de ajuste original
                original_svls = svl_obj.search([('account_move_id', '=', move.id)])

                for svl in original_svls:
                    # Preparar SVL inverso
                    description = _("Reversión Ajuste Costo - Fact: {} - Ajuste: {} - Ref Rev: {}").format(
                        adjustment.original_invoice_id.name,
                        adjustment.name,
                        reversed_move.name
                    )
                    # El valor del SVL inverso debe estar en moneda de compañía
                    value_in_company_currency = -svl.value

                    svl_vals = {
                         'create_date': reversed_move.date, # Fecha del asiento reverso
                         'stock_move_id': svl.stock_move_id.id, # Mismo stock_move original
                         'product_id': svl.product_id.id,
                         'quantity': 0,
                         'uom_id': svl.uom_id.id,
                         'unit_cost': 0,
                         'value': value_in_company_currency, # Valor inverso en moneda compañía
                         'remaining_qty': 0,
                         'remaining_value': value_in_company_currency,
                         'description': description,
                         'account_move_id': reversed_move.id, # Asiento REVERSO
                         'company_id': svl.company_id.id,
                     }
                    svl_to_create.append(svl_vals)

        # Crear todos los SVL inversos
        if svl_to_create:
            svl_obj.create(svl_to_create)

        # Cancelar los registros de ajuste originales (solo si estaban publicados)
        if adjustments_to_cancel:
            adjustments_to_cancel.filtered(lambda adj: adj.state == 'posted').write({'state': 'cancel'})

        return reversed_moves

