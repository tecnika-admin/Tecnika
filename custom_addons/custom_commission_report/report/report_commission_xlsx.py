# -*- coding: utf-8 -*-

import io
import logging
from odoo import models, _
# Ensure xlsxwriter is installed in the Odoo environment
try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None
    # You might want to log a warning or raise an error if xlsxwriter is critical
    _logger = logging.getLogger(__name__)
    _logger.warning("The xlsxwriter library is not installed. XLSX report generation will fail.")


class CommissionReportXLSX(models.AbstractModel):
    """
    AbstractModel to generate the XLSX report based on the data
    fetched by the wizard.
    """
    # The name must match 'report.' + report_name defined in the report action XML
    _name = 'report.custom_commission_report.report_commission_xlsx_template'
    _description = 'Commission Report XLSX Generator'
    # Inherit from 'report.report_xlsx.abstract' for standard XLSX report structure
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, wizards):
        """
        Main method called by Odoo's reporting engine to generate the XLSX.

        :param workbook: xlsxwriter workbook object
        :param data: Dictionary passed from the wizard action
        :param wizards: Recordset of the wizard model (commission.report.wizard)
        """
        if not xlsxwriter:
             raise models.UserError(_("The 'xlsxwriter' library is required to generate XLSX reports. Please install it."))

        # Ensure we have wizard data
        if not wizards:
             # This case might happen if called directly without context
             # You might want to log or handle this appropriately
             return

        # We expect only one wizard record
        wizard = wizards[0]

        # Fetch the report data using the wizard's method
        report_data = wizard._get_report_data() # Call the method defined in the wizard

        # Create the worksheet
        sheet = workbook.add_worksheet('Comisiones')

        # Define formats (optional, but improves readability)
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#D3D3D3', # Light grey background
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True,
        })
        cell_format = workbook.add_format({'border': 1, 'valign': 'vcenter'})
        date_format = workbook.add_format({'num_format': 'yyyy-mm-dd', 'border': 1, 'valign': 'vcenter'})
        currency_format = workbook.add_format({'num_format': '#,##0.00', 'border': 1, 'valign': 'vcenter'})
        number_format = workbook.add_format({'num_format': '#,##0.00', 'border': 1, 'valign': 'vcenter'}) # General number format
        integer_format = workbook.add_format({'num_format': '0', 'border': 1, 'valign': 'vcenter', 'align': 'center'})

        # Define Headers based on the SQL query aliases
        # Ensure the order matches the desired column order in the report
        headers = [
            "Factura", "fecha factura", "Fecha Pago", "Días dif", "Vendedor", "Cliente",
            "Fecha vencimiento", "Producto", "Cantidad", "Precio unitario en MXN",
            "Costo de venta", "Subtotal Factura MXN", "Margen en MXN", "Divisa", "TC", 
            "Subtotal Factura", "Total MXN", "Saldo pendiente MXN", "Abonado_MXN",
            "Monto pagado", #"Fecha de pago_dup", # Exclude duplicate date column
            #"Aplica_comision" # This seems redundant with "Días dif"
        ]

        # Write Headers
        for col_num, header in enumerate(headers):
            sheet.write(0, col_num, header, header_format)
            # Set column width (optional)
            if header in ["Producto", "Cliente", "Vendedor"]:
                 sheet.set_column(col_num, col_num, 30) # Wider columns for text
            elif header in ["fecha factura", "Fecha Pago", "Fecha vencimiento"]:
                 sheet.set_column(col_num, col_num, 12)
            else:
                 sheet.set_column(col_num, col_num, 15) # Default width

        # Write Data Rows
        row_num = 1
        for row_data in report_data:
            col_num = 0
            for header in headers:
                # Get the value from the dictionary returned by dictfetchall()
                # The keys in row_data should match the aliases in the SQL query
                value = row_data.get(header) # Use .get() for safety if a column might be missing

                # Apply specific formats based on header/data type
                if header in ["fecha factura", "Fecha Pago", "Fecha vencimiento"]:
                    sheet.write_datetime(row_num, col_num, value, date_format)
                elif header in ["Cantidad"]:
                     # Assuming quantity might not always be an integer
                     sheet.write_number(row_num, col_num, value or 0, number_format)
                elif header in ["Días dif"]:
                     sheet.write_number(row_num, col_num, value or 0, integer_format)
                elif header in ["Precio unitario en MXN", "Costo de venta", "Margen en MXN",
                                "TC", "Subtotal Factura", "Subtotal Factura MXN",
                                "Total MXN", "Saldo pendiente MXN", "Abonado_MXN", "Monto pagado"]:
                    sheet.write_number(row_num, col_num, value or 0.0, currency_format)
                else:
                    # Default format for text or other types
                    sheet.write(row_num, col_num, value, cell_format)
                col_num += 1
            row_num += 1

        # Freeze header row (optional)
        sheet.freeze_panes(1, 0)

