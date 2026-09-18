from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("partners", "0004_integrator_company_name_logo"),
    ]

    operations = [
        migrations.AddField(
            model_name="integrator",
            name="is_public",
            field=models.BooleanField(
                default=False,
                help_text="Show in the public 'our integrators' landing section",
            ),
        ),
    ]
