from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def fill_team_carrier(apps, schema_editor):
    Tournament = apps.get_model('tournaments', 'Tournament')
    Tournament.objects.using(schema_editor.connection.alias).filter(competition_type='team', round_count__isnull=True).update(round_count=1)


class Migration(migrations.Migration):
    dependencies = [('tournaments', '0012_team_plan_sources')]
    operations = [
        migrations.RemoveConstraint(model_name='tournament', name='tournament_round_range'),
        migrations.RunPython(fill_team_carrier, migrations.RunPython.noop),
        migrations.AlterField(model_name='tournament', name='round_count', field=models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(6)])),
        migrations.AlterField(model_name='tournamentround', name='round_number', field=models.PositiveSmallIntegerField()),
        migrations.AddConstraint(model_name='tournament', constraint=models.CheckConstraint(condition=models.Q(models.Q(competition_type='individual', round_count__gte=1, round_count__lte=6), models.Q(competition_type='team', round_count=1), _connector='OR'), name='tournament_round_range')),
    ]
