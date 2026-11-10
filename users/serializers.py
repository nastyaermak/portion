import re

from django.contrib.auth import password_validation
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    """Реєстрація: перевіряє поля і зберігає пароль лише як хеш."""

    username = serializers.CharField(
        max_length=150,
        validators=[UnicodeUsernameValidator()],
        error_messages={
            "required": "Вкажіть username",
            "blank": "Вкажіть username",
            "max_length": "Username — не більше 150 символів",
        },
    )
    first_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        error_messages={"max_length": "Ім'я — не більше 150 символів"},
    )
    last_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        error_messages={"max_length": "Прізвище — не більше 150 символів"},
    )
    email = serializers.EmailField(
        max_length=254,
        error_messages={
            "required": "Вкажіть email",
            "blank": "Вкажіть email",
            "invalid": "Email має бути у форматі name@example.com",
            "max_length": "Email — не більше 254 символів",
        },
    )
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        max_length=128,
        trim_whitespace=False,
        error_messages={
            "required": "Вкажіть пароль",
            "blank": "Вкажіть пароль",
            "min_length": "Пароль має бути не коротший за 8 символів",
            "max_length": "Пароль — не більше 128 символів",
        },
    )
    password_confirm = serializers.CharField(
        write_only=True,
        max_length=128,
        trim_whitespace=False,
        error_messages={
            "required": "Повторіть пароль",
            "blank": "Повторіть пароль",
            "max_length": "Пароль — не більше 128 символів",
        },
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "display_name",
            "password",
            "password_confirm",
        ]
        read_only_fields = ["id", "display_name"]

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Такий username уже зайнятий")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "Користувач з таким email уже зареєстрований"
            )
        return value

    def validate(self, attrs):
        password = attrs["password"]
        if password != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Паролі не збігаються"}
            )
        if not re.search(r"[A-Za-zА-Яа-яЇїІіЄєҐґ]", password) or not re.search(
            r"\d", password
        ):
            raise serializers.ValidationError(
                {"password": "Пароль має містити хоча б одну літеру і цифру"}
            )
        # Стандартні перевірки Django: не надто простий, не схожий на
        # username чи email, не складається лише з цифр.
        candidate = User(
            username=attrs["username"],
            email=attrs["email"],
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        try:
            password_validation.validate_password(password, candidate)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": error.messages[0]})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        first = validated_data.get("first_name", "")
        last = validated_data.get("last_name", "")
        display_name = f"{first} {last}".strip() or validated_data["username"]
        # create_user хешує пароль, у базу відкритий пароль не потрапляє
        return User.objects.create_user(
            password=password, display_name=display_name, **validated_data
        )


class DailyGoalSerializer(serializers.Serializer):
    kcal = serializers.IntegerField(
        source="kcal_goal", min_value=0, allow_null=True, required=False
    )
    protein = serializers.IntegerField(
        source="protein_goal", min_value=0, allow_null=True, required=False
    )
    fat = serializers.IntegerField(
        source="fat_goal", min_value=0, allow_null=True, required=False
    )
    carbs = serializers.IntegerField(
        source="carbs_goal", min_value=0, allow_null=True, required=False
    )


class ProfileSerializer(serializers.ModelSerializer):
    """Мій профіль: GET і PATCH /api/me."""

    daily_goal = DailyGoalSerializer(source="*", required=False)
    is_admin = serializers.BooleanField(source="is_staff", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "display_name",
            "bio",
            "avatar_url",
            "daily_goal",
            "is_admin",
            "created_at",
        ]
        read_only_fields = ["id", "username", "email", "created_at"]
        extra_kwargs = {
            "display_name": {
                "allow_blank": False,
                "error_messages": {
                    "blank": "Ім'я на сайті не може бути порожнім"
                },
            },
        }

    def update(self, instance, validated_data):
        goal = validated_data.pop("daily_goal", None) or {}
        validated_data.update(goal)
        return super().update(instance, validated_data)
