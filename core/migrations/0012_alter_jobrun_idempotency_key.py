# core/migrations/0012_alter_jobrun_idempotency_key.py
from django.db import migrations, models


def backfill_jobrun_idempotency_key(apps, schema_editor):
    JobRun = apps.get_model("core", "JobRun")

    # fill NULLs and also empty-string, just in case
    qs = JobRun.objects.filter(idempotency_key__isnull=True) | JobRun.objects.filter(
        idempotency_key=""
    )

    for jr in qs.iterator():
        jr.idempotency_key = f"legacy-{jr.id}"  # unique, stable, <= 80 chars
        jr.save(update_fields=["idempotency_key"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_backfill_jobrun_idempotency_key"),
    ]

    operations = [
        migrations.AlterField(
            model_name="jobrun",
            name="idempotency_key",
            # IMPORTANT: match your models.py field args (db_index/unique/etc),
            # but make it non-null/non-blank.
            field=models.CharField(max_length=80),
        ),
    ]
