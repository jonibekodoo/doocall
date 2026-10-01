import django.db.models.deletion
import django.db.models.manager
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calls", "0003_contact_responsible"),
        ("companies", "0005_company_integrator"),
        ("integrations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CrmDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "provider",
                    models.CharField(
                        choices=[("amocrm", "amoCRM / Kommo"), ("bitrix24", "Bitrix24"), ("odoo", "Odoo")],
                        max_length=20,
                    ),
                ),
                ("status", models.CharField(choices=[("ok", "ok"), ("error", "error")], max_length=10)),
                ("error", models.CharField(blank=True, default="", max_length=500)),
                ("is_retry", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "call",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="crm_deliveries",
                        to="calls.callrecord",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(app_label)s_%(class)s_set",
                        to="companies.company",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(fields=["company", "provider", "-created_at"], name="crm_deliv_prov_idx"),
                    models.Index(fields=["call", "provider"], name="crm_deliv_call_idx"),
                ],
                "default_manager_name": "objects",
                "base_manager_name": "all_objects",
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("all_objects", django.db.models.manager.Manager()),
            ],
        ),
    ]
