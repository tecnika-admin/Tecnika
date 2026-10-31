# -*- coding: utf-8 -*-
from odoo import api, models


class L10nMxEdiDocument(models.Model):
    _inherit = 'l10n_mx_edi.document'

    @api.model
    def _get_datetime_now_with_mx_timezone(self, cfdi_values, journal=None):
        # EXTENDS 'l10n_mx_edi'
        # The invoice post time is computed with the company address
        # (account_move._l10n_mx_edi_cfdi_invoice_try_send), so an invoice
        # issued from a journal in another time zone would get a 'Fecha' in
        # the company's local time. Use the journal's issued address instead;
        # the native 'l10n_mx_edi_tz_<journal id>' parameter still wins in super().
        if journal and len(journal) == 1 and journal.l10n_mx_address_issued_id:
            cfdi_values = {**cfdi_values, 'issued_address': journal.l10n_mx_address_issued_id}
        return super()._get_datetime_now_with_mx_timezone(cfdi_values, journal=journal)
