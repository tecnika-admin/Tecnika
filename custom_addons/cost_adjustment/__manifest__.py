# -*- coding: utf-8 -*-
{
    'name': "Ajuste de Costo de Venta Post-Facturación",

    'summary': """
        Permite ajustar el costo de venta y la valoración de inventario
        en facturas de cliente ya timbradas sin necesidad de cancelación fiscal.""",

    'description': """
        Módulo que introduce una herramienta para corregir el Costo de Venta (COGS)
        y las capas de valoración de inventario (stock.valuation.layer) asociadas
        a líneas de facturas de venta de clientes que fueron emitidas y timbradas (CFDI)
        con un costo incorrecto o cero.

        Funcionalidades Principales:
        - Selección de facturas de cliente timbradas.
        - Selección de líneas específicas de la factura a ajustar.
        - Cálculo del ajuste basado en el costo promedio actual del producto.
        - Generación de un asiento contable de ajuste en un diario específico.
        - Creación de una capa de valoración de inventario (SVL) de ajuste.
        - Trazabilidad completa entre el ajuste, la factura original y el asiento generado.
        - Reversión segura del ajuste y sus impactos contables/inventario.
        - Control de acceso mediante grupo de seguridad.
    """,

    'author': "Jesus Adrian Garza Zavala", 
    'website': "https://www.tecnika.com", 


    'category': 'Accounting/Accounting', 
    'version': '18.0.1.0.0', # Versión del módulo (Odoo.Major.Minor.Patch.Revision)

    'depends': [
        'base',
        'account', # Necesario para account.move, account.journal, etc.
        'stock',   # Necesario para stock.move, stock.valuation.layer, product.category accounts
        'sale_management', # Necesario para la trazabilidad via sale.order.line
        'l10n_mx_edi', # Necesario para los campos de CFDI (l10n_mx_edi_cfdi_uuid, edi_state)
        'mail', # Necesario para chatter (mail.thread, mail.activity.mixin)
    ],

    # Archivos que siempre se cargan
    'data': [
        # 1. Seguridad (permisos y grupos)
        'security/ir.model.access.csv',
        'data/cost_adjustment_groups.xml', # Carga el grupo antes que las vistas/menús que lo usan
        # 2. Datos Iniciales (secuencias, etc.)
        'data/ir_sequence_data.xml',
        # 'data/cost_adjustment_journal_data.xml', # Descomentar si se crea el diario vía XML
        # 3. Vistas y Acciones/Menús
        'views/cost_adjustment_views.xml',
        'views/account_move_views.xml',
        'views/cost_adjustment_menus.xml',
    ],
    # Archivos cargados solo en modo demostración
    'demo': [
        # 'demo/demo.xml', # Si se crean datos de demostración
    ],
    'installable': True,
    'application': False, # Es una extensión de funcionalidad, no una aplicación principal
    'auto_install': False,
    'license': 'LGPL-3', # O la licencia que prefieras (AGPL-3, OEEL-1, etc.)
}
