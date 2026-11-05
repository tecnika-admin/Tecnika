# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    company_size = fields.Selection(
        selection=[
            ('startup', 'Startup'),
            ('micro', 'Micro'),
            ('pyme', 'PyME'),
            ('smb', 'SMB'),
            ('enterprise', 'Empresa'),
        ],
        string='Tamaño',
    )
    commercial_value = fields.Selection(
        selection=[
            ('strategic', 'Estratégico'),
            ('high', 'Alto'),
            ('medium', 'Mediano'),
            ('low', 'Bajo'),
            ('developing', 'En desarrollo'),
        ],
        string='Valor comercial',
        tracking=True,
    )
    customer_stage = fields.Selection(
        selection=[
            ('prospect', 'Prospecto'),
            ('active', 'Cliente activo'),
            ('inactive', 'Cliente inactivo'),
            ('developing', 'En desarrollo'),
        ],
        string='Etapa del cliente',
        tracking=True,
    )
    contact_profile = fields.Selection(
        selection=[
            ('it', 'TI / Sistemas'),
            ('executive', 'Dirección general / Ejecutivo'),
            ('administration', 'Administración'),
            ('finance', 'Contabilidad / Finanzas'),
            ('purchasing', 'Compras'),
            ('operations', 'Operaciones'),
            ('security', 'Seguridad'),
            ('human_resources', 'Recursos Humanos'),
            ('marketing', 'Marketing'),
            ('maintenance', 'Mantenimiento / Infraestructura'),
            ('other', 'Otros'),
        ],
        string='Perfil',
    )
    linkedin_url = fields.Char(string='LinkedIn')

    @api.model
    def _commercial_fields(self):
        return super()._commercial_fields() + [
            'company_size',
            'commercial_value',
            'customer_stage',
        ]
