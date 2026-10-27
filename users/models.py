from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Користувач сайту: дані для входу, профіль і денна ціль КБЖВ."""

    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=100)
    bio = models.TextField(blank=True)
    avatar_url = models.URLField(max_length=500, blank=True)
    kcal_goal = models.PositiveIntegerField(null=True, blank=True)
    protein_goal = models.PositiveIntegerField(null=True, blank=True)
    fat_goal = models.PositiveIntegerField(null=True, blank=True)
    carbs_goal = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.display_name or self.username
