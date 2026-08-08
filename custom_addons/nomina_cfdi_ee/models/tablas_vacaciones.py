# -*- coding: utf-8 -*-

from odoo import models, fields, _, api

class TablasVacacioneslLine(models.Model):
    _name = 'tablas.vacaciones.line'
    _description = 'tablas vacaciones'

    form_id = fields.Many2one('hr.version', string='Vacaciones', required=True)
    dias = fields.Integer('Dias disponibles')
    ano = fields.Selection(
        selection=[('2021', '2021'),
                   ('2022', '2022'),
                   ('2023', '2023'),
                   ('2024', '2024'),
                   ('2025', '2025'),
                   ('2026', '2026'),
                   ('2027', '2027'),
                   ],
        string='Año', required=True)
    estado = fields.Selection(
        selection=[('activo', 'Activo'),
                   ('inactivo', 'Inactivo'),
                   ],
        string='Estatus',)
    #dias_consumido = fields.Integer('Dias consumidos')
    dias_otorgados = fields.Integer('Dias otorgados')
    caducidad = fields.Date('Caducidad')
