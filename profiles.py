import json
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional


@dataclass
class SyncProfile:
    name: str
    source_path: str
    target_path: str
    profile_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = ""
    last_run_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SyncProfile":
        return cls(
            profile_id=data.get("profile_id", uuid.uuid4().hex[:12]),
            name=data.get("name", ""),
            source_path=data.get("source_path", ""),
            target_path=data.get("target_path", ""),
            created_at=data.get("created_at", ""),
            last_run_at=data.get("last_run_at", ""),
        )


class ProfileManager:
    def __init__(self, storage_path: Optional[str] = None):
        if storage_path is None:
            storage_path = str(Path.home() / ".syncmaster_profiles.json")
        self.storage_path = Path(storage_path)
        self.profiles: List[SyncProfile] = []
        self._load()

    def _load(self) -> None:
        if not self.storage_path.exists():
            self.profiles = []
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.profiles = [SyncProfile.from_dict(item) for item in data.get("profiles", [])]
        except (json.JSONDecodeError, OSError):
            self.profiles = []

    def _save(self) -> None:
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {"profiles": [p.to_dict() for p in self.profiles]}
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def add_profile(self, profile: SyncProfile) -> bool:
        if self.find_by_name(profile.name):
            return False
        from datetime import datetime
        if not profile.created_at:
            profile.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.profiles.append(profile)
        self._save()
        return True

    def update_profile(self, profile: SyncProfile) -> bool:
        for i, p in enumerate(self.profiles):
            if p.profile_id == profile.profile_id:
                self.profiles[i] = profile
                self._save()
                return True
        return False

    def delete_profile(self, profile_id: str) -> bool:
        for i, p in enumerate(self.profiles):
            if p.profile_id == profile_id:
                del self.profiles[i]
                self._save()
                return True
        return False

    def find_by_id(self, profile_id: str) -> Optional[SyncProfile]:
        for p in self.profiles:
            if p.profile_id == profile_id:
                return p
        return None

    def find_by_name(self, name: str) -> Optional[SyncProfile]:
        for p in self.profiles:
            if p.name == name:
                return p
        return None

    def get_all(self) -> List[SyncProfile]:
        return list(self.profiles)

    def update_last_run(self, profile_id: str) -> None:
        from datetime import datetime
        profile = self.find_by_id(profile_id)
        if profile:
            profile.last_run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save()
