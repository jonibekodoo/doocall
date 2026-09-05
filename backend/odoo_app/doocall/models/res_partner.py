# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    doocall_call_ids = fields.One2many(
        "doocall.call", "partner_id", string="DooCall qo'ng'iroqlari"
    )
    doocall_call_count = fields.Integer(compute="_compute_doocall_call_count")

    @api.depends("doocall_call_ids")
    def _compute_doocall_call_count(self):
        counts = dict(
            self.env["doocall.call"]._read_group(
                [("partner_id", "in", self.ids)], ["partner_id"], ["__count"]
            )
        )
        for partner in self:
            partner.doocall_call_count = counts.get(partner, 0)

    def action_view_doocall_calls(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "DooCall qo'ng'iroqlari",
            "res_model": "doocall.call",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }
