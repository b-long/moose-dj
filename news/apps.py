from django.apps import AppConfig


class NewsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "news"

    def ready(self) -> None:
        """
        This 'ready()' function will be executed during project startup.

        The AppConfig.ready() hook [1] is provided by Django to allow
        Django developers to perform "app" initialization work.

        [1]: https://docs.djangoproject.com/en/4.2/ref/applications/#django.apps.AppConfig.ready

        """
        # return super().ready()

        msg = "Custom app starting up"

        print(msg)
