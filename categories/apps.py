from django.apps import AppConfig


class CategoriesConfig(AppConfig):
    name = 'categories'

    def ready(self):
        import categories.signals  # noqa: F401
