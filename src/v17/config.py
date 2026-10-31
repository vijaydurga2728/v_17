from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="V17_", env_file=".env", extra="ignore")

    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])
    data_root: Path | None = None
    dukascopy_csv_dir: Path | None = None
    log_level: str = "INFO"

    telegram_token: str = ""
    telegram_chat_id: str = ""
    starting_equity: Decimal = Decimal("10000")
    news_filter_enabled: bool = True
    news_window_min: int = 2
    db_path: Path | None = None

    mt5_login: int = 0
    mt5_password: str = ""
    mt5_server: str = ""

    @property
    def data(self) -> Path:
        return self.data_root or (self.project_root / "data")

    @property
    def parquet_root(self) -> Path:
        return self.data / "parquet"

    @property
    def calendar_root(self) -> Path:
        return self.data / "calendar"

    @property
    def state_root(self) -> Path:
        return self.data / "state"

    @property
    def logs_root(self) -> Path:
        return self.project_root / "logs"

    @property
    def db(self) -> Path:
        return self.db_path if self.db_path is not None else self.state_root / "v17.db"

    def ensure_dirs(self) -> None:
        for p in (
            self.data,
            self.parquet_root,
            self.calendar_root,
            self.state_root,
            self.logs_root,
        ):
            p.mkdir(parents=True, exist_ok=True)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        config_toml = Path(__file__).resolve().parents[2] / "config.toml"
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
        ]
        if config_toml.exists():
            sources.append(TomlConfigSettingsSource(settings_cls, toml_file=config_toml))
        sources.append(file_secret_settings)
        return tuple(sources)


def get_settings() -> Settings:
    return Settings()
