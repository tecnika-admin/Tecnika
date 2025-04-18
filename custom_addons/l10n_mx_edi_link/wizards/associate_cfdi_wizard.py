# -*- coding: utf-8 -*-

# Importaciones estándar de Python
import base64
import logging
import xml.etree.ElementTree as ET # Para parsear XML
import datetime # Import needed for time combination

# Importaciones de Odoo
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError # Para errores y validaciones

# Configuración del logger para registrar información y errores
_logger = logging.getLogger(__name__)

class AssociateCfdiWizard(models.TransientModel):
    """
    Asistente (Wizard) para asociar manualmente un archivo XML de Complemento de Pago (REP)
    externo a un registro de asiento contable de pago (tipo 'entry') existente.
    Permite al usuario seleccionar un archivo XML adjunto al asiento,
    extrae y valida el UUID (Folio Fiscal), actualiza el asiento contable
    y crea el registro correspondiente en l10n_mx_edi.document.
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
        default=lambda self: self.env.context.get('active_id'),
        # Help text updated to reflect focus on payments
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
        """
        Parses the XML content (bytes) and extracts the UUID from the TimbreFiscalDigital node.
        Handles common CFDI 4.0 namespaces.
        Args:
            xml_content_bytes (bytes): Binary content of the XML file.
        Returns:
            str: The found UUID (uppercase, stripped).
        Raises:
            UserError: If XML is malformed, expected nodes (Complemento, TimbreFiscalDigital)
                       or the UUID attribute are missing.
        """
        try:
            root = ET.fromstring(xml_content_bytes)
            namespaces = {
                'cfdi': 'http://www.sat.gob.mx/cfd/4',
                'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'
            }
            # Find Complemento node (still needed for REP)
            complemento_node = root.find('.//cfdi:Complemento', namespaces)
            if complemento_node is None:
                complemento_node = root.find('.//Complemento') # Fallback
                if complemento_node is None:
                    _logger.warning(f"Node 'cfdi:Complemento' not found in XML for attachment ID {self.attachment_id.id}.")
                    # Check if it's a REP by looking for pagos:Pagos node directly? More robust check might be needed.
                    # For now, assume Complemento is needed structure-wise even if empty for some CFDI types.
                    # Let's check specifically for Pagos node if Complemento fails.
                    pagos_node = root.find('.//{http://www.sat.gob.mx/Pagos20}Pagos') # Check for Pagos 2.0 namespace explicitly
                    if not pagos_node:
                         raise UserError(_("The XML file does not seem to be a valid CFDI with Payments (Complemento or Pagos node missing)."))
                    # If Pagos node exists, maybe TFD is directly under root? Unlikely standard. Let's stick to TFD within Complemento.
                    # Re-raise the original error if Complemento is truly missing.
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
        """
        Checks if the extracted UUID is already associated with another account move in Odoo.
        Args:
            uuid_to_check (str): The UUID to check.
            current_move_id (int): The ID of the current move (to exclude it from search).
        Raises:
            ValidationError: If the UUID already exists in another (non-cancelled) move.
        """
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

    # -------------------------------------------------------------------------
    # Wizard Main Action
    # -------------------------------------------------------------------------

    def action_associate_cfdi(self):
        """
        Main method executed when the user clicks the wizard's action button.
        Performs the CFDI (REP) association process for a payment journal entry.
        """
        self.ensure_one()
        move = self.move_id
        attachment = self.attachment_id

        # Log updated for payment focus
        _logger.info(f"Starting manual CFDI Payment Complement association process for Move ID {move.id} ('{move.name}') "
                     f"with Attachment ID {attachment.id} ('{attachment.name}').")

        # --- Initial Validations ---
        if not move:
            raise UserError(_("Could not determine the active journal entry. Please close the wizard and try again."))
        # Added check for move_type consistency (although button should prevent wrong types)
        if move.move_type != 'entry':
             _logger.warning(f"Associate CFDI wizard called on move ID {move.id} with incorrect type '{move.move_type}'. Expected 'entry'.")
             raise UserError(_("This wizard is only intended for associating Payment Complements with Payment Journal Entries (Type 'entry')."))

        if not attachment:
            raise UserError(_("You must select an XML file from the list to associate."))
        if not attachment.datas:
             _logger.error(f"Selected attachment ID {attachment.id} ('{attachment.name}') has no content (datas is empty).")
             raise UserError(_("The selected attachment file '%s' appears to be empty or corrupt.") % attachment.name)
        # Ensure move date is set (should be true for posted moves)
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
        try:
            # 1. Update Journal Entry (account.move)
            move_vals_to_write = {
                'l10n_mx_edi_cfdi_uuid': extracted_uuid,
                'l10n_mx_edi_cfdi_state': 'sent',
                'l10n_mx_edi_cfdi_attachment_id': attachment.id,
                # Add SAT state to the move itself
                'l10n_mx_edi_sat_state': 'valid',
            }
            move.write(move_vals_to_write)
            _logger.info(f"Move ID {move.id} updated with UUID {extracted_uuid}, state 'sent', SAT state 'valid', and attachment ID {attachment.id}.")

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
                # --- Set correct state for l10n_mx_edi.document (Payment) ---
                # Logic simplified: always use 'payment_sent' as we only handle payments now
                edi_state = 'payment_sent'
                _logger.info(f"Using EDI document state: '{edi_state}' for payment complement.")

                # --- Determine datetime for l10n_mx_edi.document ---
                # Combine the move's date with the minimum time (00:00:00)
                edi_datetime = datetime.datetime.combine(move.date, datetime.time.min)
                _logger.info(f"Determined EDI document datetime: '{edi_datetime}' from move date '{move.date}'.")


                edi_doc_vals = {
                    'move_id': move.id,
                    # Use the fixed state for payments
                    'state': edi_state,
                    'sat_state': 'valid', # As agreed
                    'attachment_id': attachment.id,
                    # Use the determined datetime based on move date
                    'datetime': edi_datetime,
                    # Check if other mandatory fields exist in l10n_mx_edi.document in v18
                }
                self.env['l10n_mx_edi.document'].create(edi_doc_vals)
                _logger.info(f"Record l10n_mx_edi.document created for Move ID {move.id} with state '{edi_state}'.")
            else:
                _logger.warning(f"A record l10n_mx_edi.document already existed for Move ID {move.id} "
                                f"(ID: {existing_edi_doc.id}). A new one was not created, but association was verified.")

            # --- Successful Completion ---

            # 4. Log a message in the journal entry's chatter
            success_message = _(
                # Message updated for Payment Complement context
                "Original CFDI de Pago (REP) asociado manualmente desde el archivo adjunto.<br/>"
                "<b>Archivo XML:</b> %s<br/>"
                "<b>UUID (Folio Fiscal):</b> %s"
            ) % (attachment.name, extracted_uuid)
            move.message_post(body=success_message)
            _logger.info(f"Manual CFDI Payment Complement association completed successfully for Move ID {move.id}.")

        except (UserError, ValidationError) as e:
            raise e
        except Exception as e:
            # Log the exception with traceback for detailed debugging
            _logger.exception(f"Unexpected error during database update for move ID {move.id} "
                              f"while associating CFDI Payment Complement from attachment ID {attachment.id}: {e}")
            # Provide a user-friendly error message, including the technical detail if possible
            raise UserError(_("An unexpected error occurred while trying to save changes to the database. "
                              "The operation has been cancelled.\nTechnical detail: %s") % e)

        # If everything was successful, close the wizard.
        return {'type': 'ir.actions.act_window_close'}

