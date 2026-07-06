# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from datetime import datetime, timedelta
from collections import defaultdict
from odoo.osv import expression
import logging
_logger = logging.getLogger(__name__)

class Contract(models.Model):
    _inherit = "hr.version"
    
    riesgo_puesto = fields.Selection(
        selection=[('1', 'Clase I'), 
                   ('2', 'Clase II'), 
                   ('3', 'Clase III'),
                   ('4', 'Clase IV'), 
                   ('5', 'Clase V'), 
                   ('99', 'No aplica'),],
        string='Riesgo del puesto',
    )	
    sueldo_diario = fields.Float('Sueldo diario')
    sueldo_hora = fields.Float('Sueldo por hora')
    sueldo_diario_integrado = fields.Float('Sueldo diario integrado')
    sueldo_base_cotizacion = fields.Float('Sueldo base cotización (IMSS)')
    tablas_cfdi_id = fields.Many2one('tablas.cfdi','Tabla CFDI')
    company_cfdi = fields.Boolean(related="company_id.company_cfdi",store=True)
    wage_type = fields.Selection([
        ('monthly', 'Sueldo fijo'),
        ('hourly', 'Sueldo por hora')
    ], default='monthly')
#    vacaciones_adelantadas = fields.Integer('Dias vacaciones adelantadas', default=0)
#    tabla_vacaciones = fields.One2many('tablas.vacaciones.line', 'form_id')
#    historial_salario_ids = fields.One2many('contract.historial.salario','contract_id', 'Historial Salario')

    #FUNCTION TO CREATE INCIDENTIA DAR ALTA
    def action_dar_alta(self):
        for contract in self:
           vals = {
              'tipo_de_incidencia': 'Alta',
              'employee_id': contract.employee_id.id,
              'fecha': contract.date_start,
              'state': 'done',
           }
           contract.env['incidencias.nomina'].create(vals)

    def _get_work_hours_domain(self, date_from, date_to, domain=None, inside=True):
        if domain is None:
            domain = []
        domain = expression.AND([domain, [
            ('state', 'in', ['validated', 'draft']),
            ('version_id', 'in', self.ids),
        ]])
        if inside:
            domain = expression.AND([domain, [
                ('date', '>=', date_from),
                ('date', '<=', date_to)]])
        else:
            domain = expression.AND([domain, [
                '|', '|',
                '&', '&',
                    ('date', '>=', date_from),
                    ('date', '<', date_to),
                    ('date', '>', date_to),
                '&', '&',
                    ('date', '<', date_from),
                    ('date', '<=', date_to),
                    ('date', '>', date_from),
                '&',
                    ('date', '<', date_from),
                    ('date', '>', date_to)]])
        return domain

    def _get_work_hours(self, date_from, date_to, domain=None):
        """
        Returns the amount (expressed in hours) of work
        for a contract between two dates.
        If called on multiple contracts, sum work amounts of each contract.
        :param date_from: The start date
        :param date_to: The end date
        :returns: a dictionary {work_entry_id: hours_1, work_entry_2: hours_2}
        """
        assert isinstance(date_from, datetime)
        assert isinstance(date_to, datetime)

        # First, found work entry that didn't exceed interval.
        work_entries = self.env['hr.work.entry']._read_group(
            self._get_work_hours_domain(date_from, date_to, domain=domain, inside=True),
            ['work_entry_type_id'],
            ['duration:sum']
        )
        work_data = defaultdict(int)
        work_data.update({work_entry_type.id: duration_sum for work_entry_type, duration_sum in work_entries})
        self._preprocess_work_hours_data(work_data, date_from, date_to)

        # Second, find work entry that exceeds interval and compute right duration.
        work_entries = self.env['hr.work.entry'].search(self._get_work_hours_domain(date_from, date_to, domain=domain, inside=False))

        for work_entry in work_entries:
            date_start = max(date_from, work_entry.date_start)
            date_stop = min(date_to, work_entry.date_stop)
            if work_entry.work_entry_type_id.is_leave:
                contract = work_entry.contract_id
                calendar = contract.resource_calendar_id
                employee = contract.employee_id
                contract_data = employee._get_work_days_data_batch(
                    date_start, date_stop, compute_leaves=False, calendar=calendar
                )[employee.id]

                work_data[work_entry.work_entry_type_id.id] += contract_data.get('hours', 0)
            else:
                work_data[work_entry.work_entry_type_id.id] += work_entry._get_work_duration(date_start, date_stop)  # Number of hours
        return work_data

    def _preprocess_work_hours_data(self, work_data, date_from, date_to):
        """
        Removes extra hours from attendance work data and add a new entry for extra hours
        """
        attendance_contracts = self.filtered(lambda c: c.work_entry_source == 'attendance' and c.wage_type == 'hourly')
        overtime_work_entry_type = self.env.ref('hr_work_entry.overtime_work_entry_type', False)
        default_work_entry_type = self.env['hr.work.entry.type'].sudo().search([('code','=','WORK100')]) #self.structure_type_id.default_work_entry_type_id
        if not attendance_contracts or not overtime_work_entry_type or len(default_work_entry_type) != 1:
            return
        overtime_hours = self.env['hr.attendance.overtime']._read_group(
            [('employee_id', 'in', self.employee_id.ids),
                ('date', '>=', date_from), ('date', '<=', date_to)],
            [], ['duration:sum'],
        )[0][0]
        if not overtime_hours or overtime_hours < 0:
            return
        work_data[default_work_entry_type.id] -= overtime_hours
        work_data[overtime_work_entry_type.id] = overtime_hours
