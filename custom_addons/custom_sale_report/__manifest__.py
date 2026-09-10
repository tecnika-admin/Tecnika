# -*- coding: utf-8 -*-
{
    'name': 'Reporte Cotización / Pedido Personalizado',
    'version': '19.0.1.0.0',
    'summary': 'Representación impresa de cotizaciones y pedidos de venta con '
               'el mismo diseño que el CFDI 4.0 (reutiliza custom_invoice_report)',
    'author': 'Tecnika',
    'category': 'Sales/Sales',
    'depends': [
        'sale',
        'l10n_mx_edi_sale',
        'custom_invoice_report',
    ],
    'data': [
        'report/report_quotation.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
