# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class CostCorrectionWizard(models.TransientModel):
    _name = 'cost.correction.wizard'
    _description = 'Wizard for Correcting Invoice Line Costs'

    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice',
        required=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        'cost.correction.wizard.line',
        'wizard_id',
        string='Invoice Lines to Correct',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'account.move' and self.env.context.get('active_id'):
            invoice = self.env['account.move'].browse(self.env.context['active_id'])
            res['invoice_id'] = invoice.id
            eligible_lines = invoice.line_ids.filtered(
                lambda line: line.display_type == 'product' and \
                             line.product_id and \
                             line.product_id.type == 'consu' and \
                             line.product_id.is_storable
            )
            # Pre-populate wizard lines
            wizard_lines = []
            for line in eligible_lines:
                # Placeholder for original cost - needs logic later
                original_cost_display = 0.0 # TODO: Calculate or fetch original cost

                wizard_lines.append((0, 0, {
                    'invoice_line_id': line.id,
                    # 'original_cost_display': original_cost_display, # Add field later
                    'correct_unit_cost': 0.0, # Default to 0, user must input
                    'selected': False, # Default to not selected
                }))
            res['line_ids'] = wizard_lines
        return res

    def action_apply_correction(self):
        """Applies the cost corrections based on user input."""
        self.ensure_one()
        selected_lines = self.line_ids.filtered(lambda l: l.selected)

        if not selected_lines:
            raise UserError(_("Please select at least one line to correct and provide the correct unit cost."))

        if any(line.correct_unit_cost < 0 for line in selected_lines):
             raise ValidationError(_("Correct unit cost cannot be negative."))

        # Placeholder for the main correction logic
        # This is where we will iterate through selected_lines and call
        # the functions to create/adjust account.move.lines for
        # both the invoice and the stock valuation entries.
        for line in selected_lines:
            print(f"TODO: Apply correction for Invoice Line ID: {line.invoice_line_id.id}, "
                  f"Product: {line.product_id.display_name}, "
                  f"Quantity: {line.quantity}, "
                  f"New Unit Cost: {line.correct_unit_cost}")
            # 1. Get accounts (COGS, Transitory)
            # 2. Find related stock.move -> stock.valuation.layer -> valuation account.move
            # 3. Determine original cost scenario (incorrect vs zero)
            # 4. Create adjustment lines in invoice account.move
            # 5. Create adjustment lines in valuation account.move
            pass # Implement actual logic here

        return {'type': 'ir.actions.act_window_close'}


class CostCorrectionWizardLine(models.TransientModel):
    _name = 'cost.correction.wizard.line'
    _description = 'Line for Cost Correction Wizard'

    wizard_id = fields.Many2one('cost.correction.wizard', required=True, ondelete='cascade')
    invoice_line_id = fields.Many2one('account.move.line', string='Invoice Line', required=True, readonly=True)
    product_id = fields.Many2one(related='invoice_line_id.product_id', readonly=True)
    quantity = fields.Float(related='invoice_line_id.quantity', readonly=True)
    # original_cost_display = fields.Float(string='Original Unit Cost', readonly=True) # Add later
    correct_unit_cost = fields.Float(string='Correct Unit Cost', required=True, default=0.0, digits='Product Price')
    selected = fields.Boolean(string='Correct', default=False)