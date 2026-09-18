import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("partners", "0006_sales_manager"),
    ]

    operations = [
        migrations.AddField(
            model_name="integratorapplication",
            name="sales_manager",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="applications", to="partners.salesmanager"),
        ),
        migrations.CreateModel(
            name="Pipeline",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("sales_manager", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pipelines", to="partners.salesmanager")),
            ],
            options={"ordering": ["order", "id"]},
        ),
        migrations.CreateModel(
            name="PipelineStage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("order", models.PositiveSmallIntegerField(default=0)),
                ("color", models.CharField(blank=True, default="", max_length=16)),
                ("pipeline", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stages", to="partners.pipeline")),
            ],
            options={"ordering": ["order", "id"]},
        ),
        migrations.CreateModel(
            name="Lead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("full_name", models.CharField(max_length=200)),
                ("phone", models.CharField(blank=True, max_length=32)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("company", models.CharField(blank=True, max_length=200)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("application", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="leads", to="partners.integratorapplication")),
                ("pipeline", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="leads", to="partners.pipeline")),
                ("sales_manager", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="leads", to="partners.salesmanager")),
                ("stage", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="leads", to="partners.pipelinestage")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="CrmTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=300)),
                ("due_at", models.DateTimeField(blank=True, null=True)),
                ("is_done", models.BooleanField(default=False)),
                ("auto", models.BooleanField(default=False, help_text="System-generated (e.g. balance warning)")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("lead", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="tasks", to="partners.lead")),
                ("sales_manager", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tasks", to="partners.salesmanager")),
            ],
            options={"ordering": ["is_done", "due_at", "-created_at"]},
        ),
        migrations.AddIndex(
            model_name="lead",
            index=models.Index(fields=["sales_manager", "pipeline", "stage"], name="partners_lead_sm_pipe_idx"),
        ),
        migrations.AddIndex(
            model_name="crmtask",
            index=models.Index(fields=["sales_manager", "is_done", "due_at"], name="partners_task_sm_done_idx"),
        ),
    ]
