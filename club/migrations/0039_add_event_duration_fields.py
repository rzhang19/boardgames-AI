from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def backfill_end_time(apps, schema_editor):
    Event = apps.get_model('club', 'Event')
    for event in Event.objects.all():
        event.end_time = event.date + __import__('datetime').timedelta(minutes=event.duration_minutes)
        event.save(update_fields=['end_time'])


class Migration(migrations.Migration):

    dependencies = [
        ('club', '0038_sitesettings_site_lockdown_active_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='default_event_duration_minutes',
            field=models.PositiveIntegerField(default=120),
        ),
        migrations.AddField(
            model_name='group',
            name='default_event_duration_minutes',
            field=models.PositiveIntegerField(default=120),
        ),
        migrations.AddField(
            model_name='event',
            name='duration_minutes',
            field=models.PositiveIntegerField(default=120),
        ),
        migrations.AddField(
            model_name='event',
            name='end_time',
            field=models.DateTimeField(default=django.utils.timezone.now, db_index=True),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_end_time, migrations.RunPython.noop),
        migrations.AddField(
            model_name='event',
            name='ended_early_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
