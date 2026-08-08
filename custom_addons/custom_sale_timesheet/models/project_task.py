# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    custom_portal_progress = fields.Float(
        compute='_compute_custom_portal_progress',
        aggregator='avg',
        help="Progreso de la tarea para el portal del cliente. "
             "Calculado sin filtrar por project_id en las líneas analíticas.",
        export_string_translation=False,
    )
    custom_portal_total_hours_spent = fields.Float(
        compute='_compute_custom_portal_progress',
        help="Horas totales registradas (tarea + subtareas) para el portal del cliente.",
        export_string_translation=False,
    )

    @property
    def TASK_PORTAL_READABLE_FIELDS(self):
        return super().TASK_PORTAL_READABLE_FIELDS | {'custom_portal_progress', 'custom_portal_total_hours_spent'}

    @api.depends('allocated_hours', 'timesheet_ids.unit_amount', 'timesheet_ids.validated')
    def _compute_custom_portal_progress(self):
        subtask_ids_per_task_id = self.sudo().with_context(active_test=False)._get_subtask_ids_per_task_id()
        all_task_ids = set.union(set(), *subtask_ids_per_task_id.values(), self.ids)

        # Se omite el filtro ('project_id', '!=', False) presente en portal_progress
        # para soportar cuentas analíticas compartidas entre proyectos.
        param = self.env['ir.config_parameter'].sudo().get_param('sale.invoiced_timesheet', 'all')
        domain = [('task_id', 'in', list(all_task_ids))]
        if param == 'approved':
            domain.append(('validated', '=', True))

        timesheet_read_group = self.env['account.analytic.line'].sudo()._read_group(
            domain,
            ['task_id'],
            ['unit_amount:sum'],
        )
        timesheets_per_task = {task.id: unit_amount_sum for task, unit_amount_sum in timesheet_read_group}

        for task in self:
            effective_hours = timesheets_per_task.get(task.id, 0.0)
            subtask_effective_hours = sum(
                timesheets_per_task.get(subtask_id, 0.0)
                for subtask_id in subtask_ids_per_task_id.get(task.id, [])
            )
            total_hours_spent = effective_hours + subtask_effective_hours
            progress = 0.0
            if task.allocated_hours > 0:
                progress = 1.0 if max(total_hours_spent - task.allocated_hours, 0) else round(total_hours_spent / task.allocated_hours, 2)
            task.custom_portal_progress = progress
            task.custom_portal_total_hours_spent = total_hours_spent
