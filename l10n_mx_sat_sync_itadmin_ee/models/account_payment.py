# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command, _
DEFAULT_CFDI_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S'

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    attachment_id = fields.Many2one("ir.attachment", 'Attachment Sync')

    @api.depends('l10n_mx_edi_cfdi_attachment_id')
    def _compute_cfdi_uuid(self):
        for payment in self:
          if payment.payment_type == 'inbound':
            if not payment.l10n_mx_edi_cfdi_attachment_id:
                attachments = payment.attachment_ids
                results = []
                results += [rec for rec in attachments if rec.name.endswith('.xml')]
                if results:
                    domain = [('res_id', '=', payment.id),
                              ('res_model', '=', payment._name),
                              ('name', '=', results[0].name)]

                    attachment = payment.env['ir.attachment'].search(domain, limit=1)
                    if attachment and not payment.move_id.l10n_mx_edi_invoice_document_ids:

                         document_values = {
                               'move_id': payment.id,
                               'invoice_ids': [Command.set(payment.ids)],
                               'state': 'payment_sent',
                               'sat_state': 'not_defined',
                               'message': None,
                               'attachment_id': attachment.id,
                               }
                         self.env['l10n_mx_edi.document']._create_update_invoice_document_from_invoice(payment.move_id, document_values)

