import django.db.models.deletion
from django.db import migrations, models


def seed_configs(apps, schema_editor):
    PaymentProviderConfig = apps.get_model("billing", "PaymentProviderConfig")
    defaults = {
        "paylov": (True, 0),
        "manual": (True, 1),
        "payme": (False, 2),
        "click": (False, 3),
    }
    for name, (enabled, order) in defaults.items():
        PaymentProviderConfig.objects.get_or_create(
            provider=name, defaults={"is_enabled": enabled, "sort_order": order}
        )


def unseed(apps, schema_editor):
    apps.get_model("billing", "PaymentProviderConfig").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0004_alter_billingnotification_kind"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="provider",
            field=models.CharField(
                choices=[
                    ("payme", "Payme"),
                    ("click", "Click"),
                    ("paylov", "Paylov"),
                    ("manual", "Bank / Naqd"),
                ],
                max_length=10,
            ),
        ),
        migrations.CreateModel(
            name="PaymentProviderConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "provider",
                    models.CharField(
                        choices=[
                            ("payme", "Payme"),
                            ("click", "Click"),
                            ("paylov", "Paylov"),
                            ("manual", "Bank / Naqd"),
                        ],
                        max_length=10,
                        unique=True,
                    ),
                ),
                ("is_enabled", models.BooleanField(default=False)),
                ("logo_key", models.CharField(blank=True, default="", help_text="MinIO key", max_length=500)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["sort_order", "provider"],
            },
        ),
        migrations.CreateModel(
            name="PaylovLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("direction", models.CharField(choices=[("in", "Paylov → biz"), ("out", "Biz → Paylov")], max_length=3)),
                ("event", models.CharField(help_text="method / endpoint / event name", max_length=64)),
                ("ok", models.BooleanField(default=True)),
                ("http_status", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("request_body", models.JSONField(blank=True, default=dict)),
                ("response_body", models.JSONField(blank=True, default=dict)),
                ("note", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "payment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="paylov_logs",
                        to="billing.payment",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="paylovlog",
            index=models.Index(fields=["-created_at"], name="billing_pay_created_dc9e3f_idx"),
        ),
        migrations.AddIndex(
            model_name="paylovlog",
            index=models.Index(fields=["event"], name="billing_pay_event_1a2b3c_idx"),
        ),
        migrations.RunPython(seed_configs, unseed),
    ]
