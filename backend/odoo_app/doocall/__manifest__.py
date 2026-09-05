# -*- coding: utf-8 -*-
{
    "name": "DooCall",
    "summary": "DooCall qo'ng'iroqlari: kontakt va CRM ichida, audio player bilan",
    "description": """
DooCall — qo'ng'iroqlarni yozib olish xizmati integratsiyasi.
Har bir qo'ng'iroq avtomatik ravishda kontakt (yoki yangi lid) bilan
bog'lanadi, chatter'ga yozuv tushadi va qo'ng'iroq kartochkasida audio
player orqali yozuvni tinglash mumkin.
""",
    "version": "19.0.1.0.0",
    "author": "DooCall",
    "website": "https://doocall.uz",
    "category": "Sales/CRM",
    "license": "LGPL-3",
    "depends": ["crm"],
    "data": [
        "security/ir.model.access.csv",
        "views/doocall_call_views.xml",
        "views/res_partner_views.xml",
        "views/crm_lead_views.xml",
    ],
    "installable": True,
    "application": True,
}
