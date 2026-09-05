# -*- coding: utf-8 -*-
"""DooCall qo'ng'irog'i: kontakt/lid bilan avtomatik bog'lanadi, chatter'ga
yozuv tushiradi, kartochkasida audio player ko'rsatadi."""

from markupsafe import Markup

from odoo import api, fields, models


class DoocallCall(models.Model):
    _name = "doocall.call"
    _description = "DooCall qo'ng'irog'i"
    _order = "start_time desc, id desc"
    _rec_name = "display_label"

    call_id = fields.Char(string="Call ID", index=True)
    server_id = fields.Char(string="Server ID", index=True, copy=False)
    direction = fields.Selection(
        [("inbound", "Kiruvchi"), ("outbound", "Chiquvchi")],
        string="Yo'nalish",
        required=True,
        default="inbound",
    )
    status = fields.Selection(
        [
            ("answered", "Javob berilgan"),
            ("no_answer", "Javobsiz"),
            ("busy", "Band"),
            ("failed", "Xato"),
        ],
        string="Holat",
        required=True,
        default="answered",
    )
    phone = fields.Char(string="Telefon", index=True)
    operator = fields.Char(string="Operator")
    duration = fields.Integer(string="Davomiylik (soniya)")
    duration_display = fields.Char(
        string="Davomiylik", compute="_compute_duration_display"
    )
    start_time = fields.Datetime(string="Boshlanish vaqti")
    record_url = fields.Char(string="Yozuv havolasi")
    partner_id = fields.Many2one("res.partner", string="Kontakt", index=True)
    lead_id = fields.Many2one("crm.lead", string="Lid", index=True)
    display_label = fields.Char(compute="_compute_display_label")
    player_html = fields.Html(
        string="Audio yozuv", compute="_compute_player_html", sanitize=False
    )

    _sql_constraints = [
        ("server_id_uniq", "unique(server_id)", "Bu qo'ng'iroq allaqachon mavjud."),
    ]

    @api.depends("duration")
    def _compute_duration_display(self):
        for rec in self:
            minutes, seconds = divmod(rec.duration or 0, 60)
            rec.duration_display = "%02d:%02d" % (minutes, seconds)

    @api.depends("direction", "phone")
    def _compute_display_label(self):
        labels = dict(self._fields["direction"].selection)
        for rec in self:
            rec.display_label = "%s · %s" % (
                labels.get(rec.direction, rec.direction),
                rec.phone or "?",
            )

    @api.depends("record_url")
    def _compute_player_html(self):
        for rec in self:
            if rec.record_url:
                rec.player_html = Markup(
                    '<audio controls preload="none" style="width:100%%;max-width:480px"'
                    ' src="%s"></audio>'
                ) % rec.record_url
            else:
                rec.player_html = False

    # ── Avto-bog'lash + chatter ────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            try:
                rec._link_and_notify()
            except Exception:  # bog'lay olmasa ham qo'ng'iroq saqlanib qolsin
                pass
        return records

    def _phone_tail(self):
        digits = "".join(ch for ch in (self.phone or "") if ch.isdigit())
        return digits[-9:] if len(digits) >= 9 else digits

    def _link_and_notify(self):
        self.ensure_one()
        tail = self._phone_tail()
        if tail and not self.partner_id:
            self.partner_id = self.env["res.partner"].search(
                ["|", ("phone", "like", tail), ("mobile", "like", tail)], limit=1
            )
        if not self.partner_id and not self.lead_id:
            lead = False
            if tail:
                lead = self.env["crm.lead"].search(
                    [("phone", "like", tail)], limit=1
                )
            if not lead:
                lead = self.env["crm.lead"].create(
                    {
                        "name": "DooCall: %s" % (self.phone or "?"),
                        "phone": self.phone,
                        "type": "lead",
                    }
                )
            self.lead_id = lead
        body = self._chatter_body()
        for target in (self.partner_id, self.lead_id):
            if target:
                target.message_post(body=body)

    def _chatter_body(self):
        self.ensure_one()
        labels = dict(self._fields["direction"].selection)
        statuses = dict(self._fields["status"].selection)
        body = Markup(
            "<b>DooCall: %s qo'ng'iroq</b><br/>"
            "Raqam: %s<br/>Holat: %s · Davomiylik: %s"
        ) % (
            labels.get(self.direction, self.direction),
            self.phone or "?",
            statuses.get(self.status, self.status),
            self.duration_display,
        )
        if self.operator:
            body += Markup("<br/>Operator: %s") % self.operator
        if self.record_url:
            body += Markup(
                '<br/><a href="%s" target="_blank">&#9654; Yozuvni tinglash</a>'
            ) % self.record_url
        return body

    def action_play_record(self):
        self.ensure_one()
        if not self.record_url:
            return False
        return {
            "type": "ir.actions.act_url",
            "url": self.record_url,
            "target": "new",
        }
