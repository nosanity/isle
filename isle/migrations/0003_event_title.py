# Generated by Django 2.0.7 on 2018-07-06 10:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('isle', '0002_auto_20180704_1519'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='title',
            field=models.CharField(default='', max_length=1000),
        ),
    ]
