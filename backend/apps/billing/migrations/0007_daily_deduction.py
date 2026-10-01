"""Prepaid daily billing: each operator-day is deducted from the balance the
next night. Charges already taken by a PAID statement are marked deducted."""

from django.db import migrations, models


def backfill(apps, schema_editor):
    DailyCharge = apps.get_model("billing", "DailyCharge")
    MonthlyStatement = apps.get_model("billing", "MonthlyStatement")
    for s in MonthlyStatement.objects.filter(status="paid"):
        when = s.settled_at or s.created_at
        DailyCharge.objects.filter(statement_id=s.pk, deducted_at__isnull=True).update(deducted_at=when)


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0006_billing_cycles"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailycharge",
            name="deducted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
