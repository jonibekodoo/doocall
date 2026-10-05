import django.db.models.deletion
import django.db.models.manager
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0005_company_integrator"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("billing", "0007_daily_deduction"),
    ]

    operations = [
        migrations.CreateModel(
            name="SavedCard",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("paylov_card_id", models.CharField(db_index=True, max_length=64)),
                ("paylov_user_id", models.CharField(max_length=64)),
                ("masked_number", models.CharField(blank=True, default="", max_length=24)),
                ("owner", models.CharField(blank=True, default="", max_length=120)),
                ("vendor", models.CharField(blank=True, default="", max_length=32)),
                ("expire", models.CharField(blank=True, default="", help_text="YYMM", max_length=4)),
                ("is_confirmed", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(app_label)s_%(class)s_set",
                        to="companies.company",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "abstract": False,
                "default_manager_name": "objects",
                "base_manager_name": "all_objects",
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("all_objects", django.db.models.manager.Manager()),
            ],
        ),
        migrations.CreateModel(
            name="AutoPaySettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_enabled", models.BooleanField(default=False)),
                (
                    "amount_mode",
                    models.CharField(
                        choices=[("month", "One month of service"), ("fixed", "Fixed amount")],
                        default="month", max_length=8,
                    ),
                ),
                ("fixed_amount_uzs", models.PositiveBigIntegerField(blank=True, null=True)),
                ("monthly_limit_uzs", models.PositiveBigIntegerField(blank=True, null=True)),
                ("consent_at", models.DateTimeField(blank=True, null=True)),
                ("fail_streak", models.PositiveSmallIntegerField(default=0)),
                ("last_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("last_status", models.CharField(blank=True, default="", max_length=8)),
                ("last_error", models.CharField(blank=True, default="", max_length=64)),
                ("disabled_reason", models.CharField(blank=True, default="", max_length=64)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "card",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                        related_name="autopay", to="billing.savedcard",
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
                (
                    "consent_by",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "abstract": False,
                "default_manager_name": "objects",
                "base_manager_name": "all_objects",
                "constraints": [
                    models.UniqueConstraint(fields=("company",), name="uniq_autopay_per_company")
                ],
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("all_objects", django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddField(
            model_name="payment",
            name="is_auto",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="payment",
            name="saved_card",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="payments", to="billing.savedcard",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="failure_code",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="paymentproviderconfig",
            name="autopay_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="billingnotification",
            name="kind",
            field=models.CharField(
                choices=[
                    ("charge_settled", "Monthly charge deducted"),
                    ("payment_due", "Payment due"),
                    ("payment_requested", "Payment request submitted"),
                    ("payment_received", "Payment received"),
                    ("payment_refunded", "Payment refunded"),
                    ("tariff_changed", "Tariff changed"),
                    ("blocked", "Access blocked"),
                    ("autopay_failed", "Automatic payment failed"),
                ],
                max_length=20,
            ),
        ),
    ]
