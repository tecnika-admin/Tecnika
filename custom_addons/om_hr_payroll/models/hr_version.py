# -*- coding:utf-8 -*-

from odoo import api, fields, models


class HrContract(models.Model):
    """
    Employee contract based on the visa, work permits
    allows to configure different Salary structure
    """
    # _inherit = 'hr.contract'
    _inherit = 'hr.version'
    _description = 'Employee Contract'

    struct_id = fields.Many2one('hr.payroll.structure', string='Salary Structure')
    schedule_pay = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('semi-annually', 'Semi-annually'),
        ('annually', 'Annually'),
        ('weekly', 'Weekly'),
        ('bi-weekly', 'Bi-weekly'),
        ('bi-monthly', 'Bi-monthly'),
    ], string='Scheduled Pay', index=True, default='monthly',
    help="Defines the frequency of the wage payment.")

    def get_all_structures(self):
        """
        @return: the structures linked to the given contracts, ordered by
        hierarchy (parent=False first,then first level children and so on)
        and without duplicate
        """
        # structures = self.mapped('struct_id')
        structures = self.mapped('contract_template_id.struct_id')

        if not structures:
            return []
        # YTI TODO return browse records
        return list(set(structures._get_parent_structure().ids))

    def get_attribute(self, code, attribute):
        """Function for return code for Contract"""
        return self.env['hr.contract.advantage.template'].search(
                [('code', '=', code)],
                limit=1)[attribute]

    def set_attribute_value(self, code, active):
        """Function for set code for Contract"""
        for contract in self:
            if active:
                value = self.env['hr.contract.advantage.template'].search(
                    [('code', '=', code)], limit=1).default_value
                contract[code] = value
            else:
                contract[code] = 0.0
