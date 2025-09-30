from __future__ import annotations

import os
import time
from typing import Optional
from django.conf import settings
from redis import Redis


class DisplayPool:
    def __init__(self,
                 redis: Optional[Redis] = None,
                 base_display: int = None,
                 pool_size: int = None,
                 namespace: str = "displays",
                 lease_ttl_seconds: Optional[int] = None):
        self.r = redis or Redis(host=os.environ.get("REDIS_HOST", "127.0.0.1"), port=int(os.environ.get("REDIS_PORT", 6379)), db=0)
        self.base = base_display if base_display is not None else int(getattr(settings, "DISPLAY_BASE", 99))
        self.size = pool_size if pool_size is not None else int(getattr(settings, "DISPLAY_POOL_SIZE", 5))
        self.ns = namespace
        self.lease_ttl = int(lease_ttl_seconds) if lease_ttl_seconds is not None else int(getattr(settings, "DISPLAY_LEASE_TTL", 120))

    def _key(self, suffix: str) -> str:
        return f"{self.ns}:{suffix}"

    def seed_if_needed(self) -> None:
        init_key = self._key("initialized")
        # Use SETNX semantics to avoid duplicate seeding under races
        did_set = self.r.set(init_key, 1, nx=True)
        if not did_set:
            print("[DisplayPool] Already initialized; skipping seed")
            return
        print(f"[DisplayPool] Seeding displays from :{self.base} size={self.size}")
        pipe = self.r.pipeline()
        for i in range(self.size):
            disp = f":{self.base + i}"
            pipe.rpush(self._key("free"), disp)
        pipe.execute()

    def acquire(self, run_id: int, block_timeout: int = 0) -> str:
        """Acquire a display; blocks if none free. Returns display like ":99"."""
        self.seed_if_needed()
        print(f"[DisplayPool] Waiting to acquire display for run={run_id}")
        # BLMOVE free -> leased (RIGHT->LEFT) with optional blocking timeout
        disp = self.r.execute_command("BLMOVE", self._key("free"), self._key("leased"), "RIGHT", "LEFT", block_timeout)
        if disp is None:
            # Timed out without resource
            raise TimeoutError("No display available")
        disp = disp.decode("utf-8") if isinstance(disp, (bytes, bytearray)) else disp
        # Create a lease key with TTL
        self.r.set(self._key(f"lease:{disp}"), run_id, ex=self.lease_ttl)
        print(f"[DisplayPool] Acquired display {disp} for run={run_id}")
        return disp

    def heartbeat(self, disp: str, extend_seconds: int = None) -> None:
        ttl = int(extend_seconds or self.lease_ttl)
        self.r.expire(self._key(f"lease:{disp}"), ttl)
        print(f"[DisplayPool] Heartbeat display={disp} ttl={ttl}s")

    def release(self, disp: str) -> None:
        pipe = self.r.pipeline()
        pipe.lrem(self._key("leased"), 1, disp)
        pipe.lpush(self._key("free"), disp)
        pipe.delete(self._key(f"lease:{disp}"))
        pipe.execute()
        print(f"[DisplayPool] Released display {disp}")

    def reap_expired(self) -> int:
        """Scan leases and reclaim any expired displays. Returns count reclaimed."""
        reclaimed = 0
        for i in range(self.size):
            disp = f":{self.base + i}"
            key = self._key(f"lease:{disp}")
            if not self.r.exists(key):
                # Ensure it's in free
                # Remove any leftover from leased then LPUSH free
                pipe = self.r.pipeline()
                pipe.lrem(self._key("leased"), 0, disp)
                pipe.lrem(self._key("free"), 0, disp)
                pipe.lpush(self._key("free"), disp)
                pipe.execute()
                reclaimed += 1
        if reclaimed:
            print(f"[DisplayPool] Reclaimed {reclaimed} expired display(s)")
        return reclaimed


