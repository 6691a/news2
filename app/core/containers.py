from dependency_injector import containers, providers

from app.core.config import settings as app_settings
from app.core.database import Database


class Container(containers.DeclarativeContainer):
    """애플리케이션 인프라 의존성을 조립한다."""

    settings = providers.Object(app_settings)
    database = providers.Singleton(
        Database,
        database_url=settings.provided.database_url,
    )


container = Container()
