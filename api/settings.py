from pydantic import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@db:5432/opus"
    REDIS_URL: str = "redis://redis:6379/0"
    API_KEY: str = "dev-key"
    MEDIA_ROOT: str = "/data"
    MODEL_CACHE: str = "/data/models"

settings = Settings()
