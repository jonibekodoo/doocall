from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0004_call_analysis"),
    ]

    operations = [
        migrations.AddField(
            model_name="crmdelivery",
            name="external_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
