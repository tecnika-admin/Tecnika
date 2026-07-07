# -*- coding: utf-8 -*-
"""
Pre-migración 18.x -> 19.1.7 de nomina_cfdi_ee. Corre antes de cargar los
archivos de datos del módulo, en SQL puro (en fase "pre" el ORM no es
confiable). Tres pasos, todos idempotentes:

1. Adopta los hr.work.entry.type y hr.leave.type existentes bajo los XML IDs
   que declaran data/hr_payroll_data.xml y data/hr_data.xml, con noupdate=1,
   fusionando duplicados por código. La base los trae de antes
   (hr_work_entry_ce o captura manual) con nóminas/ausencias históricas
   colgando; sin esto la actualización truena por código duplicado (si los
   XML IDs no están ligados) o por FK contra hr_leave (si _process_end
   intenta borrar los huérfanos).

2. Retira hr_work_entry_ce (eliminado del repo el 2026-07-04, respaldo en
   tmp/removed_modules/): transfiere sus menús a nomina_tecnika (que ahora
   los define con los mismos nombres de XML ID), suelta el resto de sus XML
   IDs (los registros sobreviven como datos de usuario) y lo marca como
   desinstalado. Sin esto cada carga registra "Some modules have
   inconsistent states: ['hr_work_entry_ce']".

3. Corrige el signo de amount_currency en apuntes contables donde quedó
   cruzado respecto al balance (pólizas manuales de pagos USD de 2022):
   Odoo 19 lo exige con la restricción
   account_move_line_check_amount_currency_balance_sign. Solo voltea el
   signo (el valor absoluto en divisa es correcto y los pesos no se tocan).
   Ya se corrigió en producción; queda como red de seguridad para respaldos
   que aún traigan las filas malas.
"""
import logging

_logger = logging.getLogger(__name__)

MODULE = 'nomina_cfdi_ee'

# codigo -> nombre del XML ID en nomina_cfdi_ee (data/hr_payroll_data.xml)
WET_MAP = {
    'FJC': 'work_entry_type_fjc',
    'FJS': 'work_entry_type_fjs',
    'FI': 'work_entry_type_fi',
    'FR': 'work_entry_type_fr',
    'VAC': 'work_entry_type_vac',
    'INC_RT': 'work_entry_type_inc_rt',
    'INC_EG': 'work_entry_type_inc_eg',
    'INC_MAT': 'work_entry_type_inc_mat',
    'DFES': 'work_entry_type_dfest',
    'DFES_3': 'work_entry_type_dfest3',
}

# codigo -> (nombre del XML ID, nombre visible) (data/hr_data.xml)
LEAVE_MAP = {
    'FJC': ('hr_holidays_status_fjc', 'Falta justificada con goce'),
    'FJS': ('hr_holidays_status_fjs', 'Falta justificada sin goce'),
    'FI': ('hr_holidays_status_fi', 'Falta injustificada'),
    'FR': ('hr_holidays_status_fr', 'Falta por retardo'),
    'VAC': ('hr_holidays_status_vac', 'Vacaciones'),
    'INC_RT': ('hr_holidays_status_inc_rt', 'Incapacidad por riesgo trabajo'),
    'INC_EG': ('hr_holidays_status_inc_eg', 'Incapacidad por enfermedad gral.'),
    'INC_MAT': ('hr_holidays_status_inc_mat', 'Incapacidad por maternidad'),
    'DFES': ('hr_holidays_status_dfest', 'Dia festivo'),
    'DFES_3': ('hr_holidays_status_dfest3', 'Dia festivo triple'),
}

# menus que se movieron de hr_work_entry_ce a nomina_tecnika (mismos nombres)
MENU_NAMES = [
    'menu_hr_payroll_work_entries_base',
    'menu_work_entry',
    'hr_work_entry_configuration',
    'menu_hr_work_entry_type_view',
    'menu_resource_calendar_view',
]


def _fk_columns(cr, table):
    """Columnas (tabla, columna) de toda la BD que referencian a `table`."""
    cr.execute("""
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
             ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
             ON tc.constraint_name = ccu.constraint_name
             AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = %s
    """, (table,))
    return cr.fetchall()


def _has_column(cr, table, column):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return bool(cr.fetchone())


def _set_xmlid(cr, model, xml_name, res_id):
    cr.execute("""
        UPDATE ir_model_data
        SET model = %s, res_id = %s, noupdate = true
        WHERE module = %s AND name = %s
    """, (model, res_id, MODULE, xml_name))
    if not cr.rowcount:
        cr.execute("""
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            VALUES (%s, %s, %s, %s, true)
        """, (MODULE, xml_name, model, res_id))


