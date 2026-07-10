from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str

    # 한국투자증권
    kis_virtual: bool = False
    kis_app_key: str
    kis_app_secret: str
    kis_rest_domain: str
    kis_websocket_domain: str
    kis_virtual_rest_domain: str
    kis_virtual_websocket_domain: str


settings = Settings()
