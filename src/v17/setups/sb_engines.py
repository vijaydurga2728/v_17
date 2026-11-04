"""Six Silver Bullet engine configurations per spec section 4."""
from dataclasses import dataclass
from typing import Literal

EntryModel = Literal["CE", "AGGRESSIVE"]


@dataclass(frozen=True)
class SBEngineConfig:
    engine_id: str
    window_ny: tuple[str, str]
    entry_model: EntryModel
    symbols: tuple[str, ...]
    priority_order: int


ENGINE_CATALOG: list[SBEngineConfig] = [
    SBEngineConfig("SB-LDN-CE",  ("03:00", "04:00"), "CE",         ("EURUSD", "GBPUSD"), 1),
    SBEngineConfig("SB-LDN-AG",  ("03:00", "04:00"), "AGGRESSIVE", ("EURUSD", "GBPUSD"), 2),
    SBEngineConfig("SB-NYAM-CE", ("10:00", "11:00"), "CE",         ("USATECHIDXUSD", "EURUSD", "GBPUSD"), 3),
    SBEngineConfig("SB-NYAM-AG", ("10:00", "11:00"), "AGGRESSIVE", ("USATECHIDXUSD", "EURUSD", "GBPUSD"), 4),
    SBEngineConfig("SB-NYPM-CE", ("14:00", "15:00"), "CE",         ("USATECHIDXUSD",), 5),
    SBEngineConfig("SB-NYPM-AG", ("14:00", "15:00"), "AGGRESSIVE", ("USATECHIDXUSD",), 6),
]
