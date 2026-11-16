"""
HuggingFace model cache manager for the Goddard MLX Copilot Engine.

Manages ``~/.cache/huggingface/hub`` snapshot directories: listing cached
models, checking presence, resolving paths, and downloading via
``huggingface_hub.snapshot_download`` or deterministic offline mock.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any


class ModelCacheManager:
    """Inspect and manage the local HuggingFace model snapshot cache."""

    _MODEL_PREFIX = "models--"
    _downloads: dict[str, dict[str, Any]] = {}

    PRESET_MODELS: list[dict[str, Any]] = [
        {
            "repo_id": "mlx-community/Llama-3.2-3B-Instruct-4bit",
            "name": "Llama 3.2 3B Instruct (4-bit)",
            "tier": "entry",
            "quantization": "4-bit",
            "context_length": 4096,
            "recommended_vram_gib": 8.0,
            "size_gib": 2.0,
            "is_mlx": True,
            "description": "Ultra-lightweight embedded copilot for machines with <16 GiB RAM.",
        },
        {
            "repo_id": "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
            "name": "Qwen 2.5 Coder 7B Instruct (4-bit)",
            "tier": "pro",
            "quantization": "4-bit",
            "context_length": 8192,
            "recommended_vram_gib": 18.0,
            "size_gib": 4.5,
            "is_mlx": True,
            "description": "High-accuracy code and parametric reasoning copilot for 16-32 GiB unified memory.",
        },
        {
            "repo_id": "mlx-community/Qwen2.5-Coder-7B-Instruct-8bit",
            "name": "Qwen 2.5 Coder 7B Instruct (8-bit)",
            "tier": "max",
            "quantization": "8-bit",
            "context_length": 16384,
            "recommended_vram_gib": 32.0,
            "size_gib": 8.0,
            "is_mlx": True,
            "description": "High-fidelity 8-bit quantized copilot with extended 16k context for >=32 GiB unified memory.",
        },
    ]

    def __init__(self, cache_dir: Path | str | None = None) -> None:
        if cache_dir is not None:
            self.cache_dir = Path(cache_dir)
        elif os.environ.get("GODDARD_CACHE_DIR"):
            self.cache_dir = Path(os.environ["GODDARD_CACHE_DIR"])
        elif os.environ.get("HUGGINGFACE_HUB_CACHE"):
            self.cache_dir = Path(os.environ["HUGGINGFACE_HUB_CACHE"])
        elif os.environ.get("HF_HUB_CACHE"):
            self.cache_dir = Path(os.environ["HF_HUB_CACHE"])
        elif os.environ.get("HF_HOME"):
            self.cache_dir = Path(os.environ["HF_HOME"]) / "hub"
        else:
            self.cache_dir = Path.home() / ".cache" / "huggingface" / "hub"

        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _repo_id_to_dir_name(self, repo_id: str) -> str:
        """Convert ``org/name`` to ``models--org--name``."""
        return self._MODEL_PREFIX + repo_id.replace("/", "--")

    def _dir_name_to_repo_id(self, dir_name: str) -> str:
        """Convert ``models--org--name`` back to ``org/name``."""
        without_prefix = dir_name[len(self._MODEL_PREFIX) :]
        return without_prefix.replace("--", "/", 1)

    def _get_snapshot_dir(self, repo_id: str) -> Path | None:
        """Return the first valid snapshot directory for *repo_id*, or None."""
        model_dir = self.cache_dir / self._repo_id_to_dir_name(repo_id)
        snapshots_dir = model_dir / "snapshots"
        if not snapshots_dir.exists():
            return None
        snapshots = [
            p
            for p in snapshots_dir.iterdir()
            if p.is_dir() and not p.name.endswith(".incomplete") and not p.name.endswith(".tmp")
        ]
        return snapshots[0] if snapshots else None

    @staticmethod
    def _dir_size_gib(path: Path) -> float:
        """Recursively compute directory size in GiB."""
        total = sum(
            f.stat().st_size
            for f in path.rglob("*")
            if f.is_file() and not f.name.endswith(".incomplete") and not f.name.endswith(".tmp")
        )
        return total / (1024**3)

    @staticmethod
    def validate_repo_id(repo_id: str) -> bool:
        """Validate repo_id against path traversal and illegal characters."""
        if not repo_id or not isinstance(repo_id, str):
            return False
        if ".." in repo_id or repo_id.startswith("/") or repo_id.endswith("/"):
            return False
        if repo_id.count("/") != 1:
            return False
        pattern = r"^[a-zA-Z0-9_\-\.]+\/[a-zA-Z0-9_\-\.]+\Z"
        return bool(re.match(pattern, repo_id))

    # ── Public API ───────────────────────────────────────────────────────────

    def list_cached_models(self) -> list[dict[str, Any]]:
        """Scan *cache_dir* and return metadata for every cached model.

        Returns
        -------
        list of dicts with keys: ``repo_id``, ``size_gib``, ``is_mlx``, ``cached``
        """
        if not self.cache_dir.exists():
            return []

        results: list[dict[str, Any]] = []
        for entry in self.cache_dir.iterdir():
            if not entry.is_dir():
                continue
            if not entry.name.startswith(self._MODEL_PREFIX):
                continue
            if entry.name.endswith(".incomplete") or entry.name.endswith(".tmp"):
                continue

            repo_id = self._dir_name_to_repo_id(entry.name)
            snapshots_dir = entry / "snapshots"
            if not snapshots_dir.exists():
                continue

            snapshot_dirs = [
                p
                for p in snapshots_dir.iterdir()
                if p.is_dir() and not p.name.endswith(".incomplete") and not p.name.endswith(".tmp")
            ]
            if not snapshot_dirs:
                continue

            snapshot = snapshot_dirs[0]
            size_gib = self._dir_size_gib(snapshot)
            is_mlx = any(snapshot.glob("*.safetensors")) and not any(
                snapshot.glob("pytorch_model*.bin")
            )

            results.append(
                {
                    "repo_id": repo_id,
                    "size_gib": round(size_gib, 3),
                    "is_mlx": is_mlx,
                    "cached": True,
                }
            )

        return results

    def is_model_cached(self, repo_id: str) -> bool:
        """Return True if a snapshot directory exists for *repo_id*."""
        return self._get_snapshot_dir(repo_id) is not None

    def get_model_path(self, repo_id: str) -> Path | None:
        """Return the snapshot directory path for *repo_id*, or None."""
        return self._get_snapshot_dir(repo_id)

    def get_model_size_gib(self, repo_id: str) -> float:
        """Return size in GiB for *repo_id* snapshot, or 0.0."""
        snapshot = self._get_snapshot_dir(repo_id)
        if snapshot is None:
            return 0.0
        return round(self._dir_size_gib(snapshot), 3)

    def get_catalog(self) -> dict[str, Any]:
        """Return unified catalog with preset models and cached models."""
        models: list[dict[str, Any]] = []
        preset_catalog: list[dict[str, Any]] = []

        for p in self.PRESET_MODELS:
            is_cached = self.is_model_cached(p["repo_id"])
            item = dict(p)
            item["cached"] = is_cached
            preset_catalog.append(item)
            models.append(item)

        cached_list = self.list_cached_models()
        for c in cached_list:
            if not any(m["repo_id"] == c["repo_id"] for m in models):
                models.append(
                    {
                        "repo_id": c["repo_id"],
                        "name": c["repo_id"].split("/")[-1],
                        "tier": "custom",
                        "quantization": "4-bit" if c.get("is_mlx") else "unknown",
                        "context_length": 8192,
                        "recommended_vram_gib": 16.0,
                        "size_gib": c["size_gib"],
                        "is_mlx": c["is_mlx"],
                        "cached": True,
                        "description": "Locally cached model snapshot.",
                    }
                )

        return {
            "models": models,
            "preset_catalog": preset_catalog,
            "cached_models": cached_list,
        }

    def get_download_progress(self, repo_id: str) -> dict[str, Any]:
        """Return download progress for *repo_id*."""
        if repo_id in self._downloads:
            return dict(self._downloads[repo_id])

        if self.is_model_cached(repo_id):
            size_gib = self.get_model_size_gib(repo_id)
            size_bytes = int(size_gib * (1024**3)) or 4294967296
            return {
                "repo_id": repo_id,
                "status": "complete",
                "bytes_downloaded": size_bytes,
                "total_bytes": size_bytes,
                "percent_complete": 100.0,
                "speed_str": "complete",
            }

        return {
            "repo_id": repo_id,
            "status": "idle",
            "bytes_downloaded": 0,
            "total_bytes": 0,
            "percent_complete": 0.0,
            "speed_str": "idle",
        }

    def download_model(
        self,
        repo_id: str,
        progress_callback: Callable[[float, str], None] | None = None,
        offline_mock: bool = False,
    ) -> Path:
        """Download or mock-snapshot *repo_id*."""
        if not self.validate_repo_id(repo_id):
            raise ValueError(f"Invalid repo_id: path traversal detected: {repo_id}")

        if not offline_mock:
            # Live download path requested — verify huggingface_hub dependency
            try:
                import huggingface_hub  # noqa: F401
            except ImportError as exc:
                raise ImportError(
                    "huggingface_hub is required to download models. "
                    "Install it with: pip install huggingface-hub"
                ) from exc

        if self._downloads.get(repo_id, {}).get("status") == "downloading":
            existing_path = self.get_model_path(repo_id)
            if existing_path is not None:
                return existing_path
            return self.cache_dir / self._repo_id_to_dir_name(repo_id) / "snapshots" / "main"

        if offline_mock:
            # Deterministic zero-socket local mock snapshot
            self._downloads[repo_id] = {
                "repo_id": repo_id,
                "status": "downloading",
                "bytes_downloaded": 0,
                "total_bytes": 4096,
                "percent_complete": 0.0,
                "speed_str": "starting…",
            }
            if progress_callback is not None:
                progress_callback(0.0, "starting…")

            snapshot_dir = (
                self.cache_dir / self._repo_id_to_dir_name(repo_id) / "snapshots" / "main"
            )
            snapshot_dir.mkdir(parents=True, exist_ok=True)

            config_file = snapshot_dir / "config.json"
            if not config_file.exists():
                config_file.write_text(
                    json.dumps(
                        {
                            "model_type": "qwen2",
                            "repo_id": repo_id,
                            "architectures": ["Qwen2ForCausalLM"],
                        },
                        indent=2,
                    )
                )

            weights_file = snapshot_dir / "model.safetensors"
            if not weights_file.exists():
                weights_file.write_bytes(b"\x00" * 4096)

            if progress_callback is not None:
                progress_callback(1.0, "done")

            self._downloads[repo_id] = {
                "repo_id": repo_id,
                "status": "complete",
                "bytes_downloaded": 4096,
                "total_bytes": 4096,
                "percent_complete": 100.0,
                "speed_str": "done",
            }
            return snapshot_dir

        # Live online download path
        try:
            import huggingface_hub  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "huggingface_hub is required to download models. "
                "Install it with: pip install huggingface-hub"
            ) from exc

        from huggingface_hub import snapshot_download

        if progress_callback is not None:
            progress_callback(0.0, "starting…")

        self._downloads[repo_id] = {
            "repo_id": repo_id,
            "status": "downloading",
            "bytes_downloaded": 0,
            "total_bytes": 1000000,
            "percent_complete": 0.0,
            "speed_str": "downloading",
        }

        local_dir = snapshot_download(repo_id=repo_id, cache_dir=str(self.cache_dir))

        self._downloads[repo_id] = {
            "repo_id": repo_id,
            "status": "complete",
            "bytes_downloaded": 1000000,
            "total_bytes": 1000000,
            "percent_complete": 100.0,
            "speed_str": "done",
        }

        if progress_callback is not None:
            progress_callback(1.0, "done")

        return Path(local_dir)
