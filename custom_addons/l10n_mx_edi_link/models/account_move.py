# -*- coding: utf-8 -*-

# Importaciones de Odoo
from odoo import models, fields, api, _
from odoo.exceptions import UserError # Para posibles validaciones previas
# import logging # Descomentar si se añaden logs específicos aquí
# _logger = logging.getLogger(__name__) # Descomentar si se añaden logs específicos aquí

class AccountMove(models.Model):
    """
    Hereda del modelo account.move para añadir la funcionalidad
    de lanzar el asistente de asociación manual de CFDI de Pagos (REP).
    """
    # Hereda del modelo base de asientos contables
    _inherit = 'account.move'

    # -------------------------------------------------------------------------
    # Métodos de Acción
    # -------------------------------------------------------------------------

    def action_open_associate_cfdi_wizard(self):
        """
        Este método es llamado por el botón 'Asociar CFDI Original' que
        agregaremos en la vista de formulario de account.move (tipo 'entry').

        Su propósito es abrir el asistente (wizard) definido en
        'l10n_mx_edi_link.associate_cfdi_wizard' para que el usuario
        pueda seleccionar el archivo XML del Complemento de Pago (REP) a asociar.

        Returns:
            dict: Un diccionario de acción de Odoo ('ir.actions.act_window')
                  que define cómo abrir la ventana del wizard.
        """
        # self.ensure_one() asegura que la acción se ejecute sobre un solo registro a la vez.
        self.ensure_one()

        # --- Validaciones Previas (Opcional pero recomendado) ---

        # 1. Verificar el tipo de movimiento permitido (AHORA SOLO 'entry')
        # Simplificado para permitir solo 'entry'
        if self.move_type != 'entry':
            # Si por alguna razón el botón fuera visible en un tipo no permitido, detenemos.
            # _logger.warning(f"Intento de abrir wizard de asociación CFDI en un asiento tipo '{self.move_type}' (ID: {self.id}). No permitido.")
            raise UserError(_("Esta acción solo está disponible para Asientos Contables de tipo 'Apunte Contable' destinados a Complementos de Pago."))

        # 2. Verificar si ya tiene un CFDI asociado y en estado 'sent'
        #    El botón debería ocultarse, pero verificamos de nuevo.
        if self.l10n_mx_edi_cfdi_state == 'sent' and self.l10n_mx_edi_cfdi_uuid:
             # _logger.warning(f"Intento de abrir wizard de asociación CFDI en un asiento (ID: {self.id}) que ya está en estado 'sent' con UUID '{self.l10n_mx_edi_cfdi_uuid}'.")
             raise UserError(_("Este asiento contable ya tiene un CFDI de Pago (REP) asociado y marcado como enviado (UUID: %s). No puede asociar otro.") % self.l10n_mx_edi_cfdi_uuid)

        # --- Construcción de la Acción para Abrir el Wizard ---
        # Busca la definición de la vista de formulario del wizard por su XML ID completo (nombre módulo + ID vista)
        wizard_form_view_id = self.env.ref('l10n_mx_edi_link.view_associate_cfdi_wizard_form').id

        # Devuelve un diccionario que Odoo interpreta como una acción de ventana.
        return {
            'name': _('Asociar CFDI de Pago Externo'), # Título que aparecerá en la ventana emergente
            'type': 'ir.actions.act_window',           # Tipo de acción: abrir una ventana
            'res_model': 'l10n_mx_edi_link.associate_cfdi_wizard', # El modelo del wizard a instanciar
            'view_mode': 'form',                       # Modo de vista principal (solo formulario para este wizard)
            'views': [(wizard_form_view_id, 'form')],  # Especifica la vista a usar (ID, tipo)
            'target': 'new',                           # 'new': abre en una ventana emergente (modal)
            'context': {
                 # Pasamos explícitamente el ID del asiento actual en el contexto.
                 # Esto puede ayudar a resolver el problema reportado donde el wizard
                 # mostraba un asiento incorrecto. El wizard debe ser ajustado
                 # para usar 'default_move_id' si está presente.
                 'default_move_id': self.id,
                 # Se podría fusionar con el contexto existente si fuera necesario:
                 # **self.env.context,
                 # 'default_move_id': self.id,
             },
        }
