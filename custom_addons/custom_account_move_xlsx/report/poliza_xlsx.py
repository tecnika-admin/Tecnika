# -*- coding: utf-8 -*-
from datetime import datetime, time

from odoo import models
from odoo.tools import html2plaintext


class PolizaXlsx(models.AbstractModel):
    """Exporta las pólizas seleccionadas a Excel.

    Hoja "Apuntes": una fila por apunte con los datos de la póliza repetidos
    (pensada para filtrar y hacer tablas dinámicas).
    Hoja "Pólizas": una fila por póliza con sus totales de Debe y Haber.
    """
    _name = 'report.custom_account_move_xlsx.poliza_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Pólizas contables en Excel'

    def _get_objs_for_report(self, docids, data):
        # La base toma el modelo de context['active_model'], que no siempre
        # viene (p. ej. al llamarlo desde código); el modelo aquí es fijo.
        ids = (docids
               or (data or {}).get('context', {}).get('active_ids')
               or self.env.context.get('active_ids', []))
        return self.env['account.move'].browse(ids).sorted(lambda m: (m.date, m.name or '', m.id))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _poliza_formats(self, workbook):
        base = {'font_name': 'Arial', 'font_size': 9, 'valign': 'top'}
        money = '#,##0.00;-#,##0.00;""'

        def fmt(**kw):
            return workbook.add_format(dict(base, **kw))

        return {
            'header': fmt(bold=True, bg_color='#1F3864', font_color='#FFFFFF',
                          border=1, text_wrap=True, valign='vcenter', align='center'),
            'text': fmt(),
            'wrap': fmt(text_wrap=True),
            'date': fmt(num_format='dd/mm/yyyy', align='left'),
            'int': fmt(num_format='0'),
            'money': fmt(num_format=money),
            'rate': fmt(num_format='#,##0.0000;-#,##0.0000;""'),
            'money_red': fmt(num_format=money, font_color='#C00000', bold=True,
                             bg_color='#FDE9E7'),
            'total_label': fmt(bold=True, top=2, align='right'),
            'total': fmt(bold=True, top=2, num_format=money),
        }

    def _poliza_analytic_names(self, lines):
        """Mapa id -> nombre de todas las cuentas analíticas del lote (una sola lectura)."""
        ids = set()
        for distribution in lines.mapped('analytic_distribution'):
            for key in (distribution or {}):
                ids.update(int(i) for i in str(key).split(',') if i.strip().isdigit())
        accounts = self.env['account.analytic.account'].with_context(active_test=False).browse(ids).exists()
        return {a.id: a.display_name for a in accounts}

    @staticmethod
    def _poliza_analytic_text(distribution, names):
        parts = []
        for key, pct in (distribution or {}).items():
            label = ' / '.join(names.get(int(i), i) for i in str(key).split(',') if i.strip().isdigit())
            parts.append('%s %s%%' % (label, ('%.2f' % pct).rstrip('0').rstrip('.')))
        return '; '.join(parts)

    @staticmethod
    def _poliza_date(value):
        return datetime.combine(value, time.min) if value else None

    def _poliza_write_table(self, sheet, columns, rows, formats, totals=()):
        """Escribe encabezado, filas, fila de totales con SUBTOTAL, autofiltro y panes.

        columns: lista de (título, ancho, formato); cada fila es una lista de
        valores alineada con columns, o (valores, {índice_columna: formato}) para
        sobreescribir formatos puntuales.
        totals: índices de columnas numéricas a totalizar.
        """
        sheet.set_row(0, 30)
        for col, (title, width, _fmt) in enumerate(columns):
            sheet.write(0, col, title, formats['header'])
            sheet.set_column(col, col, width)

        sums = dict.fromkeys(totals, 0.0)
        for row_idx, row in enumerate(rows, start=1):
            values, overrides = row if isinstance(row, tuple) else (row, {})
            for col, value in enumerate(values):
                cell_fmt = formats[overrides.get(col, columns[col][2])]
                if value is None or value == '':
                    sheet.write_blank(row_idx, col, None, cell_fmt)
                elif isinstance(value, datetime):
                    sheet.write_datetime(row_idx, col, value, cell_fmt)
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    sheet.write_number(row_idx, col, value, cell_fmt)
                    if col in sums:
                        sums[col] += value
                else:
                    sheet.write_string(row_idx, col, str(value), cell_fmt)
        last = len(rows)

        if totals:
            total_row = last + 1
            first_total = min(totals)
            if first_total:
                sheet.write(total_row, first_total - 1, 'Totales', formats['total_label'])
            for col in totals:
                ref = '%s2:%s%d' % (self._col_letter(col), self._col_letter(col), max(last, 1) + 1)
                sheet.write_formula(total_row, col, '=SUBTOTAL(9,%s)' % ref, formats['total'], round(sums[col], 2))

        sheet.autofilter(0, 0, max(last, 1), len(columns) - 1)
        sheet.freeze_panes(1, 0)

    @staticmethod
    def _col_letter(col):
        letters = ''
        col += 1
        while col:
            col, rem = divmod(col - 1, 26)
            letters = chr(65 + rem) + letters
        return letters

    # ------------------------------------------------------------------
    # Reporte
    # ------------------------------------------------------------------
    def generate_xlsx_report(self, workbook, data, moves):
        formats = self._poliza_formats(workbook)
        multi_company = len(moves.company_id) > 1
        move_types = dict(moves._fields['move_type']._description_selection(self.env))
        states = dict(moves._fields['state']._description_selection(self.env))
        has_uuid = 'l10n_mx_edi_cfdi_uuid' in moves._fields

        lines_by_move = {
            move: move.line_ids.filtered('account_id').sorted(lambda l: (l.sequence, l.id))
            for move in moves
        }
        all_lines = moves.line_ids.filtered('account_id')
        analytic_names = self._poliza_analytic_names(all_lines)

        def move_head(move):
            head = [
                move.name or '/',
                self._poliza_date(move.date),
                move.journal_id.display_name,
                move_types.get(move.move_type, move.move_type),
                states.get(move.state, move.state),
                move.ref or '',
                move.partner_id.display_name or '',
                (move.l10n_mx_edi_cfdi_uuid or '') if has_uuid else '',
            ]
            return ([move.company_id.name] if multi_company else []) + head

        head_cols = ([('Empresa', 22, 'text')] if multi_company else []) + [
            ('Póliza', 18, 'text'),
            ('Fecha', 11, 'date'),
            ('Diario', 22, 'text'),
            ('Tipo', 16, 'text'),
            ('Estado', 11, 'text'),
            ('Referencia', 22, 'text'),
            ('Contacto', 30, 'text'),
            ('UUID', 38, 'text'),
        ]
        offset = len(head_cols)

        # --- Hoja Apuntes -------------------------------------------------
        line_cols = head_cols + [
            ('Cuenta', 12, 'text'),
            ('Nombre de la cuenta', 32, 'text'),
            ('Concepto', 40, 'text'),
            ('Contacto apunte', 30, 'text'),
            ('Analítica', 30, 'text'),
            ('Moneda', 8, 'text'),
            ('Importe M.E.', 14, 'money'),
            ('T.C.', 10, 'rate'),
            ('Debe', 15, 'money'),
            ('Haber', 15, 'money'),
            ('Saldo', 15, 'money'),
        ]
        line_rows = []
        for move in moves:
            head = move_head(move)
            company_ccy = move.company_id.currency_id
            for line in lines_by_move[move]:
                foreign = line.currency_id and line.currency_id != company_ccy
                rate = abs(line.balance / line.amount_currency) if foreign and line.amount_currency else None
                line_rows.append(head + [
                    line.account_id.code or '',
                    line.account_id.name or '',
                    line.name or '',
                    line.partner_id.display_name or '',
                    self._poliza_analytic_text(line.analytic_distribution, analytic_names),
                    (line.currency_id or company_ccy).name,
                    line.amount_currency if foreign else None,
                    rate,
                    line.debit,
                    line.credit,
                    line.balance,
                ])
        sheet = workbook.add_worksheet('Apuntes')
        self._poliza_write_table(sheet, line_cols, line_rows, formats,
                                 totals=(offset + 8, offset + 9, offset + 10))

        # --- Hoja Pólizas -------------------------------------------------
        move_cols = head_cols + [
            ('Moneda', 8, 'text'),
            ('Concepto', 45, 'wrap'),
            ('Núm. apuntes', 9, 'int'),
            ('Debe', 15, 'money'),
            ('Haber', 15, 'money'),
            ('Diferencia', 14, 'money'),
        ]
        move_rows = []
        for move in moves:
            lines = lines_by_move[move]
            debit = sum(lines.mapped('debit'))
            credit = sum(lines.mapped('credit'))
            diff = move.company_id.currency_id.round(debit - credit)
            values = move_head(move) + [
                move.currency_id.name or '',
                html2plaintext(move.narration).strip() if move.narration else '',
                len(lines),
                debit,
                credit,
                diff,
            ]
            move_rows.append((values, {offset + 5: 'money_red'} if diff else {}))
        sheet = workbook.add_worksheet('Pólizas')
        self._poliza_write_table(sheet, move_cols, move_rows, formats,
                                 totals=(offset + 3, offset + 4, offset + 5))
