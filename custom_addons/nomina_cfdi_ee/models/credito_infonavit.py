# -*- coding: utf-8 -*-
from odoo import models, fields, _, api
from datetime import date, datetime, timedelta
from odoo.exceptions import UserError

class CreditoInfonavit(models.Model):
    _name = 'credito.infonavit'
    _description = 'CreditoInfonavit'

    name = fields.Char("Name", required=True, copy=False, readonly=True,index=True, default=lambda self: _('New'))
# states={'draft': [('readonly', False)]}, 
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    no_credito = fields.Char(string="Número de crédito")
    tipo_de_movimiento = fields.Selection([('15', 'Inicio de crédito vivienda'), 
                                          ('16', 'Fecha de suspensión de descuento'),
                                          ('17', 'Reinicio de descuento'),
                                          ('18', 'Modificación de tipo de descuento'),
                                          ('19', 'Modificación de valor de descuento'),
                                          ('20', 'Modificación de número de crédito'),],
                                            string='Tipo de movimiento')

    tipo_de_descuento = fields.Selection([('1', 'Porcentaje %'), 
                                          ('2', 'Cuota fija'),
                                          ('3', 'Veces SMGV'),],
                                            string='Tipo de descuento', default='1')

    aplica_tabla = fields.Selection([('N', 'No'), 
                                     ('S', 'Si')],
                                     string='Aplica tabla disminución')
    fecha = fields.Date(string="Fecha", required=True)
    valor_descuento = fields.Float(string="Valor descuento", digits = (12,4))
    state = fields.Selection([('draft', 'Borrador'), ('done', 'Hecho'), ('cancel', 'Cancelado')], string='Estado', default='draft')
    #contract_id = fields.Many2one('hr.version', string='Contrato')
    company_id = fields.Many2one('res.company', 'Company', required=True, index=True, default=lambda self: self.env.company)
    valor_infonavit_ant = fields.Float(string="Valor Infonavit anterior", digits = (12,4))
    desc_infonavit_ant = fields.Char(string="Descripción Infonavit anterior")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
           if vals.get('name', _('New')) == _('New'):
               if 'company_id' in vals:
                   vals['name'] = self.env['ir.sequence'].with_company(vals['company_id']).next_by_code('credito.infonavit') or _('New')
               else:
                   vals['name'] = self.env['ir.sequence'].next_by_code('credito.infonavit') or _('New')
        result = super(CreditoInfonavit, self).create(vals_list)
        return result

    def action_validar(self):
        for rec in self:
            descripcion = ''
            if rec.tipo_de_descuento == '1':
                descripcion = 'INFONAVIT porcentaje'
            if rec.tipo_de_descuento == '2':
                descripcion = 'INFONAVIT cuota fija'
            if rec.tipo_de_descuento == '3':
                descripcion = 'INFONAVIT veces SMGV'
            if rec.employee_id and rec.state == 'draft':
                found = False
                for linea in rec.employee_id.tabla_otras_entradas:
                    if 'INFONAVIT' in linea.descripcion:
                        rec.valor_infonavit_ant = linea.monto
                        rec.desc_infonavit_ant = linea.descripcion
                        linea.monto = rec.valor_descuento
                        linea.descripcion = descripcion
                        found = True
                if not found:
                    rec.employee_id.write({'tabla_otras_entradas': [(0, 0, {'descripcion': descripcion, 
                                                                            'codigo': 'D094', 
                                                                            'monto': rec.valor_descuento})]})
            rec.write({'state':'done'})
        return

    def action_cancelar(self):
        for rec in self:
            if rec.employee_id and rec.state == 'done':
                for linea in rec.employee_id.tabla_otras_entradas:
                    if 'INFONAVIT' in linea.descripcion:
                        linea.monto = rec.valor_infonavit_ant
                        #linea.descripcion= rec.desc_infonavit_ant
            rec.write({'state':'cancel'})

    def action_draft(self):
        self.write({'state':'draft'})

    def unlink(self):
        raise UserError("Los registros no se pueden borrar, solo cancelar.")

    def action_change_state(self):
        for creditoinfonavit in self:
            if creditoinfonavit.state == 'draft':
                creditoinfonavit.action_validar()
