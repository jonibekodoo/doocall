from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("partners", "0002_platformsetting_min_payout_uzs"),
    ]

    operations = [
        migrations.CreateModel(
            name="IntegratorApplication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("full_name", models.CharField(max_length=200)),
                ("phone", models.CharField(max_length=32)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("company", models.CharField(blank=True, max_length=200)),
                ("message", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("contacted", "Contacted"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        default="new",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="integratorapplication",
            index=models.Index(fields=["status", "-created_at"], name="partners_in_status_2b6d1e_idx"),
        ),
    ]
