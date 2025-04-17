# -*- coding: utf-8 -*-

# Importaciones de Odoo
from odoo import models, fields, api, _
from odoo.exceptions import UserError # Para posibles validaciones previas

class AccountMove(models.Model):
    """
    Hereda del modelo account.move para añadir la funcionalidad
    de lanzar el asistente de asociación manual de CFDI.
    """
    # Hereda del modelo base de asientos contables
    _inherit = 'account.move'

    # -------------------------------------------------------------------------
    # Métodos de Acción
    # -------------------------------------------------------------------------

    def action_open_associate_cfdi_wizard(self):
        """
        Este método es llamado por el botón 'Asociar CFDI Original' que
        agregaremos en la vista de formulario de account.move.

        Su propósito es abrir el asistente (wizard) definido en
        'l10n_mx_edi_link.associate_cfdi_wizard' para que el usuario
        pueda seleccionar el archivo XML a asociar.

        Returns:
            dict: Un diccionario de acción de Odoo ('ir.actions.act_window')
                  que define cómo abrir la ventana del wizard.
        """
        # self.ensure_one() asegura que la acción se ejecute sobre un solo registro a la vez.
        # Es importante porque el wizard está diseñado para trabajar con un 'active_id'.
        self.ensure_one()

        # --- Validaciones Previas (Opcional pero recomendado) ---
        # Aunque la visibilidad del botón controlará esto, una validación aquí
        # añade una capa extra de seguridad.

        # 1. Verificar el tipo de movimiento permitido (según los requisitos)
        allowed_move_types = ('out_invoice', 'entry') # Factura Cliente y Asiento (para REP)
        if self.move_type not in allowed_move_types:
            # Si por alguna razón el botón fuera visible en un tipo no permitido, detenemos.
            # _logger.warning(f"Intento de abrir wizard de asociación CFDI en un asiento tipo '{self.move_type}' (ID: {self.id}). No permitido.") # Necesitaría importar logging
            raise UserError(_("Esta acción solo está disponible para Facturas de Cliente y Asientos Contables destinados a Complementos de Pago."))

        # 2. Verificar si ya tiene un CFDI asociado y en estado 'sent'
        #    El botón debería ocultarse, pero verificamos de nuevo.
        if self.l10n_mx_edi_cfdi_state == 'sent' and self.l10n_mx_edi_cfdi_uuid:
             # _logger.warning(f"Intento de abrir wizard de asociación CFDI en un asiento (ID: {self.id}) que ya está en estado 'sent' con UUID '{self.l10n_mx_edi_cfdi_uuid}'.") # Necesitaría importar logging
             raise UserError(_("Este asiento contable ya tiene un CFDI asociado y marcado como enviado (UUID: %s). No puede asociar otro.") % self.l10n_mx_edi_cfdi_uuid)

        # --- Construcción de la Acción para Abrir el Wizard ---
        # Busca la definición de la vista de formulario del wizard por su XML ID completo (nombre módulo + ID vista)
        # ID de vista simplificado y nombre de módulo corregido
        wizard_form_view_id = self.env.ref('l10n_mx_edi_link.view_associate_cfdi_wizard_form').id

        # Devuelve un diccionario que Odoo interpreta como una acción de ventana.
        return {
            'name': _('Asociar CFDI Original Externo'), # Título que aparecerá en la ventana emergente
            'type': 'ir.actions.act_window',           # Tipo de acción: abrir una ventana
            # Modelo del wizard con nombre de módulo corregido
            'res_model': 'l10n_mx_edi_link.associate_cfdi_wizard', # El modelo del wizard a instanciar
            'view_mode': 'form',                       # Modo de vista principal (solo formulario para este wizard)
            'views': [(wizard_form_view_id, 'form')],  # Especifica la vista a usar (ID, tipo)
            'target': 'new',                           # 'new': abre en una ventana emergente (modal)
                                                       # 'current': reemplazaría la vista actual
            'context': self.env.context,               # Pasa el contexto actual. Odoo añade automáticamente 'active_id',
                                                       # 'active_model', etc., que son usados por el default del wizard.
        }

