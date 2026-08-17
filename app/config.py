from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    db_servername: str
    db_port: int = 3306
    db_username: str
    db_password: str

    db_name_origem: str
    db_name_destino: str

    # Compatibilidade com funções antigas
    db_name: str | None = None

    groq_api_key: str
    groq_model: str = (
        "llama-3.3-70b-versatile"
    )

    max_search_results: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def model_post_init(self, __context):
        if not self.db_name:
            self.db_name = self.db_name_destino


settings = Settings()