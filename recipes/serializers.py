from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.functions import Lower
from rest_framework import serializers

from config.errors import Conflict

from .models import Category, Cuisine, Ingredient, Recipe, RecipeIngredient, RecipeStep

User = get_user_model()


def nutrition(kcal, protein, fat, carbs):
    """КБЖВ у форматі API: калорії цілим числом, решта з одним знаком після коми."""
    return {
        'kcal': round(float(kcal or 0)),
        'protein': round(float(protein or 0), 1),
        'fat': round(float(fat or 0), 1),
        'carbs': round(float(carbs or 0), 1),
    }


class UniqueNameMixin:
    """Назва довідника унікальна без урахування регістру; дубль — 409, а не 400."""

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Назва не може бути порожньою')
        same = self.Meta.model.objects.annotate(lower_name=Lower('name')).filter(lower_name=value.lower())
        if self.instance is not None:
            same = same.exclude(pk=self.instance.pk)
        if same.exists():
            raise Conflict(f'{self.Meta.label} з назвою «{value}» уже є')
        return value


class CategorySerializer(UniqueNameMixin, serializers.ModelSerializer):
    name = serializers.CharField(max_length=50)
    recipes_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Category
        fields = ['id', 'name', 'recipes_count']
        label = 'Категорія'


class CuisineSerializer(UniqueNameMixin, serializers.ModelSerializer):
    name = serializers.CharField(max_length=50)
    recipes_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Cuisine
        fields = ['id', 'name', 'recipes_count']
        label = 'Кухня'


class Per100gSerializer(serializers.Serializer):
    """КБЖВ на 100 г; при PATCH можна передати лише частину значень."""

    kcal = serializers.DecimalField(max_digits=6, decimal_places=1, min_value=0, source='kcal_100g')
    protein = serializers.DecimalField(max_digits=5, decimal_places=1, min_value=0, source='protein_100g')
    fat = serializers.DecimalField(max_digits=5, decimal_places=1, min_value=0, source='fat_100g')
    carbs = serializers.DecimalField(max_digits=5, decimal_places=1, min_value=0, source='carbs_100g')

    def to_representation(self, instance):
        return {
            'kcal': float(instance.kcal_100g),
            'protein': float(instance.protein_100g),
            'fat': float(instance.fat_100g),
            'carbs': float(instance.carbs_100g),
        }


class IngredientSerializer(UniqueNameMixin, serializers.ModelSerializer):
    name = serializers.CharField(max_length=100)
    per_100g = Per100gSerializer(source='*')
    recipes_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Ingredient
        fields = ['id', 'name', 'per_100g', 'recipes_count']
        label = 'Інгредієнт'

    def to_internal_value(self, data):
        """При PATCH дозволяємо передати лише частину per_100g, решту беремо з бази."""
        if self.partial and self.instance is not None and isinstance(data, dict) \
                and isinstance(data.get('per_100g'), dict):
            current = Per100gSerializer(self.instance).data
            data = {**data, 'per_100g': {**current, **data['per_100g']}}
        return super().to_internal_value(data)

    def validate(self, attrs):
        """Білки, жири й вуглеводи разом не можуть важити більше за 100 г."""
        get = lambda name: attrs.get(name, getattr(self.instance, name, 0) if self.instance else 0)
        total = get('protein_100g') + get('fat_100g') + get('carbs_100g')
        if total > 100:
            raise serializers.ValidationError(
                {'per_100g': f'Білки, жири й вуглеводи разом — {total} г, а це більше, ніж 100 г продукту'})
        return attrs


class ShortCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name']


class ShortCuisineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cuisine
        fields = ['id', 'name']


class ShortAuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'display_name']


class RecipeListSerializer(serializers.ModelSerializer):
    """Рецепт у каталозі; КБЖВ береться з анотацій запиту (див. views.with_nutrition)."""

    category = ShortCategorySerializer()
    cuisine = ShortCuisineSerializer()
    author = ShortAuthorSerializer()
    nutrition_per_serving = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = ['id', 'title', 'image_url', 'cook_time_min', 'servings',
                  'category', 'cuisine', 'author', 'nutrition_per_serving']

    def get_nutrition_per_serving(self, recipe):
        return nutrition(recipe.kcal, recipe.protein, recipe.fat, recipe.carbs)


class RecipeIngredientReadSerializer(serializers.ModelSerializer):
    ingredient = serializers.SerializerMethodField()
    amount_g = serializers.FloatField()

    class Meta:
        model = RecipeIngredient
        fields = ['ingredient', 'amount_g', 'note']

    def get_ingredient(self, item):
        return {'id': item.ingredient_id, 'name': item.ingredient.name}


