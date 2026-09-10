# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'tecnika.report.document']

    def _get_name_invoice_report(self):
        """Route every customer invoice/refund to the CFDI body template.

        The standard l10n_mx_edi only uses ``l10n_mx_edi.report_invoice_document``
        once the invoice is stamped (``cfdi_state == 'sent'``); before that it
        falls back to the generic layout.  Since this DB is a single Mexican
        company and the custom design must apply *always* (drafts included, with
        the CFDI blocks degrading gracefully), we force that template whenever it
        is a customer document.  Our QWeb override then replaces its body.
        """
        self.ensure_one()
        if self.move_type in ('out_invoice', 'out_refund'):
            return 'l10n_mx_edi.report_invoice_document'
        return super()._get_name_invoice_report()

    # -------------------------------------------------------------------------
    # tecnika.report.document hooks
    # -------------------------------------------------------------------------

    def _tecnika_line_ids(self):
        """Invoice lines are already limited to product/section/note."""
        return self.invoice_line_ids

    def _tecnika_amount_words(self):
        """Use the native field: l10n_mx_edi already computes the CFDI wording."""
        self.ensure_one()
        return self.amount_total_words or ''

    def _tecnika_tax_summary(self):
        """Split tax lines into traslados (positive) and retenciones (negative).

        Returns the transferred IVA and the withheld IVA used by the totals box.
        """
        self.ensure_one()
        traslado = retenido = 0.0
        for line in self.line_ids:
            tax = line.tax_line_id
            if not tax:
                continue
            amount = abs(line.amount_currency) or abs(line.balance)
            if tax.amount < 0:
                retenido += amount
            else:
                traslado += amount
        return {'traslado': traslado, 'retenido': retenido}

    # -------------------------------------------------------------------------
    # CFDI custom report helpers
    #
    # The heavy lifting (sello, sello SAT, cadena original via the official
    # XSLT, certificate numbers, stamp date, fiscal folio and the SAT
    # verification QR) is already provided natively by l10n_mx_edi through
    # ``_l10n_mx_edi_get_extra_invoice_report_values``.  We only wrap it so the
    # template stays clean and never breaks on drafts / un-stamped invoices.
    # -------------------------------------------------------------------------

    def _cfdi_get_render_data(self):
        """Collect every value the custom CFDI PDF needs in a single dict.

        Robust by design: a draft (no stamp yet) simply yields empty CFDI
        fields instead of raising.
        """
        self.ensure_one()

        try:
            cfdi = self._l10n_mx_edi_get_extra_invoice_report_values() or {}
        except Exception:  # noqa: BLE001 - never let the report crash
            cfdi = {}

        # Comprobante version (the only node attribute the layout still needs;
        # TipoCambio / Exportacion were dropped from the PDF design).
        node = cfdi.get('cfdi_node')
        version = '4.0'
        if node is not None:
            version = node.get('Version') or version

        data = {
            'cfdi': cfdi,
            'version': version,
            'usage_display': self._cfdi_usage_display(cfdi),
            'payment_policy': self.l10n_mx_edi_payment_policy or '',
            'payment_way': self._cfdi_payment_way_display(cfdi),
            'credit_days': self._cfdi_credit_days(),
            'emission_time': self._cfdi_emission_time(cfdi),
            'taxes': self._tecnika_tax_summary(),
            'bank_accounts': self._tecnika_bank_accounts(),
            'amount_words': self._tecnika_amount_words(),
        }
        data.update(self._tecnika_branding())
        return data

    def _cfdi_usage_display(self, cfdi):
        """Uso CFDI as ``CODE - Label`` (label honours the active language)."""
        code = cfdi.get('usage') or self.l10n_mx_edi_usage or ''
        label = cfdi.get('usage_desc')
        if not label and code:
            label = dict(
                self._fields['l10n_mx_edi_usage']._description_selection(self.env)
            ).get(code, '')
        return ' - '.join(part for part in (code, label) if part)

    def _cfdi_payment_way_display(self, cfdi):
        """Forma de pago as ``CODE - Name`` (e.g. ``99 - Por definir``)."""
        if cfdi.get('payment_way'):
            return cfdi['payment_way']
        method = self.l10n_mx_edi_payment_method_id
        if method:
            return ' - '.join(part for part in (method.code, method.name) if part)
        return ''

    def _cfdi_emission_time(self, cfdi):
        """Emission clock time (``hh:mm:ss``) of the CFDI.

        Prefers the ``Fecha`` attribute of the stamped CFDI node (already in
        local time). Falls back to the stored post time converted to the user
        timezone, so drafts/un-stamped invoices still show a sensible value.
        """
        self.ensure_one()
        node = cfdi.get('cfdi_node')
        if node is not None:
            fecha = node.get('Fecha') or ''
            if 'T' in fecha:
                return fecha.split('T', 1)[1][:8]
        if self.l10n_mx_edi_post_time:
            local_dt = fields.Datetime.context_timestamp(self, self.l10n_mx_edi_post_time)
            return local_dt.strftime('%H:%M:%S')
        return ''

    def _cfdi_credit_days(self):
        """Días de crédito: prefer the actual date span, fall back to the term."""
        if self.invoice_date and self.invoice_date_due:
            return (self.invoice_date_due - self.invoice_date).days
        return self.invoice_payment_term_id.name or ''

    def _cfdi_line_series(self, line):
        """Serial / lot numbers tied to an invoice line via the sale-stock chain.

        Returns ``[]`` when traceability isn't installed or available, so the
        block is simply skipped instead of breaking the render.
        """
        try:
            lots = line.sale_line_ids.move_ids.move_line_ids.lot_id
            return [name for name in lots.mapped('name') if name]
        except Exception:  # noqa: BLE001 - traceability is optional
            return []
