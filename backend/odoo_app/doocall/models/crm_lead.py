# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    doocall_call_ids = fields.One2many(
        "doocall.call", "lead_id", string="DooCall qo'ng'iroqlari"
    )
    doocall_call_count = fields.Integer(compute="_compute_doocall_call_count")

    @api.depends("doocall_call_ids")
    def _compute_doocall_call_count(self):
        counts = dict(
            self.env["doocall.call"]._read_group(
                [("lead_id", "in", self.ids)], ["lead_id"], ["__count"]
            )
        )
        for lead in self:
            lead.doocall_call_count = counts.get(lead, 0)

    def action_view_doocall_calls(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "DooCall qo'ng'iroqlari",
            "res_model": "doocall.call",
            "view_mode": "list,form",
            "domain": [("lead_id", "=", self.id)],
            "context": {"default_lead_id": self.id},
        }
