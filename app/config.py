from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    app_env: str = "development"
    app_title: str = "AI Medical Chatbot API"
    app_version: str = "2.0.0"

    # Authentication — all segment routers use X-API-Key header
    api_key: str = "changeme-api-key"

    # Database (PostgreSQL async)
    database_url: str = "postgresql+asyncpg://postgres:admin123@localhost:5432/ehr_db"

    # LLM — Google Gemini
    google_api_key: str = "your-google-api-key-here"
    llm_model: str = "gemini-3.1-flash-lite"
    llm_provider: str = "gemini"

    # Safety rules file path (relative to project root)
    safety_rules_path: str = "app/rules/safety_rules.json"

    # JWT Security settings
    secret_key: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    @property
    def GROK_API_KEY(self) -> str:
        return self.grok_api_key or self.xai_api_key

    # Aliases for compatibility
    @property
    def SECRET_KEY(self) -> str:
        return self.secret_key

    @property
    def ALGORITHM(self) -> str:
        return self.algorithm

    @property
    def ACCESS_TOKEN_EXPIRE_MINUTES(self) -> int:
        return self.access_token_expire_minutes

    @property
    def DATABASE_URL(self) -> str:
        return self.database_url

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

