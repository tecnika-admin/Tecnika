# -*- coding: utf-8 -*-
import base64
import json
import requests
from odoo import fields, models,api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
from dateutil import parser

class ResCompany(models.Model):
    _inherit = 'res.company'

    curp = fields.Char(string=_('CURP'))
    proveedor_timbrado= fields.Selection(
        selection=[('servidor', _('Principal')),
                   ('servidor2', _('Respaldo')),],
        string=_('Servidor de timbrado'), default='servidor'
    )
    api_key = fields.Char(string=_('API Key'))
    modo_prueba = fields.Boolean(string=_('Modo prueba'))
    regimen_fiscal = fields.Selection(
        selection=[('601', _('General de Ley Personas Morales')),
                   ('603', _('Personas Morales con Fines no Lucrativos')),
                   ('605', _('Sueldos y Salarios e Ingresos Asimilados a Salarios')),
                   ('606', _('Arrendamiento')),
                   ('608', _('Demás ingresos')),
                   ('609', _('Consolidación')),
                   ('610', _('Residentes en el Extranjero sin Establecimiento Permanente en México')),
                   ('611', _('Ingresos por Dividendos (socios y accionistas)')),
                   ('612', _('Personas Físicas con Actividades Empresariales y Profesionales')),
                   ('614', _('Ingresos por intereses')),
                   ('616', _('Sin obligaciones fiscales')),
                   ('620', _('Sociedades Cooperativas de Producción que optan por diferir sus ingresos')),
                   ('621', _('Incorporación Fiscal')),
                   ('622', _('Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras')),
                   ('623', _('Opcional para Grupos de Sociedades')),
                   ('624', _('Coordinados')),
                   ('628', _('Hidrocarburos')),
                   ('607', _('Régimen de Enajenación o Adquisición de Bienes')),
                   ('629', _('De los Regímenes Fiscales Preferentes y de las Empresas Multinacionales')),
                   ('630', _('Enajenación de acciones en bolsa de valores')),
                   ('615', _('Régimen de los ingresos por obtención de premios')),
                   ('625', _('Régimen de las Actividades Empresariales con ingresos a través de Plataformas Tecnológicas')),
                   ('626', _('Régimen Simplificado de Confianza')),],
        string=_('Régimen Fiscal'), 
    )
    archivo_cer = fields.Binary(string=_('Archivo .cer'))
    archivo_key = fields.Binary(string=_('Archivo .key'))
    contrasena = fields.Char(string=_('Contraseña'))
    nombre_fiscal = fields.Char(string=_('Razón social'))
    saldo_timbres =  fields.Float(string=_('Saldo de timbres'), readonly=True)
    saldo_alarma =  fields.Float(string=_('Alarma timbres'), default=10)
    correo_alarma =  fields.Char(string=_('Correo de alarma'))

    rfc_patron = fields.Char(string=_('RFC Patrón'))
    serie_nomina = fields.Char(string=_('Serie nomina'))
    registro_patronal = fields.Char(string=_('Registro patronal'))
    nomina_mail = fields.Char('Nomina Mail',)
    fecha_csd = fields.Datetime(string=_('Vigencia CSD'), readonly=True)
    estado_csd =  fields.Char(string=_('Estado CSD'), readonly=True)
    aviso_csd =  fields.Char(string=_('Aviso vencimiento (días antes)'), default=14)
    company_cfdi = fields.Boolean(string="CFDI MX")

    @api.onchange('country_id')
    def _get_company_cfdi(self):
        if self.country_id:
            if self.country_id.code == 'MX':
               values = {'company_cfdi': True}
            else:
               values = {'company_cfdi': False}
        else:
            values = {'company_cfdi': False}
        self.update(values)

    @api.model
    def contract_warning_mail_cron(self):
        companies = self.search([('nomina_mail','!=',False)])
        cr = self._cr
        dt = datetime.now()
        start_week_day = (dt - timedelta(days=dt.weekday())).date()
        end_week_day = start_week_day + timedelta(days=6)

        where_clause = []
        while start_week_day<=end_week_day:
            where_clause.append("TO_CHAR(date_start,'MM-DD')='%s-%s'"%("{0:0=2d}".format(start_week_day.month),"{0:0=2d}".format(start_week_day.day)))
            start_week_day = start_week_day + timedelta(days=1) #.date()
        where_clause = " OR ".join(where_clause)
        
        for company in companies:
            cr.execute("select id from hr_contract where (%s) and company_id=%d"%(where_clause,company.id))
            contract_ids = [r[0] for r in cr.fetchall()]
            if not contract_ids:
                continue
            for contract in self.env['hr.contract'].browse(contract_ids):
                if contract.state != 'open':
                   continue
                if contract.date_start.year == datetime.today().date().year:
                   continue
                change_done =  False
                for vacation_line in contract.tabla_vacaciones:
                    if str(vacation_line.ano) == str(start_week_day.year):
                       change_done =  True
                if not change_done:
                   if company.nomina_mail:
                         mail_values = {
                         'email_to': company.nomina_mail,
                         'subject': 'Aniversario de un empleado',
                         'body_html': 'Esta semana es el aniversario de ' +  contract.employee_id.name + ' en la empresa, revisar ajuste en sueldo creado en incidencias.',
                         'auto_delete': True,
                         }
                         mail = self.env['mail.mail'].create(mail_values)
                         mail.send()
                   self.calculate_contract_vacaciones(contract)
                   self.create_cambio_salario(contract)
        return

    @api.model
    def calculate_contract_vacaciones(self, contract):
        tablas_cfdi = contract.tablas_cfdi_id
        if not tablas_cfdi:
            tablas_cfdi = self.env['tablas.cfdi'].search([],limit=1)
        if not tablas_cfdi:
            return
        if contract.date_start:
            date_start = contract.date_start
            today = datetime.today().date()
            diff_date = today - date_start
            years = diff_date.days /365.0
            antiguedad_anos = round(years)
        else:
            antiguedad_anos = 0
        if antiguedad_anos < 1.0:
            tablas_cfdi_lines = tablas_cfdi.tabla_antiguedades.filtered(lambda x: x.antiguedad >= antiguedad_anos).sorted(key=lambda x:x.antiguedad)
        else:
            tablas_cfdi_lines = tablas_cfdi.tabla_antiguedades.filtered(lambda x: x.antiguedad <= antiguedad_anos).sorted(key=lambda x:x.antiguedad, reverse=True)
        if not tablas_cfdi_lines:
            return
        tablas_cfdi_line = tablas_cfdi_lines[0]
        today = datetime.today()
        current_year = today.strftime('%Y')
        vac_adelantada = self.env['ir.config_parameter'].sudo().get_param('nomina_cfdi_extras_ee.vacaciones_adelantadas')
        if not vac_adelantada:
           contract.write({'tabla_vacaciones': [(0, 0, {'ano':current_year, 'dias': tablas_cfdi_line.vacaciones, 'dias_otorgados': tablas_cfdi_line.vacaciones})]})
        else:
           contract.write({'tabla_vacaciones': [(0, 0, {'ano':current_year, 'dias': tablas_cfdi_line.vacaciones - contract.vacaciones_adelantadas, 'dias_otorgados': tablas_cfdi_line.vacaciones})], 
                           'vacaciones_adelantadas': 0})
        return True

    @api.model
    def create_cambio_salario(self, contract):
        if contract.date_start:
            today = datetime.today().date()
            diff_date = (today - contract.date_start + timedelta(days=1)).days #today - date_start 
            years = diff_date /365.0
            tablas_cfdi = contract.tablas_cfdi_id
            if not tablas_cfdi:
                tablas_cfdi = self.env['tablas.cfdi'].search([],limit=1)
            if not tablas_cfdi:
                return
            if years < 1.0:
                tablas_cfdi_lines = tablas_cfdi.tabla_antiguedades.filtered(lambda x: x.antiguedad >= years).sorted(key=lambda x:x.antiguedad)
            else:
                tablas_cfdi_lines = tablas_cfdi.tabla_antiguedades.filtered(lambda x: x.antiguedad <= years).sorted(key=lambda x:x.antiguedad, reverse=True)
            if not tablas_cfdi_lines:
                return
            tablas_cfdi_line = tablas_cfdi_lines[0]
            sueldo_diario_integrado = ((365 + tablas_cfdi_line.aguinaldo + (tablas_cfdi_line.vacaciones)* (tablas_cfdi_line.prima_vac/100) ) / 365) * contract.wage/tablas_cfdi.dias_mes
            if sueldo_diario_integrado > (tablas_cfdi.uma * 25):
                sueldo_base_cotizacion = tablas_cfdi.uma * 25
            else:
                sueldo_base_cotizacion = sueldo_diario_integrado
            incidencia = self.env['incidencias.nomina'].create({'tipo_de_incidencia':'Cambio salario', 
                                                                'employee_id': contract.employee_id.id,
                                                                'sueldo_mensual': contract.wage,
                                                                'sueldo_diario': contract.sueldo_diario,
                                                                'sueldo_diario_integrado': sueldo_diario_integrado,
                                                                'sueldo_por_horas' : contract.sueldo_hora,
                                                                'sueldo_cotizacion_base': sueldo_base_cotizacion,
                                                                'fecha': today,
                                                                'contract_id': contract.id
                                                                })
        return

    @api.model
    def get_saldo_by_cron(self):
        companies = self.search([('proveedor_timbrado','!=',False)])
        for company in companies:
            company.get_saldo()
            if company.saldo_timbres < company.saldo_alarma and company.correo_alarma:
                email_template = self.env.ref("nomina_cfdi_ee.email_template_alarma_de_saldo",False)
                if not email_template:return
                emails = company.correo_alarma.split(",")
                for email in emails:
                    email = email.strip()
                    if email:
                        email_template.send_mail(company.id, force_send=True,email_values={'email_to':email})
            if company.aviso_csd and company.fecha_csd and company.correo_alarma: #valida vigencia de CSD
                if datetime.today() + timedelta(days=int(company.aviso_csd)) > fields.Datetime.from_string(company.fecha_csd):
                   email_template = self.env.ref("nomina_cfdi_ee.email_template_alarma_de_csd",False)
                   if not email_template:return
                   emails = company.correo_alarma.split(",")
                   for email in emails:
                       email = email.strip()
                       if email:
                          email_template.send_mail(company.id, force_send=True,email_values={'email_to':email})
        return True

    def get_saldo(self):
        if not self.vat:
           raise UserError(_('Falta colocar el RFC'))
        if not self.proveedor_timbrado:
           raise UserError(_('Falta seleccionar el servidor de timbrado'))
        values = {
                 'rfc': self.vat,
                 'api_key': self.proveedor_timbrado,
                 'modo_prueba': self.modo_prueba,
                 }
        url=''
        if self.proveedor_timbrado == 'servidor':
            url = '%s' % ('https://facturacion.itadmin.com.mx/api/saldo')

        if not url:
            return
        try:
            response = requests.post(url,auth=None,data=json.dumps(values),headers={"Content-type": "application/json"})
            json_response = response.json()
        except Exception as e:
            print(e)
            json_response = {}
    
        if not json_response:
            return
        
        estado_factura = json_response['estado_saldo']
        if estado_factura == 'problemas_saldo':
            raise UserError(_(json_response['problemas_message']))
        if json_response.get('saldo'):
            xml_saldo = base64.b64decode(json_response['saldo'])
        values2 = {
                    'saldo_timbres': xml_saldo
                  }
        self.update(values2)

    def validar_csd(self):
        values = {
                 'rfc': self.vat,
                 'archivo_cer': self.archivo_cer.decode("utf-8"),
                 'archivo_key': self.archivo_key.decode("utf-8"),
                 'contrasena': self.contrasena,
                 }
        url=''
        if self.proveedor_timbrado == 'servidor':
            url = '%s' % ('https://facturacion.itadmin.com.mx/api/validarcsd')
        elif self.proveedor_timbrado == 'servidor2':
            url = '%s' % ('https://facturacion2.itadmin.com.mx/api/validarcsd')
        if not url:
            return
        try:
            response = requests.post(url,auth=None,data=json.dumps(values),headers={"Content-type": "application/json"})
            json_response = response.json()
        except Exception as e:
            print(e)
            json_response = {}

        if not json_response:
            return
        #_logger.info('something ... %s', response.text)

        respuesta = json_response['respuesta']
        if json_response['respuesta'] == 'Certificados CSD correctos':
           self.fecha_csd = parser.parse(json_response['fecha'])
           values2 = {
               'fecha_csd': self.fecha_csd,
               'estado_csd': json_response['respuesta'],
               }
           self.update(values2)
        else:
           raise UserError(respuesta)

    def borrar_csd(self):
        values = {
                 'rfc': self.vat,
                 }
        url=''
        if self.proveedor_timbrado == 'servidor':
            url = '%s' % ('https://facturacion.itadmin.com.mx/api/borrarcsd')
        elif self.proveedor_timbrado == 'servidor2':
            url = '%s' % ('https://facturacion2.itadmin.com.mx/api/borrarcsd')
        if not url:
            return
        try:
            response = requests.post(url,auth=None,data=json.dumps(values),headers={"Content-type": "application/json"})
            json_response = response.json()
        except Exception as e:
            print(e)
            json_response = {}

        if not json_response:
            return
        #_logger.info('something ... %s', response.text)
        respuesta = json_response['respuesta']
        raise UserError(respuesta)

    def borrar_estado(self):
           values2 = {
               'fecha_csd': '',
               'estado_csd': '',
               }
           self.update(values2)

    def button_dummy(self):
        self.get_saldo()
        return True
