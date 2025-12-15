# core/migrations/000X_backfill_jobrun_idempotency_key.py
from django.db import migrations


def backfill(apps, schema_editor):
    JobRun = apps.get_model("core", "JobRun")
    for jr in JobRun.objects.filter(idempotency_key__isnull=True).iterator():
        jr.idempotency_key = f"legacy-{jr.id}"
        jr.save(update_fields=["idempotency_key"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_jobrun_idempotency_key_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
