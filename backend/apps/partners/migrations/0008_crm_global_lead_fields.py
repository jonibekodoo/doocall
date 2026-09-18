import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

DEFAULT_STAGES = [
    ("Yangi", "#d99a2b"),
    ("Aloqa", "#2a9691"),
    ("Taklif", "#1f7873"),
    ("Muzokara", "#1c605d"),
    ("Yutildi", "#3fb27a"),
    ("Yutqazildi", "#e05d47"),
]


def to_global(apps, schema_editor):
    Pipeline = apps.get_model("partners", "Pipeline")
    PipelineStage = apps.get_model("partners", "PipelineStage")
    Lead = apps.get_model("partners", "Lead")

    gp = Pipeline.objects.filter(sales_manager__isnull=True).order_by("order", "id").first()
    if gp is None:
        gp = Pipeline.objects.create(sales_manager=None, name="Asosiy varonka", order=0)
        for i, (n, c) in enumerate(DEFAULT_STAGES):
            PipelineStage.objects.create(pipeline=gp, name=n, order=i, color=c)
    gstages = {s.name: s for s in gp.stages.all()}
    first_stage = gp.stages.order_by("order", "id").first()

    for lead in Lead.objects.exclude(pipeline=gp):
        old_name = None
        if lead.stage_id:
            old_name = PipelineStage.objects.filter(pk=lead.stage_id).values_list("name", flat=True).first()
        lead.pipeline = gp
        lead.stage = gstages.get(old_name, first_stage)
        lead.save(update_fields=["pipeline", "stage"])

    # Remove now-unused per-manager pipelines.
    Pipeline.objects.filter(sales_manager__isnull=False).delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("partners", "0007_crm"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pipeline",
            name="sales_manager",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="pipelines", to="partners.salesmanager"),
        ),
        migrations.AddField(
            model_name="lead",
            name="contact_name",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="lead",
            name="source",
            field=models.CharField(blank=True, help_text="Manba", max_length=120),
        ),
        migrations.AddField(
            model_name="lead",
            name="tags",
            field=models.CharField(blank=True, help_text="Comma-separated tags", max_length=300),
        ),
        migrations.AddField(
            model_name="lead",
            name="budget_uzs",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="lead",
            name="priority",
            field=models.PositiveSmallIntegerField(default=0, help_text="0-3 stars"),
        ),
        migrations.CreateModel(
            name="LeadEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("created", "Created"), ("note", "Note"), ("stage", "Stage change"), ("task", "Task"), ("task_done", "Task done"), ("field", "Field change"), ("assigned", "Assigned")], default="note", max_length=12)),
                ("text", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("lead", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="partners.lead")),
                ("task", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="events", to="partners.crmtask")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddIndex(
            model_name="leadevent",
            index=models.Index(fields=["lead", "created_at"], name="partners_leadevent_idx"),
        ),
        migrations.RunPython(to_global, noop),
    ]
