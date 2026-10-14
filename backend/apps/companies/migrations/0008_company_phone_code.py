import django.core.validators
from django.db import migrations, models

# Snapshot of apps.core.phone.DIAL_CODES (country → calling code) at the time
# of this migration; unknown countries keep the Uzbek default.
COUNTRY_CODES = {
    "UZ": "998",
    "TJ": "992",
    "KG": "996",
    "KZ": "7",
    "RU": "7",
    "TM": "993",
    "AF": "93",
    "AZ": "994",
    "AM": "374",
    "GE": "995",
    "BY": "375",
    "UA": "380",
    "MD": "373",
    "TR": "90",
    "AE": "971",
    "CN": "86",
    "IN": "91",
    "PK": "92",
    "US": "1",
    "GB": "44",
}


def set_from_country(apps, schema_editor):
    Company = apps.get_model("companies", "Company")
    for country, code in COUNTRY_CODES.items():
        if code != "998":
            Company.objects.filter(country__iexact=country).update(phone_code=code)


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0007_company_balance_uzs"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="phone_code",
            field=models.CharField(
                default="998",
                max_length=4,
                validators=[django.core.validators.RegexValidator("^\\d{1,4}$", "1–4 digits")],
            ),
        ),
        migrations.RunPython(set_from_country, migrations.RunPython.noop),
    ]
