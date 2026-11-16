"""
Adaptive VRAM / Physical RAM profiler for Apple Silicon MLX model selection.

Uses ``sysctl hw.memsize`` (or GODDARD_MOCK_RAM_BYTES env var) to detect unified
memory and maps it to the appropriate quantization tier, context length, and
HuggingFace model repo.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TypedDict


class VRAMProfile(TypedDict):
    physical_ram_gib: float
    tier: str  # "entry" | "pro" | "max"
    default_quantization: str  # "4-bit" | "8-bit"
    default_context_length: int  # 4096 | 8192 | 16384
    recommended_repo: str
    recommended_model: str
    kv_cache_limit_tokens: int


class VRAMProfiler:
    """Detects physical RAM and returns an appropriate MLX model profile."""

    # ── Tier thresholds (GiB) ────────────────────────────────────────────────
    # (max_gib_inclusive, tier, quantization, context_length, recommended_repo)
    _TIERS = [
        (
            16.0,  # strictly < 16.0 is entry
            "entry",
            "4-bit",
            4096,
            "mlx-community/Llama-3.2-3B-Instruct-4bit",
        ),
        (
            32.0,  # 16.0 <= ram <= 32.0 is pro (covers host 18 GiB and 32 GiB edge)
            "pro",
            "4-bit",
            8192,
            "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
        ),
        (
            float("inf"),  # > 32.0 is max (48 GiB, 64 GiB, 128 GiB)
            "max",
            "8-bit",
            16384,
            "mlx-community/Qwen2.5-Coder-7B-Instruct-8bit",
        ),
    ]

    def get_physical_ram_gib(self) -> float:
        """Return physical RAM in GiB.

        Priority:
        1. GODDARD_MOCK_RAM_BYTES env var (if valid int)
        2. macOS sysctl -n hw.memsize
        3. Fallback to 8.0 GiB (safe default entry tier)
        """
        mock_bytes = os.environ.get("GODDARD_MOCK_RAM_BYTES")
        if mock_bytes is not None and mock_bytes.strip():
            try:
                bytes_val = int(mock_bytes.strip())
                if bytes_val >= 0:
                    return round(bytes_val / (1024**3), 2)
            except (ValueError, TypeError):
                pass

        if sys.platform == "darwin":
            try:
                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip().isdigit():
                    bytes_val = int(result.stdout.strip())
                    if bytes_val > 0:
                        return round(bytes_val / (1024**3), 2)
            except Exception:
                pass

        return 8.0

    def get_profile(self) -> dict:
        """Return hardware-adaptive MLX model profile dict.

        Returns
        -------
        dict with keys:
            physical_ram_gib, tier, default_quantization,
            default_context_length, recommended_repo,
            recommended_model, kv_cache_limit_tokens
        """
        ram_gib = self.get_physical_ram_gib()

        if ram_gib < 16.0:
            tier = "entry"
            quant = "4-bit"
            ctx = 4096
            repo = "mlx-community/Llama-3.2-3B-Instruct-4bit"
        elif ram_gib <= 32.0:
            tier = "pro"
            quant = "4-bit"
            ctx = 8192
            repo = "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
        else:
            tier = "max"
            quant = "8-bit"
            ctx = 16384
            repo = "mlx-community/Qwen2.5-Coder-7B-Instruct-8bit"

        return {
            "physical_ram_gib": ram_gib,
            "tier": tier,
            "default_quantization": quant,
            "default_context_length": ctx,
            "recommended_repo": repo,
            "recommended_model": repo,
            "kv_cache_limit_tokens": ctx,
        }

    def get_vram_profile(self) -> dict:
        """Alias for get_profile()."""
        return self.get_profile()


def get_vram_profile() -> dict:
    """Module-level convenience function returning current VRAM profile."""
    return VRAMProfiler().get_profile()
