import hashlib
import asyncio
from typing import Dict, Optional
from actions.enterprise_feature_flag.schemas import FeatureFlagCreate, FlagStrategy

class EnterpriseFeatureFlagManager:
    def __init__(self):
        self.flags: Dict[str, FeatureFlagCreate] = {}
        self.lock = asyncio.Lock()

    async def upsert_flag(self, flag: FeatureFlagCreate) -> None:
        async with self.lock:
            self.flags[flag.name] = flag

    async def get_flag(self, name: str) -> Optional[FeatureFlagCreate]:
        async with self.lock:
            return self.flags.get(name)

    async def delete_flag(self, name: str) -> bool:
        async with self.lock:
            if name in self.flags:
                del self.flags[name]
                return True
            return False

    def _calculate_percentage(self, feature_name: str, user_id: str) -> int:
        """Deterministic hashing to ensure the same user always falls in the same bucket."""
        hash_input = f"{feature_name}:{user_id}".encode('utf-8')
        hash_val = hashlib.md5(hash_input).hexdigest()
        return int(hash_val[:8], 16) % 100

    async def evaluate(self, feature_name: str, user_id: str) -> bool:
        async with self.lock:
            flag = self.flags.get(feature_name)
            
            if not flag or not flag.enabled:
                return False

            if flag.strategy == FlagStrategy.BOOLEAN:
                return True
                
            elif flag.strategy == FlagStrategy.TARGETING:
                return user_id in flag.targeted_users
                
            elif flag.strategy == FlagStrategy.PERCENTAGE:
                if flag.rollout_percentage in (None, 0):
                    return False
                if flag.rollout_percentage == 100:
                    return True
                
                bucket = self._calculate_percentage(feature_name, user_id)
                return bucket < flag.rollout_percentage

            return False
