# -*- coding: utf-8 -*-
{
    'name': 'Lugar de expedición por diario (CFDI 4.0)',
    'version': '19.0.1.0.0',
    'summary': 'Extiende la "Address Issued" del diario a complementos de pago '
               'y a la hora de emisión del CFDI',
    'description': """
Odoo (l10n_mx_edi_extended) ya usa la dirección de emisión del diario como
LugarExpedicion de las facturas, pero:

* los complementos de pago siempre salen con el CP de la compañía;
* la hora del CFDI (Fecha) se calcula con la zona horaria de la compañía.

Este módulo:

* toma la dirección de emisión del diario del pago o, si no tiene, la de los
  diarios de las facturas pagadas cuando todas coinciden;
* calcula la hora con la zona horaria de la dirección de emisión del diario
  (el parámetro nativo l10n_mx_edi_tz_<id diario> sigue teniendo prioridad).
""",
    'author': 'Tecnika',
    'category': 'Accounting/Localizations/Mexico',
    'depends': [
        'l10n_mx_edi_extended',
    ],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
