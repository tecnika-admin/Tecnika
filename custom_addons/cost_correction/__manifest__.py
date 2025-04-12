# -*- coding: utf-8 -*-
{
    'name': 'Cost Correction for Invoices',
    'version': '18.0.1.0.0',
    'summary': """Allows manual cost correction for products on posted Mexican invoices.""",
    'description': """
        Adds a feature to manually correct the cost of goods sold
        for storable products (type='consu', is_storable=True)
        on customer invoices that have already been posted and electronically signed (CFDI).
        It adjusts both the invoice's journal entry and the related stock valuation entry.
    """,
    'author': 'Your Company Name / Developer Name', # Reemplazar con tu nombre/empresa
    'website': 'Your Website', # Opcional
    'category': 'Accounting/Accounting',
    'depends': [
        'account',          # Core accounting
        'stock_account',    # Linking stock moves and accounting
        'l10n_mx_edi',      # For CFDI check (l10n_mx_edi_cfdi_uuid)
        'sale_management',  # To access sale_order_line.move_ids
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/cost_correction_wizard_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'OEEL-1', # O Ajustar a OPL-1 u otra si aplica
}