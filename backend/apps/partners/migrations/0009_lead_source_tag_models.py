import django.db.models.deletion
from django.db import migrations, models

DEFAULT_SOURCES = ["Ariza", "Qo'ng'iroq", "Telegram", "Instagram", "Tavsiya", "Veb-sayt"]
DEFAULT_TASK_TYPES = [
    ("Qo'ng'iroq", "phone"),
    ("Uchrashuv", "calendar"),
    ("Xabar", "message"),
    ("Eslatma", "bell"),
    ("Boshqa", "clipboard"),
]


def seed(apps, schema_editor):
    LeadSource = apps.get_model("partners", "LeadSource")
    if not LeadSource.objects.exists():
        for i, name in enumerate(DEFAULT_SOURCES):
            LeadSource.objects.create(name=name, order=i)


def seed_types(apps, schema_editor):
    CrmTaskType = apps.get_model("partners", "CrmTaskType")
    if not CrmTaskType.objects.exists():
        for i, (name, icon) in enumerate(DEFAULT_TASK_TYPES):
            CrmTaskType.objects.create(name=name, icon=icon, order=i)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("partners", "0008_crm_global_lead_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="LeadSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("order", models.PositiveSmallIntegerField(default=0)),
            ],
            options={"ordering": ["order", "name"]},
        ),
        migrations.CreateModel(
            name="LeadTag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True)),
                ("color", models.CharField(blank=True, default="", max_length=16)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.RunPython(seed, noop),
        migrations.RemoveField(model_name="lead", name="source"),
        migrations.RemoveField(model_name="lead", name="tags"),
        migrations.RemoveField(model_name="lead", name="budget_uzs"),
        migrations.AddField(
            model_name="lead",
            name="source",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="leads", to="partners.leadsource"),
        ),
        migrations.AddField(
            model_name="lead",
            name="tags",
            field=models.ManyToManyField(blank=True, related_name="leads", to="partners.leadtag"),
        ),
        migrations.CreateModel(
            name="CrmTaskType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True)),
                ("icon", models.CharField(blank=True, default="", help_text="lucide icon key", max_length=32)),
                ("order", models.PositiveSmallIntegerField(default=0)),
            ],
            options={"ordering": ["order", "name"]},
        ),
        migrations.RunPython(seed_types, noop),
        migrations.AddField(
            model_name="crmtask",
            name="type",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tasks", to="partners.crmtasktype"),
        ),
        migrations.AddField(
            model_name="crmtask",
            name="is_cancelled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="crmtask",
            name="cancel_reason",
            field=models.CharField(blank=True, default="", max_length=300),
        ),
    ]
