# -*- coding: utf-8 -*-
{
    # Nombre descriptivo del módulo (actualizado)
    'name': 'Vinculación Manual CFDI Pagos (REP - México)',
    # Versión del módulo - sigue el versionado semántico o el de Odoo
    'version': '18.0.1.0.1', # Incremento de versión por cambio funcional
    # Resumen corto de la funcionalidad del módulo (actualizado)
    'summary': """
        Permite asociar manualmente un CFDI XML externo de Complemento de Pago (REP)
        a un registro de Asiento Contable de Pago (tipo 'entry') existente en Odoo v18.
    """,
    # Descripción más detallada de lo que hace el módulo (actualizada)
    'description': """
        Este módulo añade una funcionalidad para vincular manualmente un archivo XML de
        Complemento de Pago (REP), que fue previamente timbrado por un PAC externo,
        a un asiento contable de pago (tipo 'entry') correspondiente en Odoo.

        Está diseñado específicamente para:
        - Asientos Contables que representan Pagos y necesitan asociar su REP externo (move_type='entry')

        Características Principales:
        - Agrega un botón 'Asociar CFDI Pago (REP)' en la vista de formulario de los asientos contables de pago.
        - Lanza un asistente (wizard) que permite al usuario seleccionar un archivo XML (REP) previamente adjunto al registro.
        - Parsea el XML seleccionado para extraer el UUID (Folio Fiscal) del Timbre Fiscal Digital.
        - Realiza validaciones: formato XML, existencia del UUID, y verifica que el UUID no esté ya asociado a otro asiento en Odoo.
        - Actualiza los campos relevantes en el 'account.move': 'l10n_mx_edi_cfdi_uuid', 'l10n_mx_edi_cfdi_state' a 'sent', 'l10n_mx_edi_sat_state' a 'valid' y 'l10n_mx_edi_cfdi_attachment_id'.
        - Asegura que el adjunto ('ir.attachment') esté correctamente vinculado al 'account.move'.
        - Crea un registro en 'l10n_mx_edi.document' con estado 'payment_sent' y estado SAT 'valid'.
        - Registra la acción en el chatter del asiento contable para auditoría.
        - Incluye logging para facilitar la depuración en caso de errores.
    """,
    'author': 'Jesus Adrian Garza Zavala',
    'website': 'https://www.tecnika.com',
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
