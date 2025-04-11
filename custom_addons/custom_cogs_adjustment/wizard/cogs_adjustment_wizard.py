# -*- coding: utf-8 -*-
import logging # Para logging opcional de errores
from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_round

_logger = logging.getLogger(__name__)

class CogsAdjustmentWizard(models.TransientModel):
    _name = 'cogs.adjustment.wizard'
    _description = 'Wizard para Ajuste de Costo de Venta'

    invoice_id = fields.Many2one(
        'account.move',
        string='Factura Original',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    line_ids = fields.One2many(
        'cogs.adjustment.wizard.line',
        'wizard_id',
        string='Líneas a Ajustar',
    )
    accounting_date = fields.Date(
        string='Fecha Contable del Ajuste',
        required=True,
        default=fields.Date.context_today,
    )
    company_id = fields.Many2one(
        'res.company',
        related='invoice_id.company_id',
        string='Compañía',
        readonly=True,
        store=True, # Store para usar en dominios si es necesario
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        invoice = self.env['account.move'].browse(self.env.context.get('active_id'))
        if 'invoice_id' in fields_list and invoice:
            res['invoice_id'] = invoice.id
            # Aplicar filtro directamente aquí
            valid_lines = invoice.line_ids.filtered(
                lambda line: line.product_id and \
                             line.product_id.type == 'consu' and \
                             line.product_id.is_storable and \
                             line.product_id.valuation == 'real_time' and \
                             not line.display_type
            )
            lines_vals = []
            for line in valid_lines:
                # Podríamos pre-rellenar new_cost_unit con el costo estándar como sugerencia
                lines_vals.append(Command.create({
                    'invoice_line_id': line.id,
                    'new_cost_unit': line.product_id.standard_price # Sugerencia inicial
                }))
            if 'line_ids' in fields_list:
                res['line_ids'] = lines_vals
        return res

    def _find_stock_journal(self):
        """ Encuentra el diario de stock para la compañía """
        # Intenta encontrar por código 'STJ' (común, pero puede variar)
        stock_journal = self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', '=', 'general'),
            ('code', '=like', 'STJ%') # Buscar códigos que empiecen con STJ
        ], limit=1)

        if not stock_journal:
            # Fallback: buscar cualquier diario 'general' si no se encuentra por código
            stock_journal = self.env['account.journal'].search([
                ('company_id', '=', self.company_id.id),
                ('type', '=', 'general'),
            ], limit=1)

        if not stock_journal:
             raise UserError(_("No se pudo encontrar un Diario de Inventario (tipo General, código STJ o similar) para la compañía %s.") % self.company_id.name)
        return stock_journal


    def action_apply_adjustments(self):
        """
        Acción principal que ejecuta los ajustes de inventario y contabilidad.
        """
        self.ensure_one()
        AccountMove = self.env['account.move']
        precision = self.env['decimal.precision'].precision_get('Account') # Usar precisión contable

        # Validar que haya líneas con un costo nuevo >= 0
        lines_to_process = self.line_ids.filtered(lambda l: float_compare(l.new_cost_unit, 0, precision_digits=precision) >= 0)
        if not lines_to_process:
            raise UserError(_("No hay líneas con un nuevo costo unitario válido (>= 0) para procesar."))

        # Validar fecha contable
        if not self.accounting_date:
             raise ValidationError(_("Debe seleccionar una Fecha Contable para los ajustes."))

        # Encontrar diarios necesarios
        stock_journal = self._find_stock_journal()
        invoice_journal = self.invoice_id.journal_id # Usar el de la factura para el ajuste COGS

        # Acumuladores para el asiento COGS final
        cogs_adj_lines_vals_final = []
        inventory_adj_move_names = [] # Para referencia en chatter

        try:
            # Usar savepoint para asegurar atomicidad de todos los ajustes
            with self.env.cr.savepoint():
                # Iterar sobre cada línea del wizard a procesar
                for line in lines_to_process:
                    product = line.product_id
                    category = product.categ_id
                    adjustment_value = line.adjustment_value # Diferencia total calculada en la línea

                    # Si no hay diferencia, no hacer nada para esta línea
                    if float_compare(adjustment_value, 0, precision_digits=precision) == 0:
                        continue

                    # --- OBTENER CUENTAS (con validaciones) ---
                    # Cuenta COGS
                    cogs_account = product.property_account_expense_id or category.property_account_expense_categ_id
                    if not cogs_account:
                        raise UserError(_("No se encontró la Cuenta de Gasto (COGS) para el producto '%s' ni en su categoría '%s'.") % (product.display_name, category.display_name))

                    # Cuenta Salida Stock (Contrapartida para ambos JEs)
                    stock_output_account = category.property_stock_account_output_categ_id
                    if not stock_output_account:
                        raise UserError(_("No se encontró la Cuenta de Salida de Existencias en la categoría '%s'.") % category.display_name)

                    # Cuenta Valoración Stock (Para el JE de Inventario)
                    stock_valuation_account = product.property_stock_valuation_account_id or category.property_stock_valuation_account_id
                    if not stock_valuation_account:
                         raise UserError(_("No se encontró la Cuenta de Valoración de Existencias para el producto '%s' ni en su categoría '%s'.") % (product.display_name, category.display_name))

                    # --- PASO 1: CREAR AJUSTE CONTABLE DE INVENTARIO (MANUAL) ---
                    inv_adj_line_list = []
                    adj_value_abs = abs(adjustment_value)
                    ref_text = f"Ajuste Inventario Fact: {self.invoice_id.name} - Prod: {product.display_name}"

                    if adjustment_value > 0: # Nuevo costo es mayor -> Aumentar Valoración (Db), Cr Salida
                        debit_account_id = stock_valuation_account.id
                        credit_account_id = stock_output_account.id
                    else: # Nuevo costo es menor -> Disminuir Valoración (Cr), Db Salida
                        debit_account_id = stock_output_account.id
                        credit_account_id = stock_valuation_account.id

                    inv_adj_line_list.append(Command.create({
                        'name': ref_text,
                        'account_id': debit_account_id,
                        'debit': adj_value_abs,
                        'credit': 0.0,
                        'partner_id': self.invoice_id.partner_id.id, # Usar partner de la factura
                        'product_id': product.id, # Relacionar con producto
                        'quantity': line.quantity, # Informativo
                    }))
                    inv_adj_line_list.append(Command.create({
                        'name': ref_text,
                        'account_id': credit_account_id,
                        'debit': 0.0,
                        'credit': adj_value_abs,
                        'partner_id': self.invoice_id.partner_id.id,
                        'product_id': product.id,
                        'quantity': line.quantity,
                    }))

                    inv_move_vals = {
                        'ref': ref_text,
                        'journal_id': stock_journal.id, # Usar el diario de inventario encontrado
                        'date': self.accounting_date,
                        'move_type': 'entry',
                        'line_ids': inv_adj_line_list,
                        'source_invoice_id': self.invoice_id.id, # Vincular a factura origen
                    }
                    inventory_adj_move = AccountMove.create(inv_move_vals)
                    inventory_adj_move.action_post()
                    inventory_adj_move_names.append(inventory_adj_move.display_name)
                    _logger.info(f"Creado y publicado ajuste de inventario: {inventory_adj_move.display_name}")

                    # TODO OPCIONAL: Crear stock.move manual si es necesario para trazabilidad de stock.
                    # Esto dependerá de si solo se necesita el ajuste contable o también el de stock.
                    # Por ahora nos centramos en el ajuste contable según la especificación de cuentas.


                    # --- PASO 2: ACUMULAR LÍNEAS PARA AJUSTE COGS FINAL ---
                    cogs_ref_text = f"Ajuste COGS: {product.display_name} (Fact: {self.invoice_id.name})"
                    if adjustment_value > 0: # Aumentar COGS (Db), Cr Salida
                        debit_cogs_acc_id = cogs_account.id
                        credit_cogs_acc_id = stock_output_account.id
                    else: # Disminuir COGS (Cr), Db Salida
                        debit_cogs_acc_id = stock_output_account.id
                        credit_cogs_acc_id = cogs_account.id

                    cogs_adj_lines_vals_final.append(Command.create({
                        'name': cogs_ref_text,
                        'account_id': debit_cogs_acc_id,
                        'debit': adj_value_abs,
                        'credit': 0.0,
                        'partner_id': self.invoice_id.partner_id.id,
                        'product_id': product.id,
                        'quantity': line.quantity,
                    }))
                    cogs_adj_lines_vals_final.append(Command.create({
                        'name': cogs_ref_text,
                        'account_id': credit_cogs_acc_id,
                        'debit': 0.0,
                        'credit': adj_value_abs,
                        'partner_id': self.invoice_id.partner_id.id,
                        'product_id': product.id,
                        'quantity': line.quantity,
                    }))

                # --- Crear y Publicar el Asiento de Ajuste COGS (si hay líneas acumuladas) ---
                if cogs_adj_lines_vals_final:
                    cogs_final_move_vals = {
                        'ref': f"Ajuste COGS Global Factura: {self.invoice_id.name}",
                        'journal_id': invoice_journal.id, # Usar diario de la factura
                        'date': self.accounting_date,
                        'move_type': 'entry',
                        'line_ids': cogs_adj_lines_vals_final,
                        'source_invoice_id': self.invoice_id.id, # Vincular a factura origen
                    }
                    cogs_adj_move = AccountMove.create(cogs_final_move_vals)
                    cogs_adj_move.action_post()
                    _logger.info(f"Creado y publicado asiento de ajuste COGS: {cogs_adj_move.display_name}")

                    # Registrar mensaje en chatter de la factura original
                    self.invoice_id.message_post(body=_(
                        "Se ha generado un ajuste de Costo de Venta con fecha %s. "
                        "Asiento de ajuste COGS: %s. Asientos de ajuste de inventario relacionados: %s"
                    ) % (self.accounting_date, cogs_adj_move.display_name, ', '.join(inventory_adj_move_names)))

        except (UserError, ValidationError) as e:
            # Captura errores de validación o usuario esperados
            # El savepoint se revierte automáticamente al salir del 'with'
            raise e # Re-lanzar error para mostrarlo al usuario
        except Exception as e:
            # Captura errores técnicos inesperados
            # El savepoint se revierte automáticamente
            _logger.error("Error técnico inesperado al aplicar ajuste COGS para Factura %s: %s", self.invoice_id.name, str(e), exc_info=True)
            raise UserError(_("Ocurrió un error técnico inesperado. Contacte al administrador. Error: %s") % str(e))

        # Si todo fue bien, cerrar el wizard
        return {'type': 'ir.actions.act_window_close'}


