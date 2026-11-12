import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_dir: Path
    lease_seconds: int = 20
    activity_seconds: int = 45
    runtime_mode: str = "fixture"

    @classmethod
    def local(cls):
        data = Path(os.environ.get("BID_DATA_DIR", ROOT / "data")).resolve()
        return cls(
            os.environ.get("BID_DATABASE_URL", f"sqlite:///{data / 'bid.db'}"),
            data,
            runtime_mode=os.environ.get("BID_RUNTIME_MODE", "fixture"),
        )
