# -*- coding: utf-8 -*-
"""
Pre-migración 19.1.9: retira hr_work_entry_ce de la base.

El módulo se eliminó del repo el 2026-07-04 (respaldo en tmp/removed_modules/)
porque sus tipos de entrada de trabajo duplicaban los de nomina_cfdi_ee v19.
Si la base viene de un dump donde no se corrió scripts/pre_upgrade_19_map_xmlids.py,
el módulo sigue en estado instalado sin código en el addons path y cada carga
registra "Some modules have inconsistent states: ['hr_work_entry_ce']".

Réplica en SQL del paso 3 de ese script:
  1. Transfiere la propiedad de los menús a nomina_tecnika (que ahora los
     define en views/hr_work_entry_menu.xml con los mismos nombres de XML ID).
  2. Suelta el resto de sus XML IDs: los registros sobreviven como datos de
     usuario (los tipos ya fueron adoptados por nomina_cfdi_ee en la 19.1.8).
  3. Marca el módulo como desinstalado.

Idempotente: si el módulo no existe o ya está desinstalado, no hace nada.
"""
import logging

_logger = logging.getLogger(__name__)

# menus que se movieron de hr_work_entry_ce a nomina_tecnika (mismos nombres)
MENU_NAMES = [
    'menu_hr_payroll_work_entries_base',
    'menu_work_entry',
    'hr_work_entry_configuration',
    'menu_hr_work_entry_type_view',
    'menu_resource_calendar_view',
]


def migrate(cr, version):
    if not version:
        return  # instalacion nueva, no aplica

    cr.execute("SELECT state FROM ir_module_module WHERE name = 'hr_work_entry_ce'")
    row = cr.fetchone()
    if not row or row[0] == 'uninstalled':
        return

    # 1. menus -> nomina_tecnika, salvo que nomina_tecnika ya tenga el suyo
    for name in MENU_NAMES:
        cr.execute("""
            UPDATE ir_model_data d SET module = 'nomina_tecnika'
            WHERE d.module = 'hr_work_entry_ce' AND d.name = %s
              AND NOT EXISTS (
                  SELECT 1 FROM ir_model_data t
                  WHERE t.module = 'nomina_tecnika' AND t.name = %s
              )
        """, (name, name))
        if cr.rowcount:
            _logger.info('menu %s transferido a nomina_tecnika', name)

    # 2. soltar los XML IDs restantes (registros quedan como datos de usuario)
    cr.execute("DELETE FROM ir_model_data WHERE module = 'hr_work_entry_ce'")
    if cr.rowcount:
        _logger.info('liberados %d xmlid(s) de hr_work_entry_ce', cr.rowcount)

    # 3. marcar desinstalado
    cr.execute("""
        UPDATE ir_module_module SET state = 'uninstalled'
        WHERE name = 'hr_work_entry_ce'
    """)
    _logger.info('hr_work_entry_ce marcado como desinstalado')
