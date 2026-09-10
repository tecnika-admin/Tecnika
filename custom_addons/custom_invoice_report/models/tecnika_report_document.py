# -*- coding: utf-8 -*-
import base64
import functools

from odoo import models
from odoo.tools import file_open
from odoo.tools.image import image_data_uri


class TecnikaReportDocument(models.AbstractModel):
    """Building blocks shared by every Tecnika printed document.

    The CFDI invoice and the sale quotation render the same visual design
    (branding header, Emisor/Receptor boxes, concepts table, totals strip).
    Everything that does not depend on the concrete model lives here so both
    reports stay in sync; what genuinely differs is left as a hook.

    Mixed into a model with ``_inherit = ['<model>', 'tecnika.report.document']``.
    """

    _name = 'tecnika.report.document'
    _description = 'Tecnika printed document helpers'

    # -------------------------------------------------------------------------
    # Hooks - each concrete model must provide these.
    # -------------------------------------------------------------------------

    def _tecnika_line_ids(self):
        """Recordset of printable lines, in document order."""
        raise NotImplementedError

    def _tecnika_tax_summary(self):
        """``{'traslado': float, 'retenido': float}`` for the totals box."""
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Branding
    # -------------------------------------------------------------------------

    @staticmethod
    @functools.lru_cache(maxsize=8)
    def _tecnika_static_image(filename):
        """Base64 data URI for an image bundled in ``static/src/img``.

        wkhtmltopdf does not reliably fetch ``/module/static`` URLs while
        rendering a PDF, so the branding is embedded inline instead of linked.
        Cached because the bytes never change at runtime (``--dev=reload``
        clears it on a code change).
        """
        with file_open(
            'custom_invoice_report/static/src/img/%s' % filename, 'rb'
        ) as handle:
            return image_data_uri(base64.b64encode(handle.read()))

    @staticmethod
    @functools.lru_cache(maxsize=4)
    def _tecnika_static_svg(filename):
        """Base64 data URI for SVG assets used in the PDF."""
        with file_open(
            'custom_invoice_report/static/src/img/%s' % filename, 'rb'
        ) as handle:
            payload = base64.b64encode(handle.read()).decode()
        return 'data:image/svg+xml;base64,%s' % payload

    # -------------------------------------------------------------------------
    # Shared content
    # -------------------------------------------------------------------------

    def _tecnika_report_lines(self):
        """Ordered rows for the concepts table: products, sections and notes.

        Sections and notes keep their original position so the print matches
        the form; only product lines consume a ``partida`` number.

        ``display_type`` is normalised on purpose: a product line is
        ``'product'`` on ``account.move.line`` but ``False`` on
        ``sale.order.line``, so both are folded into ``'product'`` here.
        """
        self.ensure_one()
        rows = []
        partida = 0
        for line in self._tecnika_line_ids():
            display = line.display_type or 'product'
            if display == 'product':
                partida += 1
                rows.append({'type': 'product', 'partida': partida, 'line': line})
            elif display in ('line_section', 'line_note'):
                rows.append({'type': display, 'line': line})
        return rows

    def _tecnika_bank_accounts(self):
        """CLABEs of the issuing company (bank code + name).

        Only the accounts whose currency matches the document currency are
        returned: a USD document shows USD accounts and an MXN one shows MXN
        accounts. Accounts without an explicit currency are treated as
        company-currency accounts.
        """
        self.ensure_one()
        company_currency = self.company_id.currency_id
        return [
            {
                'code': bank.l10n_mx_edi_clabe or '',
                'bank': bank.bank_id.name or '',
            }
            for bank in self.company_id.partner_id.bank_ids
            if (bank.currency_id or company_currency) == self.currency_id
        ]

    def _tecnika_amount_words(self):
        """Document total spelled out in the Mexican printed-document format.

        Mirrors ``l10n_mx_edi``'s ``_l10n_mx_edi_cfdi_amount_to_text`` (which
        only exists on ``account.move``) so a quotation reads exactly like the
        invoice it will become: ``MIL PESOS 00/100 M.N``.
        """
        self.ensure_one()
        currency_name = (self.currency_id.name or '').upper()
        # M.N. = Moneda Nacional, M.E. = Moneda Extranjera.
        currency_type = 'M.N' if currency_name == 'MXN' else 'M.E.'
        amount_i, amount_d = divmod(self.amount_total, 1)
        cents = int(round(round(amount_d, 2) * 100, 2))
        words = self.currency_id.with_context(
            lang=self.partner_id.lang
        ).amount_to_text(amount_i).upper()
        return '%s %02d/100 %s' % (words, cents, currency_type)

    def _tecnika_branding(self):
        """Logo and watermark data URIs used by the shared header."""
        return {
            'logo_src': self._tecnika_static_image('header_icon.png'),
            'watermark_src': self._tecnika_static_svg('watermark.svg'),
        }
