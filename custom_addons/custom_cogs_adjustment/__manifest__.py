# -*- coding: utf-8 -*-
{
    'name': 'Ajuste de Costo de Venta Personalizado',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': """
        Permite ajustar el costo de venta de productos en facturas publicadas
        mediante un wizard, afectando valoración de inventario y creando
        asientos de ajuste.
    """,
    'author': 'Tu Nombre/Empresa Aquí', # Reemplaza con tu nombre o el de tu empresa
    'website': 'https://www.tuwebsite.com', # Opcional: Tu sitio web
    'license': 'LGPL-3', # O la licencia que prefieras
    'depends': [
        'account', # Dependencia base de contabilidad
        'stock_account', # Para la relación entre inventario y contabilidad
    ],
    'data': [
        # Archivos de seguridad (importante el orden: primero grupos, luego access)
        'security/cogs_adjustment_security.xml',
        'security/ir.model.access.csv',
        # Archivos de vistas
        'views/account_move_views.xml',
        'views/cogs_adjustment_wizard_views.xml',
        # Los archivos de wizard se cargan a través de las actions en las vistas
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}