# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from odoo.exceptions import UserError
from collections import defaultdict
from datetime import datetime
from dateutil.relativedelta import relativedelta

class CrearFaltasFromRetardos(models.TransientModel):
    _name = 'crear.faltas.from.retardos'
    _description = 'CrearFaltasFromRetardos'
    
    start_date = fields.Date("Fecha inicio")
    end_date = fields.Date("Fecha fin")
    
    
    def action_crear_faltas_from_ratardos(self):
        start_date = self.start_date
        end_date = self.end_date
        records = self.env['retardo.nomina'].search([('fecha','>=',start_date), ('fecha', '<=', end_date),('state','=','done')])
        record_by_employee = defaultdict(list)
        for retardo in records:
            record_by_employee[retardo.employee_id.id].append(retardo.id)
        retardos_x_falta = int(self.env['ir.config_parameter'].sudo().get_param('nomina_cfdi_extras_ee.numoer_de_retardos_x_falta', 0))
        holidays_obj = self.env['hr.leave']
        
        en_date = end_date #datetime.strptime(end_date,DEFAULT_SERVER_DATE_FORMAT)

        leave_type = self.env.company.leave_type_fr
        if not leave_type:
           raise UserError(_('Falta configurar el tipo de falta en Configuracion - Ajustes'))

        for emp_id,retardos in record_by_employee.items():
            record_count = len(retardos)
            if record_count >= retardos_x_falta and retardos_x_falta:
                sub_days = int(record_count/retardos_x_falta)
                fecha_inicio = en_date - relativedelta(days=sub_days) + relativedelta(days=1)

                vals = {
                   'holiday_status_id' : leave_type and leave_type.id,
                   'employee_id' : emp_id,
                   #'name' : 'Faltas_Retardo',
                   'request_date_from' : fecha_inicio.strftime(DEFAULT_SERVER_DATE_FORMAT),
                   'request_date_to' : en_date,
                   'state': 'confirm',}

                holiday = holidays_obj.new(vals)
                holiday._compute_from_employee_id()
                holiday._compute_duration()
                vals.update(holiday._convert_to_write({name: holiday[name] for name in holiday._cache}))
                vals.update({'holiday_status_id' : leave_type and leave_type.id,})
                falta = self.env['hr.leave'].create(vals)
                falta.action_validate()

        return
