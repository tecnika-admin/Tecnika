# -*- coding: utf-8 -*-

# Importaciones de Odoo
from odoo import models, fields, api, _
from odoo.exceptions import UserError # Import needed for raising errors

# import logging # Descomentar si se añaden logs específicos aquí
# _logger = logging.getLogger(__name__) # Descomentar si se añaden logs específicos aquí

class AccountMove(models.Model):
    """
    Hereda del modelo account.move para:
    1. Añadir la funcionalidad de lanzar el asistente de asociación manual de CFDI de Pagos (REP).
    2. Interceptar la acción estándar de 'Actualizar Pagos' para prevenir la re-generación
       si un REP ya fue asociado manualmente a un pago relacionado.
    """
    # Hereda del modelo base de asientos contables
    _inherit = 'account.move'

    # -------------------------------------------------------------------------
    # Métodos de Acción (Wizard Launcher)
    # -------------------------------------------------------------------------

    def action_open_associate_cfdi_wizard(self):
        """
        Este método es llamado por el botón 'Asociar CFDI Pago (REP)' que
        agregaremos en la vista de formulario de account.move (tipo 'entry').

        Su propósito es abrir el asistente (wizard) definido en
        'l10n_mx_edi_link.associate_cfdi_wizard' para que el usuario
        pueda seleccionar el archivo XML del Complemento de Pago (REP) a asociar.

        Returns:
            dict: Un diccionario de acción de Odoo ('ir.actions.act_window')
                  que define cómo abrir la ventana del wizard.
        """
        self.ensure_one()

        # --- Validaciones Previas ---
        if self.move_type != 'entry':
            raise UserError(_("Esta acción solo está disponible para Asientos Contables de tipo 'Apunte Contable' destinados a Complementos de Pago."))

        if self.l10n_mx_edi_cfdi_state == 'sent' and self.l10n_mx_edi_cfdi_uuid:
             raise UserError(_("Este asiento contable ya tiene un CFDI de Pago (REP) asociado y marcado como enviado (UUID: %s). No puede asociar otro.") % self.l10n_mx_edi_cfdi_uuid)

        # --- Construcción de la Acción para Abrir el Wizard ---
        wizard_form_view_id = self.env.ref('l10n_mx_edi_link.view_associate_cfdi_wizard_form').id
        return {
            'name': _('Asociar CFDI de Pago Externo'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_mx_edi_link.associate_cfdi_wizard',
            'view_mode': 'form',
            'views': [(wizard_form_view_id, 'form')],
            'target': 'new',
            'context': {
                 'default_move_id': self.id,
             },
        }

    # -------------------------------------------------------------------------
    # Métodos Heredados (Standard Flow Interception)
    # -------------------------------------------------------------------------

    def l10n_mx_edi_cfdi_invoice_try_update_payments(self):
        """
        Hereda la acción estándar del botón 'Actualizar Pagos' en facturas.
        Añade una validación para prevenir la ejecución si alguno de los pagos
        conciliados ya tiene un CFDI (REP) asociado (manual o automáticamente).
        """
        # Asegura que se ejecute sobre un solo registro (la factura)
        self.ensure_one()

        # La lógica de generar REP solo aplica a facturas de cliente PPD
        if self.move_type == 'out_invoice' and self.l10n_mx_edi_payment_policy == 'PPD':
            # Buscar los asientos de pago ('entry') conciliados con esta factura
            payment_moves = self.env['account.move']
            # Iterar sobre las líneas de la factura que participan en la conciliación (cuentas por cobrar)
            for line in self.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable'):
                # Obtener todas las conciliaciones parciales de esta línea
                partials = line.matched_debit_ids | line.matched_credit_ids
                # Para cada conciliación, encontrar la línea del otro asiento (el pago)
                for partial in partials:
                    counterpart_line = partial.debit_move_id if partial.credit_move_id == line else partial.credit_move_id
                    # Asegurarse de que el otro asiento sea de tipo 'entry' y no sea la factura misma
                    if counterpart_line.move_id != self and counterpart_line.move_id.move_type == 'entry':
                        payment_moves |= counterpart_line.move_id

            # Verificar si alguno de los pagos encontrados ya tiene un CFDI asociado ('sent')
            if any(payment.l10n_mx_edi_cfdi_state == 'sent' for payment in payment_moves):
                # Si al menos un pago ya tiene CFDI, bloquear la acción y mostrar error
                raise UserError(_(
                    "No se puede generar un nuevo Complemento de Pago para esta factura porque al menos uno de los pagos asociados (%s) ya tiene un CFDI (REP) vinculado (UUID: %s).") %
                    (payment_moves.filtered(lambda p: p.l10n_mx_edi_cfdi_state == 'sent')[0].display_name,
                     payment_moves.filtered(lambda p: p.l10n_mx_edi_cfdi_state == 'sent')[0].l10n_mx_edi_cfdi_uuid)
                )

        # Si no se encontró ningún pago con CFDI asociado (o si no es una factura PPD),
        # proceder con la ejecución normal del método original.
        return super().l10n_mx_edi_cfdi_invoice_try_update_payments()

