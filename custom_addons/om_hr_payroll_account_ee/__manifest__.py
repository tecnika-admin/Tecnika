#-*- coding:utf-8 -*-

{
    'name': 'Odoo 19 HR Payroll Accounting EE',
    'category': 'Generic Modules/Human Resources',
    'author': 'IT Admin',
    'version': '19.1.2',
    'sequence': 1,
    'website': 'https://www.itadmin.com.mx',
    'summary': 'Funcionalidades para crear pólizas desde las nóminas.',
    'description': """Funcionalidades para crear pólizas desde las nóminas.""",
    'depends': [
        'om_hr_payroll', 'account', 'nomina_cfdi_ee', 'nomina_cfdi_extras_ee'
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_payroll_account_views.xml',
        'views/res_config_settings_view.xml',
        'views/tablas_cfdi_view.xml',
        'wizard/poliza_imss.xml',
    ],
    'application': True,
    'license': 'LGPL-3',
}
