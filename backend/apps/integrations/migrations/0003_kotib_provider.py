from django.db import migrations, models

PROVIDER_CHOICES = [
    ("amocrm", "amoCRM / Kommo"),
    ("bitrix24", "Bitrix24"),
    ("odoo", "Odoo"),
    ("kotib", "Kotib Analytics"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0002_crm_delivery"),
    ]

    operations = [
        migrations.AlterField(
            model_name="crmintegration",
            name="provider",
            field=models.CharField(choices=PROVIDER_CHOICES, max_length=20),
        ),
        migrations.AlterField(
            model_name="crmdelivery",
            name="provider",
            field=models.CharField(choices=PROVIDER_CHOICES, max_length=20),
        ),
    ]
