# -*- coding: utf-8 -*-
{
    'name': "Custom Purchase Requisition Flow", 

    'summary': """
        Adds detailed quantity tracking and validation to Purchase Requisition Lines.
        Añade seguimiento detallado de cantidades y validación a las Líneas de Acuerdos de Compra.
        """,

    'description': """
        - Adds fields to track quantities in different stages (Manufacturing, Brand Whs, Wholesaler Whs, Tecnika Whs, Customer).
        - Calculates total ordered quantity based on related confirmed POs.
        - Calculates quantity received in Tecnika warehouse based on stock moves.
        - Implements onchange logic to automatically subtract quantities from the previous stage when a subsequent stage is updated.
        - Adds validation constraints to ensure the sum of quantities in all stages equals the total ordered quantity and prevents negative quantities.
    """,

    'author': "Jesus Adrian Garza Zavala", 
    'website': "https://www.tecnika.com", 

    'category': 'Purchases', # Categoría apropiada
    'version': '18.0.1.0.0', # Versión de tu módulo

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'purchase_requisition', # Dependencia clave del módulo de Acuerdos de Compra
        'stock', # Necesario para acceder a stock.move
        'purchase_stock', # Necesario para el vínculo entre purchase.order.line y stock.move
        'account',
        ],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv', # (Opcional si necesitas reglas de acceso específicas)
        'views/purchase_requisition_views.xml', # Carga el archivo de la vista
    ],
    # only loaded in demonstration mode
    'demo': [
        # 'demo/demo.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3', # O la licencia que prefieras
}
