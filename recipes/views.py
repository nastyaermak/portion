import logging

from django.contrib.auth import get_user_model
from django.db.models import Count, F, FloatField, Prefetch, Sum
from django.db.models.functions import Cast, Lower
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from config.errors import Conflict
from config.pagination import paginate, positive_int
from config.schema import ERROR_400, ERROR_401, ERROR_403, ERROR_404
from users.permissions import (
    IsAdminOrReadOnly,
    IsAuthenticatedOrReadOnly,
    IsAuthorOrAdminOrReadOnly,
)

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

logger = logging.getLogger("portion.recipes")

RECIPE_PAGE = inline_serializer(
    "RecipePage",
    fields={
        "count": serializers.IntegerField(),
        "page": serializers.IntegerField(),
        "page_size": serializers.IntegerField(),
        "results": RecipeListSerializer(many=True),
    },
)

RECIPE_EXAMPLE = OpenApiExample(
    "Новий рецепт",
    value={
        "title": "Омлет зі шпинатом",
        "description": "Швидкий сніданок",
        "image_url": "",
        "cook_time_min": 10,
        "servings": 1,
        "category_id": 1,
        "cuisine_id": 1,
        "ingredients": [
            {"ingredient_id": 1, "amount_g": 120, "note": "2 шт."},
            {"ingredient_id": 2, "amount_g": 50},
        ],
        "steps": ["Збити яйця", "Додати шпинат і смажити 5 хвилин"],
    },
    request_only=True,
)

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
    Змінювати довідники може тільки адміністратор.
    """

    permission_classes = [IsAdminOrReadOnly]
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
    # Додати інгредієнт може будь-який залогінений користувач,
    # бо без нього не вийде додати рецепт
    permission_classes = [IsAuthenticatedOrReadOnly]

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
    # Змінити чи видалити інгредієнт — тільки адміністратор,
    # бо від нього залежить КБЖВ чужих рецептів
    permission_classes = [IsAdminOrReadOnly]

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
    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        tags=["Рецепти"],
        summary="Каталог рецептів",
        operation_id="recipes_list",
        description=(
            "Список рецептів з КБЖВ на порцію, з пошуком, фільтрами, "
            "сортуванням і сторінками. Доступно без входу."
        ),
        parameters=[
            OpenApiParameter("search", str, description="Пошук у назві"),
            OpenApiParameter(
                "ingredient",
                int,
                many=True,
                description="id інгредієнта; можна кілька разів",
            ),
            OpenApiParameter("category", int, description="id категорії"),
            OpenApiParameter("cuisine", int, description="id кухні"),
            OpenApiParameter("author", int, description="id автора"),
            OpenApiParameter(
                "max_time", OpenApiTypes.NUMBER, description="Макс. хвилин"
            ),
            OpenApiParameter(
                "max_kcal",
                OpenApiTypes.NUMBER,
                description="Макс. ккал на порцію",
            ),
            OpenApiParameter(
                "min_protein",
                OpenApiTypes.NUMBER,
                description="Мін. білка (г) на порцію",
            ),
            OpenApiParameter(
                "sort",
                str,
                enum=list(SORTS),
                default="-created_at",
                description="Сортування",
            ),
            OpenApiParameter("page", int, default=1),
            OpenApiParameter("page_size", int, default=20),
        ],
        responses={200: RECIPE_PAGE, 400: ERROR_400},
    )
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

    @extend_schema(
        tags=["Рецепти"],
        summary="Додати рецепт",
        operation_id="recipes_create",
        description=(
            "Потрібен вхід (JWT). Автором стає залогінений користувач. "
            "КБЖВ не передається — сервер рахує його з інгредієнтів."
        ),
        request=RecipeWriteSerializer,
        responses={
            201: RecipeDetailSerializer,
            400: ERROR_400,
            401: ERROR_401,
        },
        examples=[RECIPE_EXAMPLE],
    )
    def post(self, request):
        serializer = RecipeWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Автор — завжди той, хто залогінений
        recipe = serializer.save(author=request.user)
        logger.info(
            "Recipe created: id=%s by user id=%s", recipe.pk, request.user.pk
        )
        return Response(
            RecipeDetailSerializer(
                recipe_detail_queryset().get(pk=recipe.pk)
            ).data,
            status=status.HTTP_201_CREATED,
        )


class RecipeDetailView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly, IsAuthorOrAdminOrReadOnly]

    def get_object(self, pk):
        recipe = get_or_404(
            recipe_detail_queryset(), pk, f"Рецепта з id {pk} немає"
        )
        self.check_object_permissions(self.request, recipe)
        return recipe

    @extend_schema(
        tags=["Рецепти"],
        summary="Рецепт повністю",
        operation_id="recipes_retrieve",
        description="Інгредієнти, кроки й КБЖВ на порцію. Доступно без входу.",
        responses={200: RecipeDetailSerializer, 404: ERROR_404},
    )
    def get(self, request, pk):
        return Response(RecipeDetailSerializer(self.get_object(pk)).data)

    @extend_schema(
        tags=["Рецепти"],
        summary="Змінити рецепт",
        operation_id="recipes_partial_update",
        description=(
            "Тільки автор рецепта або адміністратор. Можна передати лише "
            "частину полів; ingredients і steps замінюються повністю."
        ),
        request=RecipeWriteSerializer,
        responses={
            200: RecipeDetailSerializer,
            400: ERROR_400,
            401: ERROR_401,
            403: ERROR_403,
            404: ERROR_404,
        },
        examples=[
            OpenApiExample(
                "Змінити кількість порцій",
                value={"servings": 2},
                request_only=True,
            )
        ],
    )
    def patch(self, request, pk):
        serializer = RecipeWriteSerializer(
            self.get_object(pk), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        logger.info(
            "Recipe updated: id=%s by user id=%s, fields=%s",
            pk,
            request.user.pk,
            sorted(serializer.validated_data),
        )
        return Response(RecipeDetailSerializer(self.get_object(pk)).data)

    @extend_schema(
        tags=["Рецепти"],
        summary="Видалити рецепт",
        operation_id="recipes_destroy",
        description="Тільки автор рецепта або адміністратор.",
        responses={
            204: None,
            401: ERROR_401,
            403: ERROR_403,
            404: ERROR_404,
        },
    )
    def delete(self, request, pk):
        self.get_object(pk).delete()
        logger.info("Recipe deleted: id=%s by user id=%s", pk, request.user.pk)
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
