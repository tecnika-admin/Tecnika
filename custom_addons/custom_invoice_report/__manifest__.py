# -*- coding: utf-8 -*-
{
    'name': 'Reporte Factura Personalizado (CFDI 4.0)',
    'version': '18.0.2.0.0',
    'summary': 'Representación impresa del CFDI 4.0 con diseño fiscal mexicano '
               '(hereda account.report_invoice_with_payments)',
    'author': 'Tecnika',
    'category': 'Accounting/Localizations/Mexico',
    'depends': [
        'account',
        'l10n_mx_edi',
    ],
    'data': [
        'report/report_invoice.xml',
        'report/report_invoice_cfdi.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'custom_invoice_report/static/src/css/report_invoice_cfdi.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
