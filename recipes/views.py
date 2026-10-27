from django.contrib.auth import get_user_model
from django.db.models import Count, F, FloatField, Prefetch, Sum
from django.db.models.functions import Cast, Lower
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from config.errors import Conflict
from config.pagination import paginate, positive_int

from .models import Category, Cuisine, Ingredient, Recipe, RecipeIngredient
from .serializers import (
    AuthorDetailSerializer,
    AuthorListSerializer,
    CategorySerializer,
    CuisineSerializer,
    IngredientSerializer,
    RecipeDetailSerializer,
    RecipeListSerializer,
    RecipeWriteSerializer,
)

User = get_user_model()

SORTS = {
    "kcal": ["kcal", "id"],
    "-kcal": ["-kcal", "id"],
    "-protein": ["-protein", "id"],
    "time": ["cook_time_min", "id"],
    "-created_at": ["-created_at", "-id"],
}


def plural(n, one, few, many):
    """Українська форма слова після числа: 1 рецепт, 3 рецепти, 5 рецептів."""
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} {few}"
    return f"{n} {many}"


def recipes_word(n):
    return plural(n, "рецепт", "рецепти", "рецептів")


def get_or_404(queryset, pk, message):
    """Об'єкт за id або 404 з поясненням."""
    obj = queryset.filter(pk=pk).first()
    if obj is None:
        raise NotFound(message)
    return obj


def with_nutrition(queryset):
    """Додає до рецептів КБЖВ на порцію.

    КБЖВ порції = сума (грами / 100 × КБЖВ на 100 г) / кількість порцій.
    """

    def per_serving(field):
        total = Sum(
            Cast(F("recipe_ingredients__amount_g"), FloatField())
            * Cast(F(f"recipe_ingredients__ingredient__{field}"), FloatField())
        )
        return total / 100.0 / Cast(F("servings"), FloatField())

    return queryset.select_related("category", "cuisine", "author").annotate(
        kcal=per_serving("kcal_100g"),
        protein=per_serving("protein_100g"),
        fat=per_serving("fat_100g"),
        carbs=per_serving("carbs_100g"),
    )


def recipe_detail_queryset():
    return with_nutrition(Recipe.objects.all()).prefetch_related(
        Prefetch(
            "recipe_ingredients",
            queryset=RecipeIngredient.objects.select_related("ingredient"),
        ),
        "steps",
    )


def search_filter(queryset, field, text):
    """Пошук без урахування регістру, зокрема для кирилиці.

    Див. recipes/apps.py.
    """
    text = text.strip()
    if not text:
        return queryset
    return queryset.annotate(search_field=Lower(field)).filter(
        search_field__contains=text.lower()
    )


def number_param(request, name):
    """Числовий фільтр з query-параметрів; нечислове значення — 400."""
    raw = request.query_params.get(name)
    if raw is None or raw == "":
        return None
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        raise ValidationError({name: "Має бути числом"})
    if value < 0:
        raise ValidationError({name: "Не може бути від'ємним"})
    return value


class DictionaryListView(APIView):
    """Спільне для категорій і кухонь.

    GET — перелік (без сторінок), POST — додати.
    """

    model = None
    serializer_class = None

    def get_queryset(self):
        return self.model.objects.annotate(recipes_count=Count("recipes"))

    def get(self, request):
        return Response(
            self.serializer_class(self.get_queryset(), many=True).data
        )

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(
            self.serializer_class(self.get_queryset().get(pk=obj.pk)).data,
            status=status.HTTP_201_CREATED,
        )


