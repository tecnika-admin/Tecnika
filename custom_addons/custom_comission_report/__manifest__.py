# -*- coding: utf-8 -*-
{
    'name': "Custom Commission Report",  

    'summary': """
        Generates a custom commission report based on paid invoices
        within selected date ranges.
    """,  # Resumen corto

    'description': """
        This module provides a wizard to generate a commission report in XLSX format.
        Users can specify date ranges for invoices and payments.
        The report logic replicates a specific SQL query joining payments, invoices, partners, etc.
        Access is restricted to authorized accounting personnel.
    """,  # Descripción Larga

    'author': "Jesús Adrián Garza Zavala", 
    'website': "https://www.tecnika.com", 


    'category': 'Accounting/Reporting',
    'version': '18.0.1.0.0', # Versión del módulo

    'depends': [
        'base',
        'account', # Dependencia principal para modelos de contabilidad
    ],

    'data': [
        'security/security.xml', # Definición de grupos de seguridad
        'security/ir.model.access.csv', # Permisos de acceso a modelos
        'wizards/commission_report_wizard_view.xml', # Vista del wizard
        'report/report_action.xml', # Acción del reporte XLSX
        'views/menu.xml', # Definición del menú
    ],

    # only loaded in demonstration mode
    'demo': [],

    'installable': True,
    'application': False, # No es una aplicación completa, es un módulo de reporte
    'auto_install': False,
    'license': 'LGPL-3', # O la licencia que prefieras

    # List of external dependencies required for this module
    'external_dependencies': {
        'python': ['xlsxwriter'], # Librería para generar archivos XLSX
    },
}
