# -*- coding: utf-8 -*-

# Importaciones estándar de Python
import base64
import logging
import xml.etree.ElementTree as ET # Para parsear XML
import datetime # Import needed for time combination

# Importaciones de Odoo
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError # Para errores y validaciones
from odoo.tools import float_is_zero # Useful for checking amounts if needed later

# Configuración del logger para registrar información y errores
_logger = logging.getLogger(__name__)

class AssociateCfdiWizard(models.TransientModel):
    """
    Asistente (Wizard) para asociar manualmente un archivo XML de Complemento de Pago (REP)
    externo a un registro de asiento contable de pago (tipo 'entry') existente.
    Permite al usuario seleccionar un archivo XML adjunto al asiento,
    extrae y valida el UUID (Folio Fiscal), actualiza el asiento contable,
    crea el registro correspondiente en l10n_mx_edi.document, e intenta
    refrescar las facturas relacionadas.
    """
    # Nombre técnico del modelo del wizard
    _name = 'l10n_mx_edi_link.associate_cfdi_wizard'
    # Descripción del modelo que aparece en la interfaz de Odoo
    _description = 'Asistente para Asociar CFDI de Pago Externo'

    # -------------------------------------------------------------------------
    # Definición de Campos del Wizard
    # -------------------------------------------------------------------------

    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Asiento Contable (Pago)',
        required=True,
        readonly=True,
        # Ajuste para priorizar el context key si se pasa explícitamente
        default=lambda self: self.env.context.get('default_move_id', self.env.context.get('active_id')),
        help="El asiento contable (tipo 'entry') del pago al que se asociará el CFDI de Complemento de Pago."
    )

    attachment_id = fields.Many2one(
        comodel_name='ir.attachment',
        string='Archivo XML del CFDI (REP)',
        required=True,
        domain="[('res_model', '=', 'account.move'), ('res_id', '=', move_id), ('name', '=ilike', '%.xml')]",
        help="Seleccione el archivo XML del Complemento de Pago (REP) (que ya debe estar adjuntado al asiento contable) que desea asociar."
    )

    # -------------------------------------------------------------------------
    # Métodos de Ayuda (Privados)
    # -------------------------------------------------------------------------

    def _get_xml_uuid(self, xml_content_bytes):
        # (Código sin cambios)
        try:
            root = ET.fromstring(xml_content_bytes)
            namespaces = {
                'cfdi': 'http://www.sat.gob.mx/cfd/4',
                'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'
            }
            complemento_node = root.find('.//cfdi:Complemento', namespaces)
            if complemento_node is None:
                complemento_node = root.find('.//Complemento') # Fallback
                if complemento_node is None:
                    _logger.warning(f"Node 'cfdi:Complemento' not found in XML for attachment ID {self.attachment_id.id}.")
                    pagos_node = root.find('.//{http://www.sat.gob.mx/Pagos20}Pagos')
                    if not pagos_node:
                         raise UserError(_("The XML file does not seem to be a valid CFDI with Payments (Complemento or Pagos node missing)."))
                    raise UserError(_("The XML file does not seem to be a valid CFDI, as it lacks the 'Complemento' node."))

            tfd_node = complemento_node.find('.//tfd:TimbreFiscalDigital', namespaces)
            if tfd_node is None:
                 tfd_node = complemento_node.find('.//TimbreFiscalDigital') # Fallback
                 if tfd_node is None:
                    _logger.warning(f"Node 'tfd:TimbreFiscalDigital' not found within 'Complemento' in XML for attachment ID {self.attachment_id.id}.")
                    raise UserError(_("The XML file does not contain the 'TimbreFiscalDigital' node within 'Complemento'. Cannot extract UUID."))

            uuid = tfd_node.get('UUID')
            if not uuid:
                _logger.warning(f"Node 'tfd:TimbreFiscalDigital' lacks 'UUID' attribute in XML for attachment ID {self.attachment_id.id}.")
                raise UserError(_("Attribute 'UUID' not found in the 'TimbreFiscalDigital' node."))

            clean_uuid = uuid.strip().upper()
            _logger.info(f"UUID extracted from attachment ID {self.attachment_id.id} for move ID {self.move_id.id}: {clean_uuid}")
            return clean_uuid

        except ET.ParseError as e:
            _logger.error(f"XML parse error for attachment ID {self.attachment_id.id}: {e}")
            raise UserError(_("The selected XML file is malformed or corrupt. Please check the file.\nTechnical detail: %s", e))
        except Exception as e:
            _logger.error(f"Unexpected error processing XML for attachment ID {self.attachment_id.id}: {e}", exc_info=True)
            raise UserError(_("An unexpected error occurred while processing the XML file: %s", e))

    def _check_duplicate_uuid(self, uuid_to_check, current_move_id):
        # (Código sin cambios)
        if not uuid_to_check:
            raise ValidationError(_("No UUID provided to check for duplicates."))

        domain = [
            ('l10n_mx_edi_cfdi_uuid', '=', uuid_to_check),
            ('id', '!=', current_move_id),
            ('state', '!=', 'cancel'),
        ]
        existing_move = self.env['account.move'].search(domain, limit=1)

        if existing_move:
            _logger.warning(f"Attempt to associate duplicate UUID '{uuid_to_check}' to move ID {current_move_id}. "
                            f"UUID already exists on move ID {existing_move.id} ('{existing_move.name}').")
            raise ValidationError(
                _("The UUID '%s' extracted from this XML is already associated with the journal entry '%s' (ID: %d). "
                  "You cannot associate the same CFDI with multiple entries.") %
                (uuid_to_check, existing_move.name or f"ID {existing_move.id}", existing_move.id)
            )
        _logger.info(f"Duplicate check passed for UUID '{uuid_to_check}' and move ID {current_move_id}.")

    def _find_reconciled_invoices(self, payment_move):
        """
        Finds customer invoices reconciled with the given payment move.
        Args:
            payment_move (account.move): The payment journal entry record.
        Returns:
            account.move: Recordset of related customer invoices.
        """
        # This wizard is transient, ensure_one() might not be needed but good practice
        # self.ensure_one()
        invoice_moves = self.env['account.move']

        # Iterate through lines of the payment move that are receivable/payable
        # and involved in reconciliation.
        for line in payment_move.line_ids.filtered(lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')):
            # Get all partial reconciliations involving this line
            partials = line.matched_debit_ids | line.matched_credit_ids

            # For each partial reconciliation, find the 'other' line's move
            for partial in partials:
                # Determine which line in the partial reconciliation is NOT the current payment line
                counterpart_line = partial.debit_move_id if partial.credit_move_id == line else partial.credit_move_id
                # Check if the counterpart line's move is an invoice and not the payment itself
                if counterpart_line.move_id != payment_move and counterpart_line.move_id.move_type == 'out_invoice':
                    invoice_moves |= counterpart_line.move_id

        # Return unique invoices found
        return invoice_moves

    # -------------------------------------------------------------------------
    # Wizard Main Action
    # -------------------------------------------------------------------------

    def action_associate_cfdi(self):
        """
        Main method executed when the user clicks the wizard's action button.
        Performs the CFDI (REP) association process for a payment journal entry.
        """
        self.ensure_one()
        move = self.move_id # This is the payment move
        attachment = self.attachment_id

        _logger.info(f"Starting manual CFDI Payment Complement association process for Move ID {move.id} ('{move.name}') "
                     f"with Attachment ID {attachment.id} ('{attachment.name}').")

        # --- Initial Validations ---
        if not move:
            raise UserError(_("Could not determine the active journal entry. Please close the wizard and try again."))
        if move.move_type != 'entry':
             _logger.warning(f"Associate CFDI wizard called on move ID {move.id} with incorrect type '{move.move_type}'. Expected 'entry'.")
             raise UserError(_("This wizard is only intended for associating Payment Complements with Payment Journal Entries (Type 'entry')."))

        if not attachment:
            raise UserError(_("You must select an XML file from the list to associate."))
        if not attachment.datas:
             _logger.error(f"Selected attachment ID {attachment.id} ('{attachment.name}') has no content (datas is empty).")
             raise UserError(_("The selected attachment file '%s' appears to be empty or corrupt.") % attachment.name)
        if not move.date:
             _logger.error(f"Move ID {move.id} does not have an Accounting Date set.")
             raise UserError(_("The associated journal entry (ID: %d) does not have an Accounting Date set. Cannot determine the datetime for the EDI document.") % move.id)


        # --- XML Processing ---
        try:
            xml_content_bytes = base64.b64decode(attachment.datas)
        except (base64.binascii.Error, TypeError, ValueError) as e:
            _logger.error(f"Base64 decoding error for attachment ID {attachment.id}: {e}")
            raise UserError(_("Could not read the content of the attached XML file '%s'. "
                              "Ensure the file is not corrupt and is a valid XML.") % attachment.name)

        extracted_uuid = self._get_xml_uuid(xml_content_bytes)
        self._check_duplicate_uuid(extracted_uuid, move.id)

        # --- Data Update (within a transaction) ---
        edi_doc = None # Variable to store the created edi document
        reconciled_invoices = self.env['account.move'] # Initialize empty recordset
        try:
            # 1. Update Journal Entry (account.move)
            move_vals_to_write = {
                'l10n_mx_edi_cfdi_uuid': extracted_uuid,
                'l10n_mx_edi_cfdi_state': 'sent',
                'l10n_mx_edi_cfdi_attachment_id': attachment.id,
                'l10n_mx_edi_cfdi_sat_state': 'valid', # Correct field name
            }
            move.write(move_vals_to_write)
            _logger.info(f"Move ID {move.id} updated with UUID {extracted_uuid}, state 'sent', CFDI SAT state 'valid', and attachment ID {attachment.id}.")

            # 2. Ensure Attachment (ir.attachment) is correctly linked
            if attachment.res_model != 'account.move' or attachment.res_id != move.id:
                attachment.write({
                    'res_model': 'account.move',
                    'res_id': move.id,
                })
                _logger.info(f"Attachment ID {attachment.id} explicitly re-linked to Move ID {move.id}.")

            # 3. Create l10n_mx_edi.document record
            edi_doc_domain = [('move_id', '=', move.id)]
            existing_edi_doc = self.env['l10n_mx_edi.document'].search(edi_doc_domain, limit=1)

            if not existing_edi_doc:
                edi_state = 'payment_sent'
                _logger.info(f"Using EDI document state: '{edi_state}' for payment complement.")
                edi_datetime = datetime.datetime.combine(move.date, datetime.time.min)
                _logger.info(f"Determined EDI document datetime: '{edi_datetime}' from move date '{move.date}'.")

                edi_doc_vals = {
                    'move_id': move.id,
                    'state': edi_state,
                    'sat_state': 'valid',
                    'attachment_id': attachment.id,
                    'datetime': edi_datetime,
                }
                # Create the document and store it
                edi_doc = self.env['l10n_mx_edi.document'].create(edi_doc_vals)
                _logger.info(f"Record l10n_mx_edi.document created (ID: {edi_doc.id}) for Move ID {move.id} with state '{edi_state}'.")
            else:
                edi_doc = existing_edi_doc # Use the existing one if found
                _logger.warning(f"A record l10n_mx_edi.document already existed for Move ID {move.id} "
                                f"(ID: {edi_doc.id}). A new one was not created, but association was verified.")

            # --- Find reconciled invoices ---
            if edi_doc: # Proceed only if we have an EDI document (new or existing)
                reconciled_invoices = self._find_reconciled_invoices(move)
                if reconciled_invoices:
                    _logger.info(f"Payment Move ID {move.id} (REP UUID: {extracted_uuid}) is reconciled with Invoices: {reconciled_invoices.ids}")
                    # --- Attempt to refresh reconciled invoices ---
                    # Try calling the method that computes payment widget info
                    _logger.info(f"Attempting to refresh payment info for invoices: {reconciled_invoices.ids}")
                    if hasattr(reconciled_invoices, '_compute_payments_widget_to_reconcile_info'):
                         reconciled_invoices._compute_payments_widget_to_reconcile_info()
                         _logger.info(f"Called '_compute_payments_widget_to_reconcile_info' on reconciled invoices.")
                    else:
                         _logger.warning(f"Method '_compute_payments_widget_to_reconcile_info' not found on account.move. Unable to refresh invoice payment widget.")
                else:
                    _logger.info(f"Payment Move ID {move.id} has no reconciled customer invoices found.")

            # --- Successful Completion ---
            # 4. Log a message in the journal entry's chatter
            success_message = _(
                "Original CFDI de Pago (REP) asociado manualmente desde el archivo adjunto.<br/>"
                "<b>Archivo XML:</b> %s<br/>"
                "<b>UUID (Folio Fiscal):</b> %s"
            ) % (attachment.name, extracted_uuid)
            move.message_post(body=success_message)
            _logger.info(f"Manual CFDI Payment Complement association completed successfully for Move ID {move.id}.")

        except (UserError, ValidationError) as e:
            raise e
        except Exception as e:
            _logger.exception(f"Unexpected error during database update for move ID {move.id} "
                              f"while associating CFDI Payment Complement from attachment ID {attachment.id}: {e}")
            raise UserError(_("An unexpected error occurred while trying to save changes to the database. "
                              "The operation has been cancelled.\nTechnical detail: %s") % e)

        # If everything was successful, close the wizard.
        return {'type': 'ir.actions.act_window_close'}

