from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('club', '0019_data_migration_default_group'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='group',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to='club.group',
            ),
        ),
    ]
