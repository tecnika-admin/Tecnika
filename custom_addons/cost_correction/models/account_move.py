# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_open_cost_correction_wizard(self):
        """Opens the cost correction wizard for the selected invoice."""
        self.ensure_one()

        # Basic validation before opening wizard
        if self.state != 'posted':
            raise UserError(_("Cost correction can only be applied to posted invoices."))
        if self.move_type != 'out_invoice':
            raise UserError(_("Cost correction is only applicable to customer invoices."))
        if not self.l10n_mx_edi_cfdi_uuid:
            # You might want to relax this if some invoices are posted but not signed
            # depending on exact workflow.
             raise UserError(_("Cost correction requires the invoice to be electronically signed (CFDI)."))

        # Find eligible lines to potentially correct
        eligible_lines = self.line_ids.filtered(
            lambda line: line.display_type == 'product' and \
                         line.product_id and \
                         line.product_id.type == 'consu' and \
                         line.product_id.is_storable # As per user confirmation
        )

        if not eligible_lines:
            raise UserError(_("This invoice has no lines with storable products (type='consu', is_storable=True) eligible for cost correction."))

        # Return action to open the wizard
        action = self.env['ir.actions.actions']._for_xml_id('cost_correction.action_cost_correction_wizard')
        action['context'] = {
            'default_invoice_id': self.id,
        }
        # Pass eligible line IDs to potentially pre-fill the wizard or filter later
        action['context']['eligible_invoice_line_ids'] = eligible_lines.ids

        return action