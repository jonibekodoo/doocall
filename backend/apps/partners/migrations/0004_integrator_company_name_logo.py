from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("partners", "0003_integratorapplication"),
    ]

    operations = [
        migrations.AddField(
            model_name="integrator",
            name="company_name",
            field=models.CharField(
                blank=True, help_text="Integrator's company / brand", max_length=200
            ),
        ),
        migrations.AddField(
            model_name="integrator",
            name="logo_key",
            field=models.CharField(
                blank=True, default="", help_text="MinIO key", max_length=500
            ),
        ),
    ]
