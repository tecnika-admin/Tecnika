# -*- coding: utf-8 -*-
{
    'name': 'Custom Sale Timesheet',
    'version': '19.0.1.0.0',
    'summary': 'Corrige el cálculo de progreso de tareas en el portal de clientes',
    'description': """
        El campo portal_progress de sale_timesheet_enterprise filtra las líneas analíticas
        con project_id != False, lo que excluye timesheets cuando se usa una cuenta analítica
        compartida entre proyectos. Este módulo agrega el campo custom_portal_progress que
        calcula el progreso directamente por task_id sin ese filtro, y sobreescribe la
        plantilla del portal para mostrarlo al cliente.
    """,
    'author': 'Tecnika',
    'website': 'https://www.tecnika.com',
    'category': 'Project',
    'depends': ['sale_timesheet_enterprise'],
    'data': [
        'views/portal_task_template.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
