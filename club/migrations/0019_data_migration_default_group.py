from django.db import migrations


def create_default_group_and_assign(apps, schema_editor):
    User = apps.get_model('club', 'User')
    Group = apps.get_model('club', 'Group')
    Event = apps.get_model('club', 'Event')
    GroupMembership = apps.get_model('club', 'GroupMembership')

    if User.objects.count() == 0:
        return

    creator = (
        User.objects.filter(is_superuser=True).first()
        or User.objects.filter(is_site_admin=True).first()
        or User.objects.first()
    )

    group = Group.objects.create(
        name='Workday Boardgames',
        slug='workday-boardgames',
        created_by=creator,
    )

    Event.objects.filter(group__isnull=True).update(group=group)

    for user in User.objects.all():
        role = 'organizer' if getattr(user, 'is_organizer', False) else 'member'
        GroupMembership.objects.create(
            user=user,
            group=group,
            role=role,
        )


def reverse_default_group(apps, schema_editor):
    Group = apps.get_model('club', 'Group')
    Group.objects.filter(slug='workday-boardgames').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('club', '0018_add_group_to_event_and_creation_override'),
    ]

    operations = [
        migrations.RunPython(
            create_default_group_and_assign,
            reverse_default_group,
        ),
    ]
