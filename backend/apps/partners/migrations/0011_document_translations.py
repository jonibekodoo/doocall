from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("partners", "0010_legal_document"),
    ]

    operations = [
        migrations.AddField(
            model_name="offerdocument",
            name="content_ru",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="offerdocument",
            name="content_en",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="legaldocument",
            name="content_ru",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="legaldocument",
            name="content_en",
            field=models.TextField(blank=True, default=""),
        ),
    ]