class DictionaryDetailView(DictionaryListView):
    """GET, PATCH, DELETE одного запису довідника."""

    not_found = ""
    delete_conflict = ""

    def get_object(self, pk):
        return get_or_404(
            self.get_queryset(), pk, self.not_found.format(id=pk)
        )

    def get(self, request, pk):
        return Response(self.serializer_class(self.get_object(pk)).data)

    def patch(self, request, pk):
        obj = self.get_object(pk)
        serializer = self.serializer_class(
            obj, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(self.serializer_class(self.get_object(pk)).data)

    def delete(self, request, pk):
        obj = self.get_object(pk)
        if obj.recipes_count:
            raise Conflict(
                self.delete_conflict.format(
                    name=obj.name, recipes=recipes_word(obj.recipes_count)
                )
            )
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CategoryListView(DictionaryListView):
    model = Category
    serializer_class = CategorySerializer


class CategoryDetailView(DictionaryDetailView):
    model = Category
    serializer_class = CategorySerializer
    not_found = "Категорії з id {id} немає"
    delete_conflict = (
        "Неможливо видалити категорію «{name}», бо в ній {recipes}. "
        "Спершу перенесіть рецепти в іншу категорію або видаліть їх."
    )


class CuisineListView(DictionaryListView):
    model = Cuisine
    serializer_class = CuisineSerializer


class CuisineDetailView(DictionaryDetailView):
    model = Cuisine
    serializer_class = CuisineSerializer
    not_found = "Кухні з id {id} немає"
    delete_conflict = (
        "Неможливо видалити кухню «{name}», бо до неї належать {recipes}. "
        "Спершу перенесіть рецепти в іншу кухню або видаліть їх."
    )


def ingredient_queryset():
    return Ingredient.objects.annotate(
        recipes_count=Count("recipe_ingredients")
    )


class IngredientListView(APIView):
    def get(self, request):
        queryset = ingredient_queryset()
        queryset = search_filter(
            queryset, "name", request.query_params.get("search", "")
        )
        return Response(paginate(request, queryset, IngredientSerializer))

    def post(self, request):
        serializer = IngredientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(
            IngredientSerializer(ingredient_queryset().get(pk=obj.pk)).data,
            status=status.HTTP_201_CREATED,
        )


class IngredientDetailView(APIView):
    def get_object(self, pk):
        return get_or_404(
            ingredient_queryset(), pk, f"Інгредієнта з id {pk} немає"
        )

    def get(self, request, pk):
        return Response(IngredientSerializer(self.get_object(pk)).data)

    def patch(self, request, pk):
        serializer = IngredientSerializer(
            self.get_object(pk), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(IngredientSerializer(self.get_object(pk)).data)

    def delete(self, request, pk):
        obj = self.get_object(pk)
        if obj.recipes_count:
            used_in = plural(
                obj.recipes_count, "рецепті", "рецептах", "рецептах"
            )
            raise Conflict(
                f"Неможливо видалити інгредієнт «{obj.name}», "
                f"бо він використовується в {used_in}. "
                "Спершу приберіть його з рецептів."
            )
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RecipeListView(APIView):
    def get(self, request):
        params = request.query_params
        queryset = Recipe.objects.all()

        queryset = search_filter(queryset, "title", params.get("search", ""))
        for raw in params.getlist("ingredient"):
            if not raw.isdigit():
                raise ValidationError(
                    {"ingredient": "Має бути id інгредієнта (ціле число)"}
                )
            queryset = queryset.filter(
                id__in=RecipeIngredient.objects.filter(
                    ingredient_id=int(raw)
                ).values("recipe_id")
            )
        for name in ("category", "cuisine", "author"):
            value = positive_int(request, name)
            if value is not None:
                queryset = queryset.filter(**{f"{name}_id": value})
        max_time = number_param(request, "max_time")
        if max_time is not None:
            queryset = queryset.filter(cook_time_min__lte=max_time)

        queryset = with_nutrition(queryset)
        max_kcal = number_param(request, "max_kcal")
        if max_kcal is not None:
            queryset = queryset.filter(kcal__lte=max_kcal)
        min_protein = number_param(request, "min_protein")
        if min_protein is not None:
            queryset = queryset.filter(protein__gte=min_protein)

        sort = params.get("sort", "-created_at")
        if sort not in SORTS:
            raise ValidationError(
                {
                    "sort": (
                        f"Невідоме сортування «{sort}». "
                        f"Можна: {', '.join(SORTS)}"
                    )
                }
            )
        queryset = queryset.order_by(*SORTS[sort])
        return Response(paginate(request, queryset, RecipeListSerializer))

    def post(self, request):
        serializer = RecipeWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recipe = serializer.save()
        return Response(
            RecipeDetailSerializer(
                recipe_detail_queryset().get(pk=recipe.pk)
            ).data,
            status=status.HTTP_201_CREATED,
        )


class RecipeDetailView(APIView):
    def get_object(self, pk):
        return get_or_404(
            recipe_detail_queryset(), pk, f"Рецепта з id {pk} немає"
        )

    def get(self, request, pk):
        return Response(RecipeDetailSerializer(self.get_object(pk)).data)

    def patch(self, request, pk):
        serializer = RecipeWriteSerializer(
            self.get_object(pk), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(RecipeDetailSerializer(self.get_object(pk)).data)

    def delete(self, request, pk):
        self.get_object(pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def author_queryset():
    """Автор — користувач, який опублікував хоча б один рецепт."""
    return User.objects.annotate(recipes_count=Count("recipes")).filter(
        recipes_count__gt=0
    )


class AuthorListView(APIView):
    def get(self, request):
        queryset = author_queryset().order_by("display_name", "id")
        queryset = search_filter(
            queryset, "display_name", request.query_params.get("search", "")
        )
        return Response(paginate(request, queryset, AuthorListSerializer))


class AuthorDetailView(APIView):
    def get(self, request, pk):
        author = get_or_404(author_queryset(), pk, f"Автора з id {pk} немає")
        return Response(AuthorDetailSerializer(author).data)


class AboutView(APIView):
    def get(self, request):
        return Response(
            {
                "description": (
                    "Порція — сайт рецептів з КБЖВ на порцію "
                    "і планом харчування."
                ),
                "contacts": {
                    "email": "hello@portion.example",
                    "telegram": "@portion_recipes",
                },
                "nutrition_info": (
                    "КБЖВ рахується з інгредієнтів за даними на 100 г "
                    "і ділиться на кількість порцій. Значення орієнтовні."
                ),
                "disclaimer": (
                    "Сайт не замінює консультацію лікаря чи дієтолога."
                ),
            }
        )
