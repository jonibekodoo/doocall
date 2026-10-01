"""Billing cycles: statements carry an explicit period, daily charges link to
the statement that deducted them, and over-extended subscription periods are
re-anchored to one calendar month from their start."""

import calendar
from datetime import timedelta

import django.db.models.deletion
from django.db import migrations, models


def _add_month(d):
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def backfill(apps, schema_editor):
    MonthlyStatement = apps.get_model("billing", "MonthlyStatement")
    DailyCharge = apps.get_model("billing", "DailyCharge")
    Subscription = apps.get_model("billing", "Subscription")

    # Legacy calendar-month statements → explicit period + attach their charges.
    for s in MonthlyStatement.objects.all():
        start = s.month
        end = _add_month(start.replace(day=1))
        MonthlyStatement.objects.filter(pk=s.pk).update(period_start=start, period_end=end)
        DailyCharge.objects.filter(
            company_id=s.company_id, statement__isnull=True, date__gte=start, date__lt=end
        ).update(statement_id=s.pk)

    # Periods used to grow +30 days per top-up; a cycle is now exactly one month.
    for sub in Subscription.objects.filter(status="active").exclude(current_period_start=None):
        target = _add_month(sub.current_period_start)
        if sub.current_period_end is None or sub.current_period_end > target:
            Subscription.objects.filter(pk=sub.pk).update(current_period_end=target)


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0005_payment_provider_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="monthlystatement",
            name="period_start",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="monthlystatement",
            name="period_end",
            field=models.DateField(blank=True, help_text="Exclusive", null=True),
        ),
        migrations.AlterField(
            model_name="monthlystatement",
            name="month",
            field=models.DateField(help_text="Cycle start date (legacy: first day of the month)"),
        ),
        migrations.AddField(
            model_name="dailycharge",
            name="statement",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="charges",
                to="billing.monthlystatement",
            ),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
