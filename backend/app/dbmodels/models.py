# -*- coding: utf-8 -*-
"""Contains models related to stats"""
from django.contrib.postgres.fields import ArrayField
from django.db import models


class Game(models.Model):
    class Meta:
        db_table = 'game'

    id = models.UUIDField(primary_key=True)
    date = models.DateField(null=False, db_index=True)


class Team(models.Model):
    class Meta:
        db_table = 'team'

    id = models.UUIDField(primary_key=True)
    name = models.TextField(null=False)


class Player(models.Model):
    class Meta:
        db_table = 'player'

    id = models.UUIDField(primary_key=True)
    team = models.ForeignKey(Team, null=False, on_delete=models.PROTECT)
    name = models.TextField(null=False)


class Possession(models.Model):
    class Meta:
        db_table = 'possession'

    id = models.UUIDField(primary_key=True)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, db_index=True, null=False)
    offensive_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, db_index=True, null=False, related_name='offensive_possessions',
    )
    defensive_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, db_index=True, null=False, related_name='defensive_possessions',
    )
    offensive_player_ids = ArrayField(models.UUIDField(), size=5)
    defensive_player_ids = ArrayField(models.UUIDField(), size=5)
    period = models.SmallIntegerField(null=False)
    seconds = models.FloatField(null=False)
    fg2_made = models.IntegerField(null=False)
    fg2_attempted = models.IntegerField(null=False)
    fg3_made = models.IntegerField(null=False)
    fg3_attempted = models.IntegerField(null=False)
    fg_made = models.IntegerField(null=False)
    fg_attempted = models.IntegerField(null=False)
    ft_made = models.IntegerField(null=False)
    ft_attempted = models.IntegerField(null=False)
    rebounds_offense = models.IntegerField(null=False)
    rebounds_defense = models.IntegerField(null=False)
    rebound_opportunities = models.IntegerField(null=False)
    assists = models.IntegerField(null=False)
    steals = models.IntegerField(null=False)
    turnovers = models.IntegerField(null=False)
    blocks = models.IntegerField(null=False)
    offensive_fouls = models.IntegerField(null=False)
    defensive_fouls = models.IntegerField(null=False)
    shooting_fouls = models.IntegerField(null=False)
    points = models.IntegerField(null=False)
    shot_attempts = models.IntegerField(null=False)
    shot_attempt_points = models.IntegerField(null=False)
    ft_potential_points = models.IntegerField(null=False)
    transition_take_fouls = models.IntegerField(null=False)
