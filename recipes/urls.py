from django.urls import path

from . import views

urlpatterns = [
    path("categories", views.CategoryListView.as_view()),
    path("categories/<int:pk>", views.CategoryDetailView.as_view()),
    path("cuisines", views.CuisineListView.as_view()),
    path("cuisines/<int:pk>", views.CuisineDetailView.as_view()),
    path("ingredients", views.IngredientListView.as_view()),
    path("ingredients/<int:pk>", views.IngredientDetailView.as_view()),
    path("recipes", views.RecipeListView.as_view()),
    path("recipes/<int:pk>", views.RecipeDetailView.as_view()),
    path("authors", views.AuthorListView.as_view()),
    path("authors/<int:pk>", views.AuthorDetailView.as_view()),
    path("about", views.AboutView.as_view()),
]
