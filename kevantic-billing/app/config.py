from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg2://billing:billing@localhost:5433/kevantic_billing"
    )
    admin_user: str = "billing.admin"
    admin_password: str = "ChangeMe-Strong-Billing!"
    company_name: str = "Kevantic Cyber Security Private Limited"
    company_gstin: str = ""
    company_state: str = "Maharashtra"
    company_state_code: str = "27"
    company_address: str = "India"
    default_currency: str = "INR"
    lut_filed: bool = False
    quote_validity_days: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=_env(
            "DATABASE_URL",
            "postgresql+psycopg2://billing:billing@localhost:5433/kevantic_billing",
        ),
        admin_user=_env("BILLING_ADMIN_USER", "billing.admin"),
        admin_password=_env("BILLING_ADMIN_PASSWORD", "ChangeMe-Strong-Billing!"),
        company_name=_env(
            "BILLING_COMPANY_NAME", "Kevantic Cyber Security Private Limited"
        ),
        company_gstin=_env("BILLING_COMPANY_GSTIN", ""),
        company_state=_env("BILLING_COMPANY_STATE", "Maharashtra"),
        company_state_code=_env("BILLING_COMPANY_STATE_CODE", "27"),
        company_address=_env("BILLING_COMPANY_ADDRESS", "India"),
        default_currency=_env("BILLING_DEFAULT_CURRENCY", "INR"),
        lut_filed=_env("BILLING_LUT_FILED", "false").lower() in ("1", "true", "yes"),
        quote_validity_days=int(_env("BILLING_QUOTE_VALIDITY_DAYS", "30")),
    )


def _env(key: str, default: str) -> str:
    import os

    return os.environ.get(key, default)
