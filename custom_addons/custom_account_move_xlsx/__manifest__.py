# -*- coding: utf-8 -*-
{
    'name': 'Exportación de Pólizas a Excel',
    'version': '19.0.1.0.0',
    'summary': 'Exporta las pólizas seleccionadas en la lista, con sus apuntes, '
               'a un archivo Excel (menú Imprimir)',
    'author': 'Tecnika',
    'category': 'Accounting/Accounting',
    'depends': [
        'account',
        'l10n_mx_edi',
        'report_xlsx',
    ],
    'data': [
        'report/poliza_xlsx.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
