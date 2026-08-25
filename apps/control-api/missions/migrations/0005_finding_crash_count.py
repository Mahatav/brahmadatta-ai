# Generated for #30 (crash deduplication and clustering).
#
# Additive-only: `Finding.crash_count` defaults to 1 for every existing row (each
# already represents at least the one crash that created it), so this migration needs
# no data backfill beyond the column default. `orchestrator.findings.record_finding`
# increments it every time a caller rediscovers an existing (mission, fingerprint)
# pair instead of writing a new row -- see that module's docstring.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("missions", "0004_job_finding_unique_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="finding",
            name="crash_count",
            field=models.PositiveIntegerField(
                default=1,
                help_text=(
                    "How many raw crash occurrences this fingerprint has collapsed "
                    "into one row, including the one that created it (#30). "
                    "orchestrator.findings.record_finding increments this every time "
                    "a caller rediscovers an existing (mission, fingerprint) pair "
                    "instead of writing a new row -- the cluster count for 'a "
                    "hundred crashes on one root cause reads as one finding.'"
                ),
            ),
        ),
    ]
