# -*- coding: utf-8 -*-

from odoo import fields, models


class HrPayslipWorkedDays(models.Model):
    _name = 'hr.payslip.worked_days'
    _description = 'Payslip Worked Days'
    _order = 'payslip_id, sequence'

    name = fields.Char(string='Description', required=True)
    payslip_id = fields.Many2one('hr.payslip', string='Pay Slip', required=True, ondelete='cascade', index=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', related='payslip_id.employee_id', store=True)
    sequence = fields.Integer(required=True, index=True, default=10)
    code = fields.Char(required=True, help="The code that can be used in the salary rules")
    number_of_days = fields.Float(string='Number of Days', digits=(0,4))
    number_of_hours = fields.Float(string='Number of Hours')
    contract_id = fields.Many2one(related='payslip_id.contract_id', string='Contract',
        help="The contract for which applied this input")
