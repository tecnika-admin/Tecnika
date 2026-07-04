# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import logging
_logger = logging.getLogger(__name__)

class Employee(models.Model):
    _inherit = "hr.employee"

    no_empleado = fields.Char('Número de empleado')
    tipo_pago = fields.Selection(selection=[('transferencia', 'Transferencia'),('efectivo', 'Efectivo'),
                                         ('cheque', 'Cheque')],
        string='Tipo de Pago',
    )
    banco = fields.Many2one('res.bank','Banco empleado')
    no_cuenta = fields.Char('No. cuenta empleado')
    rfc = fields.Char('RFC')
    curp = fields.Char('CURP')
    segurosocial = fields.Char('Seguro social')
    correo_electronico = fields.Char('Correo electrónico')
    tipo_cuenta = fields.Selection(selection=[('t_debido', 'Tarjeta de débito'),('cheques', 'Cheques'),
                                         ('c_ahorro', 'Cuenta de ahorro'),('t_credito', 'Tarjeta de crédito')],
        string='Tipo de cuenta',
    )
    diario_pago = fields.Many2one('account.journal', string='Cuenta de pago', domain=[('type', 'in', ('bank', 'cash'))])

    registro_patronal_id = fields.Many2one('registro.patronal', string='Registro patronal')

    regimen = fields.Selection(
        selection=[('02', '02 - Sueldos'),
                   ('03', '03 - Jubilados'),
                   ('04', '04 - Pensionados'),
                   ('05', '05 - Asimilados Miembros Sociedades Cooperativas Produccion'),
                   ('06', '06 - Asimilados Integrantes Sociedades Asociaciones Civiles'),
                   ('07', '07 - Asimilados Miembros consejos'),
                   ('08', '08 - Asimilados comisionistas'),
                   ('09', '09 - Asimilados Honorarios'),
                   ('10', '10 - Asimilados acciones'),
                   ('11', '11 - Asimilados otros'),
                   ('12', '12 - Jubilados o Pensionados'),
                   ('13', '13 - Indemnización o Separación'),
                   ('99', '99 - Otro Regimen'),],
        string='Régimen',
    )
    contrato = fields.Selection(
        selection=[('01', '01 - Contrato de trabajo por tiempo indeterminado'), 
                   ('02', '02 - Contrato de trabajo para obra determinada'), 
                   ('03', '03 - Contrato de trabajo por tiempo determinado'),
                   ('04', '04 - Contrato de trabajo por temporada'), 
                   ('05', '05 - Contrato de trabajo sujeto a prueba'),
                   ('06', '06 - Contrato de trabajo con capacitación inicial'), 
                   ('07', '07 - Modalidad de contratación por pago de hora laborada'), 
                   ('08', '08 - Modalidad de trabajo por comisión laboral'), 
                   ('09', '09 - Modalidades de contratación donde no existe relación de trabajo'), 
                   ('10', '10 - Jubilación, pensión, retiro'), 
                   ('99', '99 - Otro contrato'),],
        string='Contrato',
    )

    jornada = fields.Selection(
        selection=[('01', '01 - Diurna'), 
                   ('02', '02 - Nocturna'), 
                   ('03', '03 - Mixta'),
                   ('04', '04 - Por hora'), 
                   ('05', '05 - Reducida'),
                   ('06', '06 - Continuada'), 
                   ('07', '07 - Partida'), 
                   ('08', '08 - Por turnos'), 
                   ('99', '99 - Otra Jornada'),],
        string='Jornada',
    )
    estado = fields.Many2one('res.country.state','Lugar donde labora (estado)')

    empleado_nombre = fields.Char("Nombre")
    empleado_paterno = fields.Char("Apellido Paterno")
    empleado_materno = fields.Char("Apellido Materno")
    sindicalizado = fields.Boolean('Sindicalizado', default=False)
    domicilio_receptor = fields.Char("Código postal (SAT)")
    company_cfdi = fields.Boolean(related="company_id.company_cfdi",store=True)
    confianza = fields.Boolean('Es de confianza', default=False)
    directivo = fields.Boolean('Directivo, administrativo o gerencia', default=False)

    periodicidad_pago = fields.Selection(
        selection=[('01', 'Diario'), 
                   ('02', 'Semanal'), 
                   ('03', 'Catorcenal'),
                   ('04', 'Quincenal'), 
                   ('05', 'Mensual'),
                   ('06', 'Bimensual'), 
                   ('07', 'Unidad obra'),
                   ('08', 'Comisión'), 
                   ('09', 'Precio alzado'), 
                   ('10', 'Pago por consignación'), 
                   ('99', 'Otra periodicidad'),],
        string='Periodicidad de pago CFDI',
    )
    antiguedad_anos = fields.Float('Años de antiguedad', compute='_compute_antiguedad_anos')
    conteo_dias = fields.Selection(
        selection=[('01', 'Por periodo'), 
                   ('02', 'Por día'),
                   ('03', 'Mes proporcional 15.21'),
                   ('04', 'Mes proporcional 15.2083'),],
        string='Conteo de días',
    )
    tipo_prima_vacacional = fields.Selection(
        selection=[('01', 'Al cumplir el año'), 
                   ('02', 'Con día de vacaciones'),
                   ('03', 'Al cumplir el año - 2da qna'),
                   ('04', 'Manualmente'),
                  ],
        string='Prima vacacional',
        default = '02'
    )
    septimo_dia = fields.Boolean(string='Descontar faltas en 7mo día')
    incapa_sept_dia = fields.Boolean(string='Incluir incapacidad en 7mo día')
    sept_dia = fields.Boolean(string='Séptimo día separado')
    tipo_semana = fields.Selection(
        selection=[('01', 'Semana 6 x 1'), 
                   ('02', 'Semana 5 x 2'),
                   ('03', 'Semana 4 x 3'),
                  ],
        string='Tipo de semana',
        default = '01'
    )
    prima_dominical = fields.Boolean(string='Prima dominical')
    calc_isr_extra = fields.Boolean(string='Incluir nóminas extraordinarias en calculo ISR mensual', default = False)
    faltas_proporcionales = fields.Boolean(string='Mostrar faltas proporcionales')

    #############  Quitar en version Odoo 20 ######################################
    bono_productividad = fields.Boolean('Bono productividad')
    bono_productividad_amount = fields.Float('Monto bono productividad')
    bono_asistencia = fields.Boolean('Bono asistencia')
    bono_asistencia_amount = fields.Float('Monto bono asistencia')
    bono_puntualidad = fields.Boolean('Bono puntualidad')
    bono_puntualidad_amount = fields.Float('Monto bono puntualidad')
    fondo_ahorro  = fields.Boolean('Fondo de ahorro')
    fondo_ahorro_amount  = fields.Float('Monto fondo de ahorro')
    vale_despensa  = fields.Boolean('Vale de despensa')
    vale_despensa_amount  = fields.Float('Monto vale de despensa')
    alimentacion  = fields.Boolean('Alimentación')
    alimentacion_amount  = fields.Float('Monto alimentación')
    percepcion_adicional  = fields.Boolean('Percepcion adicional')
    percepcion_adicional_amount  = fields.Float('Monto percepcion adicional')
    infonavit_fijo = fields.Float('Infonavit (fijo)', digits = (12,4))
    infonavit_vsm = fields.Float('Infonavit (vsm)', digits = (12,4))
    infonavit_porc = fields.Float('Infonavit (%)', digits = (12,4))
    prestamo_fonacot = fields.Float('Prestamo FONACOT')
    pens_alim = fields.Float('Pensión alimenticia (%)')
    pens_alim_fijo = fields.Float('Pensión alimenticia (fijo)')
    caja_ahorro  = fields.Boolean('Caja de ahorro')
    caja_ahorro_amount  = fields.Float('Monto caja de ahorro')
    deduccion_adicional  = fields.Boolean('Deduccion adicional')
    deduccion_adicional_amount  = fields.Float('Monto deduccion adicional')
    ################################################################################

    riesgo_puesto = fields.Selection(readonly=False, related='version_id.riesgo_puesto', inherited=True, groups="hr.group_hr_manager")
    sueldo_diario = fields.Float(readonly=False, related='version_id.sueldo_diario', inherited=True, groups="hr.group_hr_manager")
    sueldo_hora = fields.Float(readonly=False, related='version_id.sueldo_hora', inherited=True, groups="hr.group_hr_manager")
    sueldo_diario_integrado = fields.Float(readonly=False, related='version_id.sueldo_diario_integrado', inherited=True, groups="hr.group_hr_manager")
    sueldo_base_cotizacion = fields.Float(readonly=False, related='version_id.sueldo_base_cotizacion', inherited=True, groups="hr.group_hr_manager")
    tablas_cfdi_id = fields.Many2one(readonly=False, related='version_id.tablas_cfdi_id', inherited=True, groups="hr.group_hr_manager")
    wage_type = fields.Selection(readonly=False, related='version_id.wage_type', inherited=True, groups="hr.group_hr_manager")
    tabla_otras_entradas = fields.One2many('otras.entradas.empleados', 'form_id')

    @api.onchange('segurosocial')
    def _check_nss_length(self):
        if self.segurosocial:
            if len(self.segurosocial) != 11:
                raise UserError(_('La longitud del número de seguro social es incorrecto'))

    @api.onchange('rfc')
    def _check_rfc_length(self):
        if self.rfc:
            if len(self.rfc) != 12 and len(self.rfc) != 13:
                raise UserError(_('La longitud del RFC es incorrecto'))

    @api.onchange('wage')
    def _compute_sueldo(self):
        if self.wage and self.tablas_cfdi_id:
            values = {
            'sueldo_diario': self.wage/self.tablas_cfdi_id.dias_mes,
            'sueldo_hora': self.wage/self.tablas_cfdi_id.dias_mes/8,
            'sueldo_diario_integrado': self.calculate_sueldo_diario_integrado(),
            'sueldo_base_cotizacion': self.calculate_sueldo_base_cotizacion(),
            }
            self.update(values)

    @api.depends('date_start')
    def _compute_antiguedad_anos(self):
        for employee in self:
            date_start = self._get_first_version_date()
            today = datetime.today().date()
            diff_date = today - date_start
            years = diff_date.days /365.0
            employee.antiguedad_anos = int(years)

    def antiguedad_to(self, contract_id, date_to):
        antiguedad = 0
        if contract_id.date_start: 
            date_start = contract_id.date_start
            diff_date = date_to - date_start 
            antiguedad = diff_date.days / 365.0
        return antiguedad

    @api.model
    def calcular_liquidacion(self):
        first_date = self._get_first_version_date()
        if self.date_end:
            diff_date = (self.date_end - first_date + timedelta(days=1)).days
            years = diff_date /365.0
            self.antiguedad_anos = int(years)
            self.dias_totales = self.antiguedad_anos * self.dias_x_ano + self.dias_base

    def button_dummy(self):
        self.calcular_liquidacion()
        return True

    @api.model
    def calculate_sueldo_base_cotizacion(self):
        first_date = self._get_first_version_date()
        if first_date: 
            today = datetime.today().date()
            diff_date = (today - first_date + timedelta(days=1)).days
            years = diff_date /365.0
            #_logger.info('years ... %s', years)
            tablas_cfdi = self.tablas_cfdi_id 
            if not tablas_cfdi: 
                tablas_cfdi = self.env['tablas.cfdi'].search([],limit=1) 
            if not tablas_cfdi:
                return 
            if years < 1.0: 
                tablas_cfdi_lines = tablas_cfdi.tabla_antiguedades.filtered(lambda x: x.antiguedad >= years).sorted(key=lambda x:x.antiguedad) 
            elif years < 6.0:
                tablas_cfdi_lines = tablas_cfdi.tabla_antiguedades.filtered(lambda x: x.antiguedad <= years).sorted(key=lambda x:x.antiguedad, reverse=True)
            else:
                tablas_cfdi_lines = tablas_cfdi.tabla_antiguedades.filtered(lambda x: x.antiguedad >= years).sorted(key=lambda x:x.antiguedad, reverse=False)
            if not tablas_cfdi_lines: 
                return 
            tablas_cfdi_line = tablas_cfdi_lines[0]
            max_sdi = tablas_cfdi.uma * 25
            sdi = ((365 + tablas_cfdi_line.aguinaldo + (tablas_cfdi_line.vacaciones)* (tablas_cfdi_line.prima_vac/100) ) / 365 ) * self.wage/self.tablas_cfdi_id.dias_mes
            if sdi > max_sdi:
                sueldo_base_cotizacion = max_sdi
            else:
                sueldo_base_cotizacion = sdi
        else: 
            sueldo_base_cotizacion = 0
        return sueldo_base_cotizacion

    @api.model
    def calculate_sueldo_diario_integrado(self):
        first_date = self._get_first_version_date()
        if first_date: 
            today = datetime.today().date()
            diff_date = (today - first_date + timedelta(days=1)).days
            years = diff_date /365.0
            #_logger.info('years ... %s', years)
            tablas_cfdi = self.tablas_cfdi_id 
            if not tablas_cfdi: 
                tablas_cfdi = self.env['tablas.cfdi'].search([],limit=1) 
            if not tablas_cfdi:
                return 
            if years < 1.0: 
                tablas_cfdi_lines = tablas_cfdi.tabla_antiguedades.filtered(lambda x: x.antiguedad >= years).sorted(key=lambda x:x.antiguedad) 
            elif years < 6.0:
                tablas_cfdi_lines = tablas_cfdi.tabla_antiguedades.filtered(lambda x: x.antiguedad <= years).sorted(key=lambda x:x.antiguedad, reverse=True)
            else:
                tablas_cfdi_lines = tablas_cfdi.tabla_antiguedades.filtered(lambda x: x.antiguedad >= years).sorted(key=lambda x:x.antiguedad, reverse=False)
            if not tablas_cfdi_lines: 
                return 
            tablas_cfdi_line = tablas_cfdi_lines[0]
            max_sdi = tablas_cfdi.uma * 25
            sdi = ((365 + tablas_cfdi_line.aguinaldo + (tablas_cfdi_line.vacaciones)* (tablas_cfdi_line.prima_vac/100.0) ) / 365.0 ) * self.wage/self.tablas_cfdi_id.dias_mes
            sueldo_diario_integrado = sdi
        else: 
            sueldo_diario_integrado = 0
        return sueldo_diario_integrado


class OtrasEntradasEmpleados(models.Model):
    _name = 'otras.entradas.empleados'
    _description = 'OtrasEntradasEmpleados'

    form_id = fields.Many2one('hr.employee', required=True) 
    monto = fields.Float('Monto') 
    descripcion = fields.Char('Descripcion') 
    codigo = fields.Char('Codigo')
    porcentaje = fields.Float('Porcentaje') 
    estado = fields.Selection(selection=[('activo', 'Activo'),('inactivo', 'Inactivo')], string='Estado', required=True, default='activo')
