# -*- coding: utf-8 -*-
from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _l10n_mx_edi_get_payment_issued_address(self, pay_results):
        """Issued address for the payment CFDI (complemento de pago).

        Priority:

        1. The ``Address Issued`` of the payment journal (bank / cash).
        2. The ``Address Issued`` of the paid invoices' journals, only when
           every invoice shares the same one.

        An empty recordset means keeping the company address (native behaviour).
        """
        self.ensure_one()
        if self.journal_id.l10n_mx_address_issued_id:
            return self.journal_id.l10n_mx_address_issued_id

        addresses = [
            invoice_values['invoice'].journal_id.l10n_mx_address_issued_id
            for invoice_values in pay_results['invoice_results']
        ]
        if addresses and addresses[0] and all(address == addresses[0] for address in addresses):
            return addresses[0]
        return self.env['res.partner']

    def _l10n_mx_edi_add_payment_cfdi_values(self, cfdi_values, pay_results):
        # EXTENDS 'l10n_mx_edi'
        # Must be set before super(): 'lugar_expedicion' and 'fecha' are read
        # from cfdi_values['issued_address'] there.
        self.ensure_one()
        issued_address = self._l10n_mx_edi_get_payment_issued_address(pay_results)
        if issued_address:
            cfdi_values['issued_address'] = issued_address
        return super()._l10n_mx_edi_add_payment_cfdi_values(cfdi_values, pay_results)
