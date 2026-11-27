# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ImportInvoiceProcessMessage(models.TransientModel):
    _name = 'import.invoice.process.message'
    _description = 'ImportInvoiceProcessMessage'

    name = fields.Char("Name")
    existed_attachment = fields.Html()
    not_imported_attachment = fields.Html()
    imported_attachment = fields.Html()

    def show_created_invoices(self):
        create_invoice_ids = self._context.get('create_invoice_ids', [])
        action = self.env.ref('account.action_move_in_invoice_type').sudo()
        result = action.read()[0]
        result['context'] = {'type': 'in_invoice'}
        result['domain'] = "[('id', 'in', " + str(create_invoice_ids) + ")]"
        return result


