# -*- coding:utf-8 -*-

{
    'name': 'Odoo 19 HR Payroll',
    'category': 'Generic Modules/Human Resources',
    'version': '19.1.0',
    'sequence': 1,
    'author': 'IT Admin',
    'summary': 'Payroll For Odoo 19 Community Edition',
    'description': "Odoo 19 Payroll, Payroll Odoo 19, Odoo Community Payroll",
    'website': 'https://odoo.itadmin.com.mx',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'hr_holidays', 'hr_work_entry'
    ],
    'data': [
        'security/hr_payroll_security.xml',
        'security/ir.model.access.csv',
        'data/hr_payroll_sequence.xml',
        'data/hr_payroll_category.xml',
        'data/hr_payroll_data.xml',
        'wizard/hr_payroll_payslips_by_employees_views.xml',
        'views/hr_version_views.xml',
        'views/hr_salary_rule_views.xml',
        'views/hr_payroll_structure_views.xml',
        'views/hr_payslip_line_views.xml',
        'views/hr_payslip_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_payslip_run_views.xml',
        'views/hr_salary_rule_category_views.xml',
        'views/res_config_settings_views.xml',
        'views/hr_leave_type_view.xml',
    ],
    'images': ['static/description/banner.png'],
    'application': True,
}
