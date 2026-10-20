from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_database: str = "medflow"
    # no default value here because a wrong secret key value can cause the app to start up 
    # seemingly successfully but with a silent failure because it will pass an incorrect 
    # secret key value for our JWT
    secret_key : str
    frontend_origin : str = "http://localhost:5173"

    # tells pydantic settings to actually read from backend/.env and fill these fields from it
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

# without the .env file setting values, this line will raise an error on startup
settings = Settings()