class CogsAdjustmentWizardLine(models.TransientModel):
    _name = 'cogs.adjustment.wizard.line'
    _description = 'Línea del Wizard para Ajuste de Costo de Venta'

    wizard_id = fields.Many2one('cogs.adjustment.wizard', string='Wizard', required=True, ondelete='cascade')
    invoice_line_id = fields.Many2one('account.move.line', string='Línea de Factura', required=True, readonly=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Producto', related='invoice_line_id.product_id', readonly=True)
    quantity = fields.Float(string='Cantidad', related='invoice_line_id.quantity', readonly=True)
    currency_id = fields.Many2one('res.currency', related='wizard_id.invoice_id.currency_id', readonly=True)

    original_cost_total = fields.Monetary(
        string='Costo Original Total',
        compute='_compute_original_cost',
        readonly=True,
        currency_field='currency_id',
        help="Costo total registrado (o que debió registrarse) en el asiento de la factura para esta línea vía COGS."
    )
    new_cost_unit = fields.Float(
        string='Nuevo Costo Unitario',
        digits='Product Price',
        required=True,
        default=0.0,
        help="Introduce el costo unitario correcto para este producto."
    )
    adjustment_value = fields.Monetary(
        string='Valor del Ajuste Total',
        compute='_compute_adjustment_value',
        readonly=True,
        currency_field='currency_id',
        help="Diferencia total a ajustar: (Nuevo Costo Unitario * Cantidad) - Costo Original Total."
    )

    @api.depends('invoice_line_id', 'invoice_line_id.move_id.line_ids')
    def _compute_original_cost(self):
        """ Calcula el costo original buscando en el asiento de la factura. """
        for line in self:
            original_cost = 0.0
            if line.invoice_line_id and line.product_id:
                move = line.invoice_line_id.move_id
                product = line.product_id
                category = product.categ_id
                # Determinar la cuenta COGS esperada
                cogs_account = product.property_account_expense_id or category.property_account_expense_categ_id

                if cogs_account:
                    # Buscar líneas en el asiento original que afecten la cuenta COGS para este producto
                    # Filtrar por la cuenta y el producto específico de esta línea de wizard
                    related_lines = move.line_ids.filtered(
                        lambda l: l.account_id == cogs_account and l.product_id == product and \
                                  l.parent_state == 'posted' # Asegurar que sean del asiento publicado
                                  # Podríamos necesitar una lógica más compleja si una factura tiene MÚLTIPLES líneas del MISMO producto
                                  # y necesitamos identificar el costo asociado a ESTA invoice_line_id específica.
                                  # Por simplicidad inicial, sumamos todo lo de ese producto en esa cuenta.
                    )
                    # El costo es el débito en la cuenta COGS
                    original_cost = sum(related_lines.mapped('debit')) - sum(related_lines.mapped('credit'))
                else:
                     # Si no hay cuenta COGS definida, no podemos determinar costo (asumimos 0)
                     _logger.warning("No se pudo determinar la cuenta COGS para producto %s al calcular costo original.", product.display_name)

            line.original_cost_total = original_cost

    @api.depends('new_cost_unit', 'quantity', 'original_cost_total')
    def _compute_adjustment_value(self):
        """ Calcula la diferencia total a ajustar. """
        precision = self.env['decimal.precision'].precision_get('Account')
        for line in self:
            # Asegurarse que new_cost_unit sea float
            new_cost_unit_float = float(line.new_cost_unit or 0.0)
            new_total_cost = new_cost_unit_float * line.quantity
            # Calcular la diferencia
            line.adjustment_value = float_round(new_total_cost - line.original_cost_total, precision_digits=precision)