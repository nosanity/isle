# Generated by Django 2.0.7 on 2018-08-03 17:54

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('isle', '0027_merge_20180803_2158'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventBlock',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('duration', models.IntegerField()),
                ('title', models.CharField(max_length=255)),
                ('block_type', models.SmallIntegerField(choices=[(1, 'Лекция с вопросами из зала'), (2, 'Образ Результата:'), (3, 'Лекция с проверкой усвоения материала'), (4, 'Мастер класс \\ освоение инструмента с фиксируемым выполнением заданий'), (5, 'Мастер класс \\ тренинг без фиксации выполнения заданий'), (6, 'Работа над проектами \\ групповая работа'), (7, 'Решение кейсов (коллективное\\индивидуальное)'), (8, 'Стратегическая сессия \\ форсайт'), (9, 'Игра \\ модельная сессия'), (10, 'Хакатон \\ дизайн сессия'), (11, 'Нетворкинг - сессия'), (12, 'Обсуждение \\ дискуссия'), (13, 'Питч сессия \\ презентация результатов'), (14, 'Экспериментальная лаборатория'), (15, 'Менторская \\ тьюторская сессия'), (16, 'Смешанный тип')])),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='isle.Event')),
            ],
        ),
    ]
