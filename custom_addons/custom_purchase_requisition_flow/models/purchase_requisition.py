# -*- coding: utf-8 -*-

from odoo import models, fields, api # Añadir api

class PurchaseRequisition(models.Model):
    """Hereda de purchase.requisition para añadir campos personalizados y lógica."""
    _inherit = 'purchase.requisition'

    # Campo Many2many para relacionar facturas de venta
    invoice_ids = fields.Many2many(
        comodel_name='account.move',
        string="Facturas de Venta Relacionadas",
        domain=[('move_type', '=', 'out_invoice'), ('state', '=', 'posted')],
        help="Facturas de venta asociadas a este acuerdo de compra. Use 'Añadir' para seleccionar facturas existentes."
    )

    # Sobrescribir el método write para forzar el recálculo de qty_cli en las líneas
    def write(self, vals):
        """
        Sobrescribe write para detectar cambios en invoice_ids y forzar
        el recálculo de qty_cli en las líneas de la requisición.
        """
        # Ejecutar primero el write original
        res = super(PurchaseRequisition, self).write(vals)

        # Verificar si 'invoice_ids' está entre los campos modificados
        if 'invoice_ids' in vals:
            # Iterar sobre las requisiciones modificadas (normalmente será una desde la UI)
            for requisition in self:
                # Si tiene líneas, invalidar el campo qty_cli para forzar recálculo
                if requisition.line_ids:
                    # Invalidate_recordset limpia la caché para estos campos,
                    # forzando a @api.depends a recalcular la próxima vez que se necesiten.
                    requisition.line_ids.invalidate_recordset(['qty_cli'])
                    # Nota: Esto indirectamente también forzará el recálculo de
                    # qty_almtec y qty_fab porque dependen de qty_cli.

        return res

    # (Opcional pero recomendado) Sobrescribir create por si se añaden facturas al crear
    @api.model_create_multi
    def create(self, vals_list):
        """Sobrescribe create para forzar recálculo si se añaden facturas."""
        requisitions = super(PurchaseRequisition, self).create(vals_list)
        for requisition in requisitions:
            # Verificar si se pasaron invoice_ids en la creación
            # (Aunque desde la UI estándar no se suele poder, es buena práctica)
            if any(vals.get('invoice_ids') for vals in vals_list if vals.get('name') == requisition.name): # Chequeo simple
                 if requisition.line_ids:
                    requisition.line_ids.invalidate_recordset(['qty_cli'])
        return requisitions

