{
    'name': "Negative stock not allowed",
    'summary': "Negative stock not allowed | Non-negative Inventory | Zero Inventory | No Negative Stock | Stock Availability Limit",
    'description': """This module used to disallow negative stock from confirm Delivery.""",
    'author': 'Tecnika',
    'category': 'Sales',
    'website': 'https://tecnika.com.mx',
    'support': 'eber.angulo@tecnika.com.mx',
    'version': '18.0.0.1',
    'license': 'LGPL-3',
    'depends': ['mrp', 'sale_management', 'product'],
    'data': [
        'views/product_template_views.xml'
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
}