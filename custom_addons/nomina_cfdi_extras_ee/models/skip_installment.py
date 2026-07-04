# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date
from dateutil.relativedelta import relativedelta
from calendar import monthrange

class dev_skip_installment(models.Model):
    _name = 'dev.skip.installment'
    _inherit = 'mail.thread'
    _order = 'name desc'
    _description = 'dev_skip_installment'

    @api.model
    def _get_employee(self):
        employee_id = self.env['hr.employee'].search([('user_id','=',self.env.user.id)],limit=1)
        return employee_id

    @api.model
    def _get_default_user(self):
        return self.env.user

    name = fields.Char('Nombre', default='/')
    employee_id = fields.Many2one('hr.employee',string='Empleado',required=True, default=_get_employee)
    loan_id = fields.Many2one('employee.loan',string='Deducción',required=True)
    installment_id = fields.Many2one('installment.line',string='Entrega', required=True)
    date = fields.Date(string='Fecha')#, default=fields.date.today())
    user_id = fields.Many2one('res.users',string='Usuario', default=_get_default_user)
    notes = fields.Text('Razón', required=True)
#    manager_id = fields.Many2one('hr.employee',string='Gerente de departamento', required=True)
    skip_installment_url = fields.Char('URL', compute='get_url')
#    hr_manager_id = fields.Many2one('hr.employee',string='Gerente de RH')
    state = fields.Selection([('draft','Borrador'),
                              ('request','Enviar petición'),
                              #('approve','Aprobar'),
                              ('confirm','Confirmar'),
                              ('done','Hecho'),
                              ('reject','Rechazar'),
                              ('cancel','Cancelar'),], string='Estado', default='draft', tracking=True)
    company_id = fields.Many2one('res.company', 'Company', required=True, index=True, default=lambda self: self.env.company)

    @api.depends('installment_id')
    def get_url(self):
        for installment in self:
            base_url = self.env['ir.config_parameter'].get_param('web.base.url', default='http://localhost:8069')
            if base_url:
                base_url += '/web/login?db=%s&login=%s&key=%s#id=%s&model=%s' % (
                self._cr.dbname, '', '', installment.id, 'dev.skip.installment')
                installment.skip_installment_url = base_url

    @api.constrains('installment_id')
    def _Check_skip_installment(self):
        request_ids = False
        if self.employee_id and self.installment_id:
            request_id = self.search([('employee_id','=',self.employee_id.id),
                                    ('installment_id','=',self.installment_id.id),
                                    ('state','in',['draft','approve','confirm','done']),('id','!=',self.id)])
        request = len(request_id)
        if request > 0:
            raise ValidationError("La línea %s salto de pago está en estado %s" % (self.installment_id.name,request_id.state))
   
    def action_send_request(self):
        self.state = 'confirm'
        
    def approve_skip_installment(self):
        self.state = 'approve'

   
    def dep_reject_skip_installment(self):
        self.state = 'reject'

   
    def hr_reject_skip_installment(self):
        self.state = 'reject'

   
    def confirm_skip_installment(self):
        self.state = 'confirm'
    
    def done_skip_installment(self):
        date = self.loan_id.start_date
        #date = datetime.strptime(date, '%Y-%m-%d')
        i = len(self.loan_id.installment_lines)
        loan = self.installment_id.loan_id
        periodo_de_pago = loan.loan_type_id.periodo_de_pago or ''
        if periodo_de_pago=='Semanal':
            date = date+relativedelta(weeks=i)
        elif periodo_de_pago=='Quincenal':
            date = date+relativedelta(days=i*15)
            month_last_day = monthrange(date.year,date.month)[1]
            items = [date+relativedelta(day=month_last_day), date+relativedelta(day=15)]
            previous_month_date = date+relativedelta(months=-1)
            previous_month_last_day = monthrange(previous_month_date.year,previous_month_date.month)[1]
            items.append(previous_month_date+relativedelta(day=previous_month_last_day),)
            if date.day>15:
                items.append(date+relativedelta(months=1,day=15))
            date = loan.nearest_date(items,date)
        else:
            date = date+relativedelta(months=1)

        vals={
            'name': str(self.installment_id.name) + ' - COPIA',
            'employee_id': self.employee_id and self.employee_id.id or False,
            'date': date,
            'amount': self.installment_id.amount,
            'interest': 0.0,
            'installment_amt': self.installment_id.installment_amt,
            'ins_interest': 0.0,
            'loan_id': loan.id,
            'tipo_deduccion': self.installment_id.tipo_deduccion,
            }
        new_inst = self.env['installment.line'].create(vals)
        if new_inst:
            self.installment_id.is_skip = True
        self.state = 'done'

    def cancel_skip_installment(self):
        for skp_installment in self:
            if skp_installment.state == 'done':
                line_name = str(self.installment_id.name) + ' - COPIA'
                line = self.env['installment.line'].search([('name','=',line_name)],limit=1)
                if line:
                    if not line.is_paid:
                       line.unlink()
                       self.installment_id.is_skip = False
                       self.state = 'cancel'
                    else:
                       raise ValidationError(_('No se puede cancelar un salto ya pagado'))
            else:
                self.state = 'cancel'

    def set_to_draft(self):
        self.state = 'draft'
    
    @api.model
    def init(self):
        company_id = self.env['res.company'].search([])
        for company in company_id:
            skip_installment_sequence = self.env['ir.sequence'].search([('code', '=', 'dev.skip.installment'), ('company_id', '=', company.id)])
            if not skip_installment_sequence:
                skip_installment_sequence.create({
                        'name': 'Secuencia de salto de prestamo',
                        'code': 'dev.skip.installment',
                        'prefix': 'SAL-PRES/',
                        'padding': 4,
                        'company_id': company.id,
                    })
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
           if vals.get('name', '/') == '/':
               if 'company_id' in vals:
                   vals['name'] = self.env['ir.sequence'].with_company(vals['company_id']).next_by_code('dev.skip.installment') or '/'
               else:
                   vals['name'] = self.env['ir.sequence'].next_by_code('dev.skip.installment') or '/'
        return super(dev_skip_installment, self).create(vals_list)

    def copy(self, default=None):
        if default is None:
            default = {}
        default['name'] = '/'
        return super(dev_skip_installment, self).copy(default=default)

   
    def unlink(self):
        for skp_installment in self:
            if skp_installment.state != 'draft':
                raise ValidationError(_('Solo se pueden eliminar los saltos en el estado borrador'))
        return super(dev_skip_installment,self).unlink()
