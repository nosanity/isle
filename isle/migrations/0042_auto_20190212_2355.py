# Generated by Django 2.0.7 on 2019-02-12 13:55

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import jsonfield.fields
import isle.models


class Migration(migrations.Migration):

    dependencies = [
        ('isle', '0041_auto_20190209_0034'),
    ]

    operations = [
        migrations.CreateModel(
            name='CSVDump',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('csv_file', models.FileField(blank=True, null=True, upload_to=isle.models.PathAndRename('csv-dumps'))),
                ('header', models.CharField(max_length=255)),
                ('datetime_ordered', models.DateTimeField(default=django.utils.timezone.now)),
                ('datetime_ready', models.DateTimeField(blank=True, null=True)),
                ('status', models.SmallIntegerField(choices=[(1, 'ожидание генерации'), (2, 'идет генерация'), (3, 'готово'), (4, 'ошибка')], default=1)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('meta_data', jsonfield.fields.JSONField(null=True)),
            ],
        ),
        migrations.AddField(
            model_name='context',
            name='guid',
            field=models.CharField(default='', max_length=500),
        ),
    ]