class RecipeDetailSerializer(RecipeListSerializer):
    ingredients = RecipeIngredientReadSerializer(source='recipe_ingredients', many=True)
    steps = serializers.SerializerMethodField()

    class Meta(RecipeListSerializer.Meta):
        fields = ['id', 'title', 'description', 'image_url', 'cook_time_min', 'servings',
                  'category', 'cuisine', 'author', 'ingredients', 'steps',
                  'nutrition_per_serving', 'created_at', 'updated_at']

    def get_steps(self, recipe):
        return [step.text for step in recipe.steps.all()]


class RecipeIngredientWriteSerializer(serializers.Serializer):
    ingredient_id = serializers.IntegerField()
    amount_g = serializers.DecimalField(max_digits=7, decimal_places=1, min_value=Decimal('0.1'),
                                        error_messages={'min_value': 'Кількість грамів має бути більше 0'})
    note = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')

    def validate_ingredient_id(self, value):
        if not Ingredient.objects.filter(pk=value).exists():
            raise serializers.ValidationError(f'Інгредієнта з id {value} немає')
        return value


class RecipeWriteSerializer(serializers.ModelSerializer):
    """Створення й редагування рецепта. КБЖВ не передається — сервер рахує його сам."""

    author_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='author',
        error_messages={'does_not_exist': 'Користувача з id {pk_value} немає'})
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category',
        error_messages={'does_not_exist': 'Категорії з id {pk_value} немає'})
    cuisine_id = serializers.PrimaryKeyRelatedField(
        queryset=Cuisine.objects.all(), source='cuisine',
        error_messages={'does_not_exist': 'Кухні з id {pk_value} немає'})
    servings = serializers.IntegerField(min_value=1, error_messages={
        'min_value': 'Кількість порцій має бути більше 0'})
    cook_time_min = serializers.IntegerField(min_value=1, error_messages={
        'min_value': 'Час приготування має бути більше 0 хвилин'})
    ingredients = RecipeIngredientWriteSerializer(many=True)
    steps = serializers.ListField(child=serializers.CharField(), allow_empty=False, error_messages={
        'empty': 'Додайте хоча б один крок приготування'})

    class Meta:
        model = Recipe
        fields = ['title', 'description', 'image_url', 'cook_time_min', 'servings',
                  'author_id', 'category_id', 'cuisine_id', 'ingredients', 'steps']

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Назва не може бути порожньою')
        return value

    def validate_ingredients(self, value):
        if not value:
            raise serializers.ValidationError('Додайте хоча б один інгредієнт')
        ids = [item['ingredient_id'] for item in value]
        repeated = sorted({i for i in ids if ids.count(i) > 1})
        if repeated:
            raise serializers.ValidationError(
                f'Інгредієнт з id {", ".join(map(str, repeated))} указано кілька разів — об\'єднайте грамовку')
        return value

    def validate(self, attrs):
        if self.instance is not None and 'author' in attrs and attrs['author'] != self.instance.author:
            raise serializers.ValidationError({'author_id': 'Автора рецепта змінити не можна'})
        return attrs

    def save_children(self, recipe, ingredients, steps):
        """Списки інгредієнтів і кроків замінюються повністю."""
        if ingredients is not None:
            recipe.recipe_ingredients.all().delete()
            RecipeIngredient.objects.bulk_create(
                RecipeIngredient(recipe=recipe, **item) for item in ingredients)
        if steps is not None:
            recipe.steps.all().delete()
            RecipeStep.objects.bulk_create(
                RecipeStep(recipe=recipe, position=n, text=text) for n, text in enumerate(steps, start=1))

    @transaction.atomic
    def create(self, validated_data):
        ingredients = validated_data.pop('ingredients')
        steps = validated_data.pop('steps')
        recipe = Recipe.objects.create(**validated_data)
        self.save_children(recipe, ingredients, steps)
        return recipe

    @transaction.atomic
    def update(self, instance, validated_data):
        ingredients = validated_data.pop('ingredients', None)
        steps = validated_data.pop('steps', None)
        for name, value in validated_data.items():
            setattr(instance, name, value)
        instance.save()
        self.save_children(instance, ingredients, steps)
        return instance


class AuthorListSerializer(serializers.ModelSerializer):
    recipes_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'display_name', 'avatar_url', 'recipes_count']


class AuthorDetailSerializer(AuthorListSerializer):
    class Meta(AuthorListSerializer.Meta):
        fields = ['id', 'display_name', 'avatar_url', 'bio', 'recipes_count']
