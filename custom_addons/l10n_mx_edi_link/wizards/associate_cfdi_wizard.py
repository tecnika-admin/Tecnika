# -*- coding: utf-8 -*-

# Importaciones estándar de Python
import base64
import logging
import xml.etree.ElementTree as ET # Para parsear XML

# Importaciones de Odoo
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError # Para errores y validaciones

# Configuración del logger para registrar información y errores
_logger = logging.getLogger(__name__)

class AssociateCfdiWizard(models.TransientModel):
    """
    Asistente (Wizard) para asociar manualmente un archivo CFDI XML externo
    a un registro de asiento contable (account.move) existente.
    Permite al usuario seleccionar un archivo XML adjunto al asiento,
    extrae y valida el UUID (Folio Fiscal), actualiza el asiento contable
    y crea el registro correspondiente en l10n_mx_edi.document.
    """
    # Nombre técnico del modelo del wizard (debe coincidir con security/ir.model.access.csv)
    _name = 'custom_l10n_mx_edi_link.associate_cfdi_wizard'
    # Descripción del modelo que aparece en la interfaz de Odoo
    _description = 'Asistente para Asociar CFDI XML Externo'

    # -------------------------------------------------------------------------
    # Definición de Campos del Wizard
    # -------------------------------------------------------------------------

    # Campo para almacenar el ID del asiento contable activo (obtenido del contexto)
    # Se hace readonly y default para que el usuario no lo cambie.
    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Asiento Contable',
        required=True,
        readonly=True,
        # Obtiene el ID del registro activo desde el contexto al abrir el wizard
        default=lambda self: self.env.context.get('active_id'),
        help="El asiento contable (factura, complemento de pago) al que se asociará el CFDI."
    )

    # Campo Many2one para que el usuario seleccione el archivo XML adjunto.
    # El dominio se filtra dinámicamente para mostrar solo los XML relevantes.
    attachment_id = fields.Many2one(
        comodel_name='ir.attachment',
        string='Archivo XML del CFDI',
        required=True,
        # Dominio para filtrar adjuntos:
        # 1. Deben pertenecer al modelo 'account.move'.
        # 2. Deben estar asociados al 'move_id' actual del wizard.
        # 3. El nombre del archivo debe terminar en '.xml' (insensible a mayúsculas/minúsculas).
        domain="[('res_model', '=', 'account.move'), ('res_id', '=', move_id), ('name', '=ilike', '%.xml')]",
        help="Seleccione el archivo XML del CFDI (que ya debe estar adjuntado al asiento contable) que desea asociar."
    )

    # -------------------------------------------------------------------------
    # Métodos de Ayuda (Privados)
    # -------------------------------------------------------------------------

    def _get_xml_uuid(self, xml_content_bytes):
        """
        Parsea el contenido XML (en bytes) y extrae el UUID del nodo TimbreFiscalDigital.
        Maneja los namespaces comunes de CFDI 4.0.
        Args:
            xml_content_bytes (bytes): Contenido binario del archivo XML.
        Returns:
            str: El UUID encontrado (en mayúsculas y sin espacios extra).
        Raises:
            UserError: Si el XML está mal formado, no contiene los nodos esperados
                       (Complemento, TimbreFiscalDigital) o el atributo UUID.
        """
        try:
            # Parsea el XML desde los bytes
            root = ET.fromstring(xml_content_bytes)

            # Define los namespaces esperados. Es crucial para encontrar los nodos.
            # Pueden variar ligeramente si el CFDI usa otras versiones o addendas.
            namespaces = {
                'cfdi': 'http://www.sat.gob.mx/cfd/4',        # Namespace principal CFDI 4.0
                'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital' # Namespace del Timbre Fiscal Digital
            }

            # Busca el nodo Complemento usando el namespace cfdi
            complemento_node = root.find('.//cfdi:Complemento', namespaces)
            if complemento_node is None:
                # Intenta buscar sin namespace como fallback (menos probable para CFDI estándar)
                complemento_node = root.find('.//Complemento')
                if complemento_node is None:
                    _logger.warning(f"No se encontró el nodo 'cfdi:Complemento' en el XML del adjunto ID {self.attachment_id.id}.")
                    raise UserError(_("El archivo XML no parece ser un CFDI válido, ya que no contiene el nodo 'Complemento'."))

            # Busca el nodo TimbreFiscalDigital dentro del Complemento, usando el namespace tfd
            tfd_node = complemento_node.find('.//tfd:TimbreFiscalDigital', namespaces)
            if tfd_node is None:
                 # Intenta buscar sin namespace como fallback
                 tfd_node = complemento_node.find('.//TimbreFiscalDigital')
                 if tfd_node is None:
                    _logger.warning(f"No se encontró el nodo 'tfd:TimbreFiscalDigital' dentro de 'Complemento' en el XML del adjunto ID {self.attachment_id.id}.")
                    raise UserError(_("El archivo XML no contiene el nodo 'TimbreFiscalDigital' dentro del 'Complemento'. No se puede extraer el UUID."))

            # Extrae el valor del atributo UUID del nodo TimbreFiscalDigital
            uuid = tfd_node.get('UUID')
            if not uuid:
                _logger.warning(f"El nodo 'tfd:TimbreFiscalDigital' no tiene el atributo 'UUID' en el XML del adjunto ID {self.attachment_id.id}.")
                raise UserError(_("No se encontró el atributo 'UUID' en el nodo 'TimbreFiscalDigital'."))

            # Limpia y retorna el UUID
            clean_uuid = uuid.strip().upper()
            _logger.info(f"UUID extraído del adjunto ID {self.attachment_id.id} para el asiento ID {self.move_id.id}: {clean_uuid}")
            return clean_uuid

        except ET.ParseError as e:
            _logger.error(f"Error de parseo XML para adjunto ID {self.attachment_id.id}: {e}")
            raise UserError(_("El archivo XML seleccionado está mal formado o corrupto. Verifique el archivo.\nDetalle técnico: %s", e))
        except Exception as e:
            _logger.error(f"Error inesperado procesando XML del adjunto ID {self.attachment_id.id}: {e}", exc_info=True)
            raise UserError(_("Ocurrió un error inesperado al procesar el archivo XML: %s", e))

    def _check_duplicate_uuid(self, uuid_to_check, current_move_id):
        """
        Verifica si el UUID extraído ya está asociado a otro asiento contable en Odoo.
        Args:
            uuid_to_check (str): El UUID a verificar.
            current_move_id (int): El ID del asiento contable actual (para excluirlo de la búsqueda).
        Raises:
            ValidationError: Si el UUID ya existe en otro asiento contable (no cancelado).
        """
        if not uuid_to_check:
            # Esta validación no debería ocurrir si _get_xml_uuid funcionó, pero es una salvaguarda.
            raise ValidationError(_("No se proporcionó un UUID para verificar duplicados."))

        # Define el dominio de búsqueda
        domain = [
            ('l10n_mx_edi_cfdi_uuid', '=', uuid_to_check), # Busca asientos con el mismo UUID
            ('id', '!=', current_move_id),                # Excluye el asiento actual
            ('state', '!=', 'cancel'),                    # Excluye asientos cancelados
        ]
        # Realiza la búsqueda
        existing_move = self.env['account.move'].search(domain, limit=1)

        # Si se encuentra un asiento existente con ese UUID
        if existing_move:
            _logger.warning(f"Intento de asociar UUID duplicado '{uuid_to_check}' al asiento ID {current_move_id}. "
                            f"UUID ya existe en el asiento ID {existing_move.id} ('{existing_move.name}').")
            # Lanza un error de validación claro para el usuario
            raise ValidationError(
                _("El UUID '%s' extraído de este XML ya está asociado al asiento contable '%s' (ID: %d). "
                  "No puede asociar el mismo CFDI a múltiples asientos.") %
                (uuid_to_check, existing_move.name or f"ID {existing_move.id}", existing_move.id)
            )
        _logger.info(f"Validación de duplicado superada para UUID '{uuid_to_check}' y asiento ID {current_move_id}.")


    # -------------------------------------------------------------------------
    # Acción Principal del Wizard
    # -------------------------------------------------------------------------

    def action_associate_cfdi(self):
        """
        Método principal ejecutado cuando el usuario hace clic en el botón de acción del wizard.
        Realiza todo el proceso de asociación del CFDI.
        """
        # Asegura que se esté ejecutando sobre un único registro del wizard
        self.ensure_one()
        move = self.move_id
        attachment = self.attachment_id

        _logger.info(f"Iniciando proceso de asociación manual de CFDI para Asiento ID {move.id} ('{move.name}') "
                     f"con Adjunto ID {attachment.id} ('{attachment.name}').")

        # --- Validaciones Iniciales ---
        if not move:
            # Esto no debería ocurrir si el default y readonly funcionan bien
            raise UserError(_("No se pudo determinar el asiento contable activo. Cierre el asistente y vuelva a intentarlo."))
        if not attachment:
            # El campo es requerido, pero verificamos por si acaso.
            raise UserError(_("Debe seleccionar un archivo XML de la lista para poder asociarlo."))
        if not attachment.datas:
             _logger.error(f"El adjunto seleccionado ID {attachment.id} ('{attachment.name}') no tiene contenido (datas está vacío).")
             raise UserError(_("El archivo adjunto seleccionado '%s' parece estar vacío o corrupto.") % attachment.name)

        # --- Procesamiento del XML ---
        try:
            # Decodifica el contenido del archivo de Base64 a bytes
            xml_content_bytes = base64.b64decode(attachment.datas)
        except (base64.binascii.Error, TypeError, ValueError) as e:
            _logger.error(f"Error al decodificar Base64 del adjunto ID {attachment.id}: {e}")
            raise UserError(_("No se pudo leer el contenido del archivo XML adjunto '%s'. "
                              "Asegúrese de que el archivo no esté corrupto y sea un XML válido.") % attachment.name)

        # Extrae el UUID del XML (maneja errores internos)
        extracted_uuid = self._get_xml_uuid(xml_content_bytes)

        # Verifica si el UUID ya existe en otro asiento (maneja errores internos)
        self._check_duplicate_uuid(extracted_uuid, move.id)

        # --- Actualización de Datos (en una transacción) ---
        try:
            # Usar un savepoint permite revertir solo esta parte si algo falla
            # aunque Odoo generalmente maneja la transacción completa.
            # with self.env.cr.savepoint(): # Opcional, Odoo maneja la transacción principal

            # 1. Actualizar el Asiento Contable (account.move)
            move_vals_to_write = {
                'l10n_mx_edi_cfdi_uuid': extracted_uuid,       # Establece el UUID extraído
                'l10n_mx_edi_cfdi_state': 'sent',            # Marca el estado EDI como 'Enviado'
                'l10n_mx_edi_cfdi_attachment_id': attachment.id, # Vincula el adjunto específico
            }
            move.write(move_vals_to_write)
            _logger.info(f"Asiento ID {move.id} actualizado con UUID {extracted_uuid}, estado 'sent' y adjunto ID {attachment.id}.")

            # 2. Asegurar que el Adjunto (ir.attachment) esté correctamente vinculado
            #    Esto es importante si el archivo se subió genéricamente al chatter antes.
            if attachment.res_model != 'account.move' or attachment.res_id != move.id:
                attachment.write({
                    'res_model': 'account.move',
                    'res_id': move.id,
                })
                _logger.info(f"Adjunto ID {attachment.id} re-vinculado explícitamente al Asiento ID {move.id}.")

            # 3. Crear el registro en l10n_mx_edi.document
            #    Este modelo rastrea los documentos EDI generados o asociados.
            #    Verificamos si ya existe uno para evitar duplicados accidentales aquí también.
            edi_doc_domain = [
                ('move_id', '=', move.id),
                # Podríamos buscar por UUID también, pero buscar por move/attachment es más directo
                # ('l10n_mx_edi_cfdi_uuid', '=', extracted_uuid)
            ]
            existing_edi_doc = self.env['l10n_mx_edi.document'].search(edi_doc_domain, limit=1)

            if not existing_edi_doc:
                edi_doc_vals = {
                    'move_id': move.id,              # Vínculo al asiento contable
                    'state': 'sent',                 # Estado del documento EDI ('Enviado')
                    'sat_state': 'valid',            # Estado ante el SAT ('Válido', según acuerdo)
                    'attachment_id': attachment.id,  # Vínculo al archivo XML
                    # 'message': 'CFDI asociado manualmente por el usuario.', # Mensaje opcional
                    # Nota: Revisa si hay otros campos obligatorios en l10n_mx_edi.document en v18
                }
                self.env['l10n_mx_edi.document'].create(edi_doc_vals)
                _logger.info(f"Registro l10n_mx_edi.document creado para Asiento ID {move.id}.")
            else:
                # Si ya existe, podríamos actualizarlo o simplemente registrar que ya estaba.
                _logger.warning(f"Ya existía un registro l10n_mx_edi.document para Asiento ID {move.id} "
                                f"(ID: {existing_edi_doc.id}). No se creó uno nuevo, pero se verificó la asociación.")
                # Opcional: Actualizar el existente si es necesario
                # existing_edi_doc.write({'state': 'sent', 'sat_state': 'valid', 'attachment_id': attachment.id})

            # --- Finalización Exitosa ---

            # 4. Registrar un mensaje en el chatter del asiento contable
            success_message = _(
                "Se asoció manualmente el CFDI Original desde el archivo adjunto.<br/>"
                "<b>Archivo XML:</b> %s<br/>"
                "<b>UUID (Folio Fiscal):</b> %s"
            ) % (attachment.name, extracted_uuid)
            move.message_post(body=success_message)
            _logger.info(f"Asociación manual de CFDI completada exitosamente para Asiento ID {move.id}.")

        except (UserError, ValidationError) as e:
            # Errores de usuario o validación ya están preparados para mostrarse.
            # El logger ya registró el detalle en los métodos _get_xml_uuid o _check_duplicate_uuid.
            # Simplemente relanzamos el error para que Odoo lo muestre.
            raise e
        except Exception as e:
            # Captura cualquier otro error inesperado durante las escrituras en BD.
            _logger.exception(f"Error inesperado durante la actualización de la base de datos para el asiento ID {move.id} "
                              f"al asociar el CFDI del adjunto ID {attachment.id}: {e}")
            # Odoo maneja el rollback de la transacción automáticamente en caso de excepción.
            raise UserError(_("Ocurrió un error inesperado al intentar guardar los cambios en la base de datos. "
                              "La operación ha sido cancelada.\nDetalle técnico: %s") % e)

        # Si todo fue exitoso, cierra el wizard.
        return {'type': 'ir.actions.act_window_close'}

