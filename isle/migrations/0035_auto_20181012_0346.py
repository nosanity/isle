# Generated by Django 2.0.7 on 2018-10-11 17:46

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('isle', '0034_auto_20180928_2105'),
    ]

    operations = [
        migrations.CreateModel(
            name='Context',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timezone', models.CharField(max_length=255)),
                ('uuid', models.CharField(max_length=255, unique=True)),
            ],
        ),
        migrations.AddField(
            model_name='event',
            name='context',
            field=models.ForeignKey(default=None, null=True, on_delete=django.db.models.deletion.SET_NULL, to='isle.Context'),
        ),
    ]
