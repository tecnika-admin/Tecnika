#-*- coding:utf-8 -*-

{
    'name': 'HR Work Entries Community',
    'category': 'Generic Modules/Human Resources',
    'author': 'IT Admin',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'sequence': 1,
    'website': 'https://www.itadmin.com.mx',
    'summary': 'Funcionalidades para menus de work entries.',
    'description': """Funcionalidades para menus de work entries.""",
    # En Odoo 19 hr_work_entry_contract y hr_work_entry_contract_attendance
    # se fusionaron en hr_work_entry (hr.contract ahora es hr.version).
    'depends': [
        'om_hr_payroll', 'hr_work_entry', 'hr_work_entry_holidays',
    ],
    'data': [
        'data/hr_payroll_data.xml',
        'views/hr_work_entry_menu.xml',
    ],
    'application': True,
}
