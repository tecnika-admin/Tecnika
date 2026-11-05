# -*- coding: utf-8 -*-
{
    'name': 'Datos comerciales de clientes',
    'version': '19.0.1.0.0',
    'summary': 'Agrega tamaño, valor comercial, etapa, perfil y LinkedIn a los '
               'contactos',
    'description': """
Enriquece res.partner con datos para segmentar clientes:

* a nivel empresa, heredados por sus contactos: tamaño, valor comercial y
  etapa del cliente;
* propios de cada registro: perfil (solo personas) y LinkedIn.

Cargo actual y Sector no se agregan porque ya existen en Odoo: son los campos
nativos function (Puesto) e industry_id (Industria). Los conceptos de Sector se
administran en Contactos > Configuración > Industrias.
""",
    'author': 'Tecnika',
    'category': 'Sales/CRM',
    'depends': [
        'contacts',
    ],
    'data': [
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
