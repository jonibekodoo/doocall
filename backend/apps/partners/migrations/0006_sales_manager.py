from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("partners", "0005_integrator_is_public"),
        ("billing", "0004_alter_billingnotification_kind"),
        ("companies", "0007_company_balance_uzs"),
    ]

    operations = [
        migrations.CreateModel(
            name="SalesManager",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("company_name", models.CharField(blank=True, max_length=200)),
                ("logo_key", models.CharField(blank=True, default="", max_length=500)),
                ("phone", models.CharField(blank=True, max_length=20)),
                ("status", models.CharField(choices=[("active", "Active"), ("suspended", "Suspended")], default="active", max_length=10)),
                ("commission_percent", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=5)),
                ("payout_details", models.JSONField(blank=True, default=dict)),
                ("bank_card", models.CharField(blank=True, default="", max_length=32)),
                ("bank_mfo", models.CharField(blank=True, default="", max_length=16)),
                ("bank_inn", models.CharField(blank=True, default="", max_length=16)),
                ("bank_transit", models.CharField(blank=True, default="", max_length=32)),
                ("offer_accepted_version", models.PositiveIntegerField(default=0)),
                ("offer_accepted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="sales_manager_profile", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="SalesPayoutRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount_uzs", models.PositiveBigIntegerField()),
                ("status", models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("paid", "Paid")], default="pending", max_length=10)),
                ("note", models.CharField(blank=True, default="", max_length=300)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("processed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="processed_sales_payouts", to=settings.AUTH_USER_MODEL)),
                ("sales_manager", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payout_requests", to="partners.salesmanager")),
            ],
            options={"ordering": ["-requested_at"]},
        ),
        migrations.CreateModel(
            name="SalesCommission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("percent", models.DecimalField(decimal_places=2, max_digits=5)),
                ("amount_uzs", models.PositiveBigIntegerField()),
                ("status", models.CharField(choices=[("accrued", "Accrued"), ("reversed", "Reversed (refund)"), ("paid_out", "Paid out")], default="accrued", max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reversed_at", models.DateTimeField(blank=True, null=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sales_commissions", to="companies.company")),
                ("integrator", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sales_commissions", to="partners.integrator")),
                ("payment", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="sales_commission", to="billing.payment")),
                ("payout", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="allocated_commissions", to="partners.salespayoutrequest")),
                ("sales_manager", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="commissions", to="partners.salesmanager")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="OfferDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("content", models.TextField(blank=True, default="")),
                ("version", models.PositiveIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="PlatformNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("payout_status", "Payout status"), ("lead_assigned", "Lead assigned"), ("balance_warning", "Balance warning"), ("commission", "Commission accrued"), ("generic", "Generic")], default="generic", max_length=20)),
                ("message", models.CharField(max_length=300)),
                ("is_read", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="platform_notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddField(
            model_name="integrator",
            name="bank_card",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="integrator",
            name="bank_mfo",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AddField(
            model_name="integrator",
            name="bank_inn",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AddField(
            model_name="integrator",
            name="bank_transit",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="integrator",
            name="offer_accepted_version",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="integrator",
            name="offer_accepted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="integrator",
            name="sales_manager",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="integrators", to="partners.salesmanager"),
        ),
        migrations.AddIndex(
            model_name="salescommission",
            index=models.Index(fields=["sales_manager", "status", "-created_at"], name="partners_sc_sm_status_idx"),
        ),
        migrations.AddIndex(
            model_name="salescommission",
            index=models.Index(fields=["company", "-created_at"], name="partners_sc_company_idx"),
        ),
        migrations.AddIndex(
            model_name="platformnotification",
            index=models.Index(fields=["user", "is_read", "-created_at"], name="partners_pn_user_read_idx"),
        ),
    ]
