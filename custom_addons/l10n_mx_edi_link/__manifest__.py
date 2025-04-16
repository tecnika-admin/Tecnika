# -*- coding: utf-8 -*-
{
    # Nombre descriptivo del módulo
    'name': 'Vinculación Manual CFDI (México)',
    # Versión del módulo - sigue el versionado semántico o el de Odoo
    'version': '18.0.1.0.0',
    # Resumen corto de la funcionalidad del módulo
    'summary': """
        Permite asociar manualmente un CFDI XML externo (Factura, Complemento de Pago)
        a un registro de Asiento Contable (account.move) existente en Odoo v18.
    """,
    # Descripción más detallada de lo que hace el módulo
    'description': """
        Este módulo añade una funcionalidad para vincular manualmente un archivo XML de CFDI,
        que fue previamente timbrado por un Proveedor Autorizado de Certificación (PAC) externo,
        a un asiento contable correspondiente en Odoo.

        Está diseñado principalmente para:
        - Facturas de Cliente (out_invoice)
        - Asientos Contables que representan Complementos de Pago (move_type='entry')

        Características Principales:
        - Agrega un botón 'Asociar CFDI Original' en la vista de formulario de los asientos contables relevantes.
        - Lanza un asistente (wizard) que permite al usuario seleccionar un archivo XML previamente adjunto al registro.
        - Parsea el XML seleccionado para extraer el UUID (Folio Fiscal) del Timbre Fiscal Digital.
        - Realiza validaciones: formato XML, existencia del UUID, y verifica que el UUID no esté ya asociado a otro asiento en Odoo.
        - Actualiza los campos relevantes en el 'account.move': 'l10n_mx_edi_cfdi_uuid', 'l10n_mx_edi_cfdi_state' a 'sent', y 'l10n_mx_edi_cfdi_attachment_id'.
        - Asegura que el adjunto ('ir.attachment') esté correctamente vinculado al 'account.move'.
        - Crea un registro en 'l10n_mx_edi.document' con estado 'sent' y estado SAT 'valid'.
        - Registra la acción en el chatter del asiento contable para auditoría.
        - Incluye logging para facilitar la depuración en caso de errores.
    """,
    'author': 'Jesus Adrian Garza Zavala',
    'website': 'https://www.tu_sitio_web.com',
    'category': 'Accounting/Localizations/Mexico',
    'depends': [
        'account',         # Módulo base de contabilidad
        'l10n_mx_edi',     # Módulo base de la localización mexicana EDI
    ],
    # Lista de archivos XML y CSV que definen datos, vistas y seguridad
    'data': [
        # 1. Seguridad: Define los permisos de acceso al nuevo modelo del wizard
        'security/ir.model.access.csv',
        # 2. Vistas del Wizard: Define la interfaz de usuario del asistente
        'wizards/associate_cfdi_wizard_views.xml',
        # 3. Vistas del Modelo: Modifica la vista de account.move para añadir el botón
        'views/account_move_views.xml',
    ],
    # Indica si el módulo se puede instalar
    'installable': True,
    # Indica si es una aplicación completa (normalmente False para módulos de personalización)
    'application': False,
    # Indica si se debe instalar automáticamente cuando se instalan todas las dependencias (normalmente False)
    'auto_install': False,
    # Licencia del módulo (Común: LGPL-3)
    'license': 'LGPL-3',
}
