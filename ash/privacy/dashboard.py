"""Everything the window's Privacy tab shows, gathered in one call:
offline mode, each online feature and your choice for it, what Ash
stores and where, and the network log. Qt-free, so it's tested
directly; the window runs snapshot() on the command worker thread
(ash/gui/bridge.py) and only draws the result."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from ash.config import Config
from ash.privacy import consent, inventory, network_log
from ash.privacy.egress import FEATURES


@dataclass(frozen=True)
class FeatureRow:
    key: str
    name: str
    service: str
    sends: str
    purpose: str
    websites: str
    status: str             # consent.GRANTED / DENIED / UNASKED
    by_setup: bool          # no yes/no of its own (see OnlineFeature.consent_by_config)
    fixed_reason: str
    in_use: bool            # set up and switched on


@dataclass(frozen=True)
class StoredRow:
    key: str
    name: str
    purpose: str
    kept: str
    sensitive: bool
    encrypted: bool
    stored: bool
    size_bytes: int


@dataclass(frozen=True)
class Snapshot:
    offline_mode: bool
    features: list[FeatureRow]
    stored: list[StoredRow]
    network: list[dict]     # newest first
    summary: str


def _status(feature) -> str:
    if feature.consent_by_config:
        return consent.GRANTED
    return consent.status(feature.key)


def snapshot(config: Config, now: datetime | None = None) -> Snapshot:
    now = now or datetime.now()
    features = [
        FeatureRow(
            key=f.key, name=f.name, service=f.service, sends=f.sends, purpose=f.purpose,
            websites="your own setting" if f.any_domain else ", ".join(f.domains),
            status=_status(f), by_setup=f.consent_by_config, fixed_reason=f.fixed_reason,
            in_use=f.in_use(config),
        )
        for f in FEATURES.values()
    ]
    stored = []
    for item in inventory.INVENTORY:
        files = inventory.existing_files(item)
        stored.append(StoredRow(
            key=item.key, name=item.name, purpose=item.purpose, kept=item.kept,
            sensitive=item.sensitive, encrypted=item.encrypted, stored=bool(files),
            size_bytes=sum(p.stat().st_size for p in files if p.is_file()),
        ))
    recent = network_log.entries(since=now - timedelta(days=network_log.RETENTION_DAYS))
    recent.sort(key=lambda e: e.get("at", ""), reverse=True)
    return Snapshot(
        offline_mode=consent.offline_mode(), features=features, stored=stored,
        network=recent, summary=network_log.summary(days=7, now=now),
    )


def set_allowed(feature_key: str, allowed: bool) -> None:
    """The dashboard's per-feature switch; the same record as saying
    "allow web search" / "stop allowing web search"."""
    if allowed:
        consent.grant(feature_key)
    else:
        consent.deny(feature_key)
