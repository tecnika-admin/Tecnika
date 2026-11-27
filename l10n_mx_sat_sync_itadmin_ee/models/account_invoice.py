# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command, _
import json, xmltodict
import base64
DEFAULT_CFDI_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S'
from ...l10n_mx_sat_sync_itadmin_ee.models.special_dict import CaselessDictionary
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

def convert_to_special_dict(d):
    for k, v in d.items():
        if isinstance(v, dict):
            d.__setitem__(k, convert_to_special_dict(CaselessDictionary(v)))
        else:
            d.__setitem__(k, v)
    return d

class AccountInvoice(models.Model):
    _inherit = 'account.move'

    attachment_id = fields.Many2one("ir.attachment", 'Attachment Sync')
    hide_message = fields.Boolean(string='Hide Message', default=False, copy=False)
    l10n_mx_edi_cfdi_sat_state = fields.Selection(selection_add=[('skip', 'Skip')])

    @api.depends('l10n_mx_edi_cfdi_attachment_id')
    def _compute_cfdi_uuid(self):
        for inv in self:
          if inv.move_type == 'out_invoice':
            if not inv.l10n_mx_edi_cfdi_attachment_id:
                attachments = inv.attachment_ids
                results = []
                results += [rec for rec in attachments if rec.name.endswith('.xml')]
                if results:
                    domain = [('res_id', '=', inv.id),
                              ('res_model', '=', inv._name),
                              ('name', '=', results[0].name)]

                    attachment = inv.env['ir.attachment'].search(domain, limit=1)
                    if attachment and not inv.l10n_mx_edi_invoice_document_ids:

                         document_values = {
                               'move_id': inv.id,
                               'invoice_ids': [Command.set(inv.ids)],
                               'state': 'invoice_sent',
                               'sat_state': 'not_defined',
                               'message': None,
                               'attachment_id': attachment.id,
                               }
                         inv.env['l10n_mx_edi.document']._create_update_invoice_document_from_invoice(self, document_values)

          if inv.move_type == 'in_invoice':
            attachments = inv.attachment_ids
            results = []
            results += [rec for rec in attachments if rec.name.endswith('.xml')]
            if results:
               domain = [('res_id', '=', inv.id),
                         ('res_model', '=', inv._name),
                         ('name', '=', results[0].name)]
               attachment = inv.env['ir.attachment'].search(domain, limit=1)
               if attachment:
                  file_content = base64.b64decode(attachment.datas)
                  if b'xmlns:schemaLocation' in file_content:
                      file_content = file_content.replace(b'xmlns:schemaLocation', b'xsi:schemaLocation')
                  file_content = file_content.replace(b'cfdi:',b'')
                  file_content = file_content.replace(b'tfd:',b'')
                  try:
                      data = json.dumps(xmltodict.parse(file_content)) #,force_list=('Concepto','Traslado',)
                      data = json.loads(data)
                  except Exception as e:
                      data = {}
                      raise UserError(str(e))

                  data = CaselessDictionary(data)
                  data = convert_to_special_dict(data)

                  if data.get('Comprobante',{}).get('@TipoDeComprobante') != 'P':
                     invoice_date = data.get('Comprobante',{}).get('@Fecha')
                     Complemento = data.get('Comprobante',{}).get('Complemento',{})
                     uso_data = data.get('Comprobante',{}).get('Receptor',{})
                     timbrado_data = Complemento.get('TimbreFiscalDigital',{})

                     inv.write({'l10n_mx_edi_cfdi_uuid': timbrado_data.get('@UUID'),
                              'l10n_mx_edi_usage' : uso_data.get('@UsoCFDI') if uso_data.get('@UsoCFDI') != 'P01' else 'S01',
                             })


    def run_cfdi_uuid(self):
        for inv in self:
            if inv.move_type == 'out_invoice':
               inv._compute_cfdi_uuid()
               inv.hide_message = True
            elif inv.move_type == 'in_invoice':
               inv._compute_cfdi_uuid()
