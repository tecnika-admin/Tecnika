# -*- coding: utf-8 -*-

import base64
import io
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError

# Optional: Import xlsxwriter if generating XLSX directly here
# import xlsxwriter
# If using ir.actions.report with report_type='xlsx', xlsxwriter is typically
# handled by the AbstractModel defined for the report.


class CommissionReportWizard(models.TransientModel):
    """
    Wizard model for generating the custom commission report.
    Users select date ranges for invoices and payments.
    """
    _name = 'commission.report.wizard'
    _description = 'Wizard for Custom Commission Report'

    # === Fields ===
    date_invoice_from = fields.Date(
        string="Fecha Factura Desde",
        required=True,
        help="Consider invoices with invoice date from this date."
    )
    date_invoice_to = fields.Date(
        string="Fecha Factura Hasta",
        required=True,
        help="Consider invoices with invoice date up to this date."
    )
    date_payment_from = fields.Date(
        string="Fecha Pago Desde",
        required=True,
        help="Consider payments registered from this date."
    )
    date_payment_to = fields.Date(
        string="Fecha Pago Hasta",
        required=True,
        help="Consider payments registered up to this date."
    )

    # === Actions ===
    def action_generate_report(self):
        """
        Called when the 'Generate Report' button is clicked.
        Validates dates and triggers the report generation (XLSX action).
        """
        self.ensure_one()

        # Basic date validation
        if self.date_invoice_from > self.date_invoice_to:
            raise UserError(_("La 'Fecha Factura Desde' no puede ser posterior a la 'Fecha Factura Hasta'."))
        if self.date_payment_from > self.date_payment_to:
            raise UserError(_("La 'Fecha Pago Desde' no puede ser posterior a la 'Fecha Pago Hasta'."))

        # Prepare data for the report action
        # The 'data' dictionary will be passed to the report template/AbstractModel
        data = {
            'wizard_id': self.id,
            'date_invoice_from': self.date_invoice_from.strftime('%Y-%m-%d'),
            'date_invoice_to': self.date_invoice_to.strftime('%Y-%m-%d'),
            'date_payment_from': self.date_payment_from.strftime('%Y-%m-%d'),
            'date_payment_to': self.date_payment_to.strftime('%Y-%m-%d'),
        }

        # Return the action defined in report/report_action.xml
        # Odoo will call the corresponding AbstractModel to generate the XLSX
        return self.env.ref('custom_commission_report.action_report_commission_xlsx').report_action(self, data=data)

    def get_report_filename(self):
        """
        Method called by the report action to determine the default filename.
        """
        self.ensure_one()
        current_date = fields.Date.today().strftime('%y%m%d') # Format AAMMDD
        return f"reporte_comisiones_{current_date}.xlsx"

    def _get_report_data(self):
        """
        Fetches the data using the direct SQL query.
        This method will be called by the report generation logic (AbstractModel).
        """
        self.ensure_one()

        # The SQL query from the requirement document
        # IMPORTANT: Use placeholders like %(param_name)s for security!
        query = """
            SELECT
                DISTINCT (ap.id) as payment_id, -- Added distinct payment ID for potential grouping if needed later
                aml.id as move_line_id,
                am."name" AS "Factura",
                am.invoice_date AS "fecha factura",
                am2."date" AS "Fecha Pago",
                am2."date" - am.invoice_date as "Días dif",
                rp2."name" AS "Vendedor",
                rp."name" AS "Cliente",
                am.invoice_date_due AS "Fecha vencimiento",
                aml."name" AS "Producto",
                aml.quantity AS "Cantidad",
                ((am.amount_total_signed / NULLIF(am.amount_total_in_currency_signed, 0)) * aml.price_unit) AS "Precio unitario en MXN",
                aml2.debit AS "Costo de venta",
                am.amount_untaxed_signed AS "Subtotal Factura MXN",
                (aml.quantity * ((am.amount_total_signed / NULLIF(am.amount_total_in_currency_signed, 0)) * aml.price_unit)) - COALESCE(aml2.debit, 0) AS "Margen en MXN",
                rc."name" AS "Divisa",
                (am.amount_total_signed / NULLIF(am.amount_total_in_currency_signed, 0)) AS "TC",
                am.amount_untaxed AS "Subtotal Factura",
                am.amount_total_signed AS "Total MXN",
                am.amount_residual_signed AS "Saldo pendiente MXN",
                (am.amount_total_signed - am.amount_residual_signed) AS "Abonado_MXN",
                ap.amount AS "Monto pagado",
                am2."date" AS "Fecha de pago_dup", -- Renamed duplicate column
                (am2."date" - am.invoice_date) AS "Aplica_comision"
            FROM account_payment ap
            INNER JOIN account_move am2 ON (am2.id = ap.move_id)
            INNER JOIN account_move_line aml_pago ON (aml_pago.move_id = am2.id AND aml_pago.account_id IN (3, 393)) -- IDs de cuenta de pago/banco (ajustar si es necesario)
            INNER JOIN account_move_line aml_factura ON (aml_factura.matching_number = aml_pago.matching_number AND aml_factura.account_id IN (3, 393)) -- IDs de cuenta por cobrar cliente (ajustar si es necesario)
            INNER JOIN account_move am ON (am.id = aml_factura.move_id)
            INNER JOIN account_move_line aml ON (aml.move_id = am.id AND aml.display_type = 'product') -- Ensure we only get product lines
            INNER JOIN product_product pp ON (aml.product_id = pp.id)
            INNER JOIN product_template pt ON (pp.product_tmpl_id = pt.id)
            INNER JOIN res_partner rp ON (rp.id = am.partner_id)
            INNER JOIN res_users ru ON (ru.id = am.invoice_user_id)
            INNER JOIN res_partner rp2 ON (rp2.id = ru.partner_id)
            INNER JOIN res_currency rc ON (am.currency_id = rc.id)
            LEFT JOIN (
                SELECT aml3.move_id, aml3.debit, aml3.product_id
                FROM account_move_line aml3
                WHERE aml3.account_id = 33 -- ID de cuenta de costo de venta (ajustar si es necesario)
            ) aml2 ON (aml2.move_id = am.id AND aml2.product_id = aml.product_id)
            WHERE
                am2."date" BETWEEN %(date_payment_from)s AND %(date_payment_to)s
            AND am.invoice_date BETWEEN %(date_invoice_from)s AND %(date_invoice_to)s
            AND (am2."date" - am.invoice_date) < 60
            AND am.move_type = 'out_invoice'
            AND aml.account_id IN (552, 553) -- IDs de cuenta de Ingresos (ajustar si es necesario)
            AND am.state = 'posted'
            ORDER BY am."name", aml.id;
        """

        # Prepare parameters safely
        params = {
            'date_payment_from': self.date_payment_from,
            'date_payment_to': self.date_payment_to,
            'date_invoice_from': self.date_invoice_from,
            'date_invoice_to': self.date_invoice_to,
        }

        # Execute the query
        self.env.cr.execute(query, params)
        results = self.env.cr.dictfetchall()

        # Add NULLIF and COALESCE in SQL for safety
        # Added NULLIF for division by zero protection on TC calculation
        # Added COALESCE for Costo de venta in Margen calculation if cost is NULL
        # Added aml.display_type = 'product' to ensure we only process actual product lines
        # Added aml.id to SELECT and ORDER BY to ensure consistent ordering for lines within the same invoice

        if not results:
            raise UserError(_("No se encontraron datos para los criterios seleccionados."))

        return results

