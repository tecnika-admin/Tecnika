# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'tecnika.report.document']

    # -------------------------------------------------------------------------
    # tecnika.report.document hooks
    # -------------------------------------------------------------------------

    def _tecnika_line_ids(self):
        """Every order line; the mixin sorts out products / sections / notes."""
        return self.order_line

    def _tecnika_tax_summary(self):
        """Split the order taxes into traslados and retenciones.

        A sale order has no tax lines to read (unlike ``account.move``), so the
        amounts are recomputed with the same engine ``_compute_amounts`` uses.
        Retenciones are the taxes with a negative rate, shown as a positive
        figure in the totals box.
        """
        self.ensure_one()
        AccountTax = self.env['account.tax']
        base_lines = [
            line._prepare_base_line_for_taxes_computation()
            for line in self._get_priced_lines()
        ]
        AccountTax._add_tax_details_in_base_lines(base_lines, self.company_id)
        AccountTax._round_base_lines_tax_details(base_lines, self.company_id)

        traslado = retenido = 0.0
        for base_line in base_lines:
            for tax_data in base_line['tax_details']['taxes_data']:
                amount = tax_data['tax_amount_currency']
                if tax_data['tax'].amount < 0:
                    retenido += abs(amount)
                else:
                    traslado += amount
        return {'traslado': traslado, 'retenido': retenido}

    # -------------------------------------------------------------------------
    # Report helpers
    # -------------------------------------------------------------------------

    def _tecnika_sale_render_data(self):
        """Everything the quotation PDF needs, in one dict.

        Deliberately mirrors ``account.move._cfdi_get_render_data()`` so both
        templates read the same way; the CFDI-only keys (sellos, QR, folio
        fiscal) simply have no counterpart here.
        """
        self.ensure_one()
        data = {
            'is_quotation': self.state in ('draft', 'sent'),
            'doc_title': 'Cotización' if self.state in ('draft', 'sent') else 'Pedido',
            'order_date': self._tecnika_order_date(),
            'order_time': self._tecnika_order_time(),
            'usage_display': self._tecnika_usage_display(),
            'payment_policy': self.l10n_mx_edi_payment_policy or '',
            'payment_way': self._tecnika_payment_way_display(),
            'credit_days': self._tecnika_credit_days(),
            'taxes': self._tecnika_tax_summary(),
            'amount_words': self._tecnika_amount_words(),
        }
        data.update(self._tecnika_branding())
        return data

    def _tecnika_order_datetime(self):
        """``date_order`` in the user timezone (it is stored in UTC)."""
        self.ensure_one()
        if not self.date_order:
            return None
        return fields.Datetime.context_timestamp(self, self.date_order)

    def _tecnika_order_date(self):
        local_dt = self._tecnika_order_datetime()
        return local_dt.strftime('%d/%m/%Y') if local_dt else ''

    def _tecnika_order_time(self):
        local_dt = self._tecnika_order_datetime()
        return local_dt.strftime('%H:%M:%S') if local_dt else ''

    def _tecnika_usage_display(self):
        """Uso CFDI as ``CODE - Label``, same wording as the invoice."""
        code = self.l10n_mx_edi_usage or ''
        if not code:
            return ''
        label = dict(
            self._fields['l10n_mx_edi_usage']._description_selection(self.env)
        ).get(code, '')
        return ' - '.join(part for part in (code, label) if part)

    def _tecnika_payment_way_display(self):
        """Forma de pago as ``CODE - Name`` (e.g. ``99 - Por definir``)."""
        method = self.l10n_mx_edi_payment_method_id
        if method:
            return ' - '.join(part for part in (method.code, method.name) if part)
        return ''

    def _tecnika_credit_days(self):
        """Días de crédito taken from the payment term, if any."""
        return self.payment_term_id.name or ''

    def _tecnika_line_series(self, line):
        """Serial numbers reserved for the line, when the pickings already exist.

        A quotation normally has none (stock moves are created on confirmation),
        so this degrades to an empty list and the block is skipped.
        """
        try:
            lots = line.move_ids.move_line_ids.lot_id
            return [name for name in lots.mapped('name') if name]
        except Exception:  # noqa: BLE001 - traceability is optional
            return []
