# Generated by Django 2.0.7 on 2018-07-17 06:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('isle', '0015_eventmaterial_is_public'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventmaterial',
            name='initiator',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='eventonlymaterial',
            name='initiator',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='eventteammaterial',
            name='initiator',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