def _adopt(cr, model, table, mapping):
    """Liga los registros existentes a los XML IDs del modulo, fusionando
    duplicados por codigo (o nombre, para capturas manuales sin codigo)."""
    fk_refs = [(t, c) for t, c in _fk_columns(cr, table) if t != 'ir_model_data']
    has_code = _has_column(cr, table, 'code')

    for code, target in mapping.items():
        xml_name, display_name = target if isinstance(target, tuple) else (target, None)

        # name es jsonb con traducciones, de ahi el ILIKE sobre su texto
        clauses, params = [], []
        if has_code:
            clauses.append('code = %s')
            params.append(code)
        if display_name:
            clauses.append('name::text ILIKE %s')
            params.append('%%"%s"%%' % display_name)
        if not clauses:
            continue
        cr.execute(
            'SELECT id FROM "%s" WHERE %s ORDER BY id' % (table, ' OR '.join(clauses)),
            tuple(params),
        )
        ids = [r[0] for r in cr.fetchall()]
        if not ids:
            _logger.info('%s %s: no existe en la BD, lo creara el XML (ok)', model, code)
            continue

        keeper, dups = ids[0], ids[1:]
        if dups:
            for ref_table, ref_col in fk_refs:
                cr.execute(
                    'UPDATE "%s" SET "%s" = %%s WHERE "%s" IN %%s' % (ref_table, ref_col, ref_col),
                    (keeper, tuple(dups)),
                )
            cr.execute(
                "DELETE FROM ir_model_data WHERE model = %s AND res_id IN %s",
                (model, tuple(dups)),
            )
            cr.execute('DELETE FROM "%s" WHERE id IN %%s' % table, (tuple(dups),))
            _logger.info('%s %s: %d duplicado(s) fusionado(s) en id %d', model, code, len(dups), keeper)

        _set_xmlid(cr, model, xml_name, keeper)
        _logger.info('%s -> %s.%s = id %d (noupdate=1)', code, MODULE, xml_name, keeper)

    # XML IDs del modulo apuntando a registros que ya no existen: fuera, para
    # que _process_end no tropiece con ellos
    cr.execute("""
        DELETE FROM ir_model_data d
        WHERE d.module = %%s AND d.model = %%s
          AND NOT EXISTS (SELECT 1 FROM "%s" t WHERE t.id = d.res_id)
    """ % table, (MODULE, model))
    if cr.rowcount:
        _logger.info('%s: %d xmlid(s) huerfano(s) eliminados', model, cr.rowcount)


def _retire_hr_work_entry_ce(cr):
    cr.execute("SELECT state FROM ir_module_module WHERE name = 'hr_work_entry_ce'")
    row = cr.fetchone()
    if not row or row[0] == 'uninstalled':
        return

    # menus -> nomina_tecnika, salvo que nomina_tecnika ya tenga el suyo
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

    # soltar los XML IDs restantes (los registros quedan como datos de usuario)
    cr.execute("DELETE FROM ir_model_data WHERE module = 'hr_work_entry_ce'")
    if cr.rowcount:
        _logger.info('liberados %d xmlid(s) de hr_work_entry_ce', cr.rowcount)

    cr.execute("""
        UPDATE ir_module_module SET state = 'uninstalled'
        WHERE name = 'hr_work_entry_ce'
    """)
    _logger.info('hr_work_entry_ce marcado como desinstalado')


def _fix_amount_currency_sign(cr):
    cr.execute("""
        UPDATE account_move_line
        SET amount_currency = -amount_currency,
            amount_residual_currency = -amount_residual_currency
        WHERE currency_id != company_currency_id
          AND ((balance < 0 AND amount_currency > 0)
            OR (balance > 0 AND amount_currency < 0))
    """)
    if cr.rowcount:
        _logger.info(
            'amount_currency: signo corregido en %d apunte(s) con signo '
            'cruzado respecto al balance', cr.rowcount,
        )


def migrate(cr, version):
    if not version:
        return  # instalacion nueva: no hay datos previos que adoptar
    _adopt(cr, 'hr.work.entry.type', 'hr_work_entry_type', WET_MAP)
    _adopt(cr, 'hr.leave.type', 'hr_leave_type', LEAVE_MAP)
    _retire_hr_work_entry_ce(cr)
    _fix_amount_currency_sign(cr)
