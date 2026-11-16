"""
Offline tests for the Goddard MLX Copilot Engine (Milestone 2).

All tests run 100% offline — no network, no MLX, no HuggingFace downloads.
Covers VRAM Profiler, Model Cache Manager, MLX Engine Offline Fallback,
Interactive Review Engine, Autonomous Goal Engine, and all FastAPI Endpoints.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from goddard.copilot.cache_manager import ModelCacheManager
from goddard.copilot.vram_profiler import VRAMProfiler
from goddard.ui.app import app

# ─────────────────────────────────────────────────────────────────────────────
# Class 1: TestVRAMProfiler
# ─────────────────────────────────────────────────────────────────────────────


class TestVRAMProfiler:
    """Tests for VRAMProfiler hardware tier mapping, mock env vars, and sysctl integration."""

    def _make_profiler(self):
        from goddard.copilot.vram_profiler import VRAMProfiler

        return VRAMProfiler()

    def _mock_sysctl(self, gib: float):
        """Return a CompletedProcess mock returning *gib* GiB in bytes."""
        bytes_val = int(gib * 1024**3)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = str(bytes_val)
        return mock_result

    @pytest.mark.parametrize(
        "ram_gib,expected_tier,expected_quant,expected_ctx",
        [
            (4.0, "entry", "4-bit", 4096),
            (7.9, "entry", "4-bit", 4096),
            (8.0, "entry", "4-bit", 4096),
            (15.9, "entry", "4-bit", 4096),
            (16.0, "pro", "4-bit", 8192),
            (18.0, "pro", "4-bit", 8192),
            (31.9, "pro", "4-bit", 8192),
            (32.0, "pro", "4-bit", 8192),
            (36.0, "max", "8-bit", 16384),
            (64.0, "max", "8-bit", 16384),
        ],
    )
    def test_tier_mapping(self, ram_gib, expected_tier, expected_quant, expected_ctx):
        profiler = self._make_profiler()
        with patch("subprocess.run", return_value=self._mock_sysctl(ram_gib)):
            profile = profiler.get_profile()

        assert profile["tier"] == expected_tier, f"RAM={ram_gib} GiB: expected tier={expected_tier}"
        assert profile["default_quantization"] == expected_quant
        assert profile["default_context_length"] == expected_ctx
        assert "recommended_repo" in profile
        assert "physical_ram_gib" in profile

    def test_entry_repo(self):
        profiler = self._make_profiler()
        with patch("subprocess.run", return_value=self._mock_sysctl(8.0)):
            profile = profiler.get_profile()
        assert "Llama-3.2-3B" in profile["recommended_repo"]

    def test_pro_repo(self):
        profiler = self._make_profiler()
        with patch("subprocess.run", return_value=self._mock_sysctl(18.0)):
            profile = profiler.get_profile()
        assert "Qwen2.5-Coder-7B" in profile["recommended_repo"]
        assert "4bit" in profile["recommended_repo"]

    def test_max_repo(self):
        profiler = self._make_profiler()
        with patch("subprocess.run", return_value=self._mock_sysctl(64.0)):
            profile = profiler.get_profile()
        assert "Qwen2.5-Coder-7B" in profile["recommended_repo"]
        assert "8bit" in profile["recommended_repo"]

    def test_sysctl_error_fallback(self):
        """On subprocess error, get_physical_ram_gib should return 8.0."""
        profiler = self._make_profiler()
        with patch("subprocess.run", side_effect=OSError("no sysctl")):
            ram = profiler.get_physical_ram_gib()
        assert ram == 8.0

    def test_sysctl_nonzero_exit_fallback(self):
        """Non-zero returncode triggers fallback to 8.0."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        profiler = self._make_profiler()
        with patch("subprocess.run", return_value=mock_result):
            ram = profiler.get_physical_ram_gib()
        assert ram == 8.0

    def test_mock_ram_bytes_env_var(self, monkeypatch):
        """GODDARD_MOCK_RAM_BYTES overrides sysctl."""
        profiler = self._make_profiler()
        bytes_val = int(18.0 * (1024**3))
        monkeypatch.setenv("GODDARD_MOCK_RAM_BYTES", str(bytes_val))
        profile = profiler.get_profile()
        assert profile["tier"] == "pro"
        assert profile["physical_ram_gib"] == 18.0

    def test_profile_keys(self):
        profiler = self._make_profiler()
        with patch("subprocess.run", return_value=self._mock_sysctl(18.0)):
            profile = profiler.get_profile()
        expected_keys = {
            "physical_ram_gib",
            "tier",
            "default_quantization",
            "default_context_length",
            "recommended_repo",
            "recommended_model",
            "kv_cache_limit_tokens",
        }
        assert expected_keys == set(profile.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Class 2: TestModelCacheManager
# ─────────────────────────────────────────────────────────────────────────────


class TestModelCacheManager:
    """Tests for ModelCacheManager cache scanning, path validation, and mock download."""

    def _make_manager(self, cache_dir=None):
        from goddard.copilot.cache_manager import ModelCacheManager

        return ModelCacheManager(cache_dir=cache_dir)

    def test_list_nonexistent_cache_returns_empty(self, tmp_path):
        """list_cached_models on non-existent cache_dir returns []."""
        manager = self._make_manager(cache_dir=tmp_path / "does_not_exist")
        result = manager.list_cached_models()
        assert result == []

    def test_list_empty_cache_returns_empty(self, tmp_path):
        """Empty cache_dir returns []."""
        manager = self._make_manager(cache_dir=tmp_path)
        result = manager.list_cached_models()
        assert result == []

    def test_is_model_cached_false_when_no_cache(self, tmp_path):
        manager = self._make_manager(cache_dir=tmp_path / "empty")
        assert manager.is_model_cached("mlx-community/some-model") is False

    def test_get_model_path_none_when_not_cached(self, tmp_path):
        manager = self._make_manager(cache_dir=tmp_path / "empty")
        assert manager.get_model_path("mlx-community/some-model") is None

    def test_list_cached_model(self, tmp_path):
        """Correctly detects a model directory following HF hub layout."""
        manager = self._make_manager(cache_dir=tmp_path)

        # Simulate: models--mlx-community--Qwen2.5-Coder-7B-Instruct-4bit/snapshots/<hash>/
        model_dir = tmp_path / "models--mlx-community--Qwen2.5-Coder-7B-Instruct-4bit"
        snapshot_dir = model_dir / "snapshots" / "abc123"
        snapshot_dir.mkdir(parents=True)
        (snapshot_dir / "model.safetensors").write_bytes(b"fake")

        result = manager.list_cached_models()
        assert len(result) == 1
        assert result[0]["repo_id"] == "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
        assert isinstance(result[0]["size_gib"], float)
        assert result[0]["is_mlx"] is True

    def test_is_model_cached_true(self, tmp_path):
        manager = self._make_manager(cache_dir=tmp_path)
        repo_id = "mlx-community/test-model"
        snapshot_dir = tmp_path / "models--mlx-community--test-model" / "snapshots" / "deadbeef"
        snapshot_dir.mkdir(parents=True)
        (snapshot_dir / "dummy.safetensors").write_bytes(b"x")

        assert manager.is_model_cached(repo_id) is True

    def test_get_model_path_returns_path(self, tmp_path):
        manager = self._make_manager(cache_dir=tmp_path)
        repo_id = "mlx-community/test-model"
        snapshot_dir = tmp_path / "models--mlx-community--test-model" / "snapshots" / "deadbeef"
        snapshot_dir.mkdir(parents=True)

        path = manager.get_model_path(repo_id)
        assert path == snapshot_dir

    def test_download_model_raises_import_error_without_hf(self, tmp_path):
        """Raises ImportError if huggingface_hub is not installed during live download."""
        import sys

        manager = self._make_manager(cache_dir=tmp_path)
        with patch.dict(sys.modules, {"huggingface_hub": None}):
            with pytest.raises(ImportError, match="huggingface_hub"):
                manager.download_model("some/model", offline_mock=False)

    def test_validate_repo_id_security(self):
        from goddard.copilot.cache_manager import ModelCacheManager

        assert (
            ModelCacheManager.validate_repo_id("mlx-community/Qwen2.5-Coder-7B-Instruct-4bit")
            is True
        )
        assert ModelCacheManager.validate_repo_id("../../etc/passwd") is False
        assert ModelCacheManager.validate_repo_id("/root/model") is False
        assert ModelCacheManager.validate_repo_id("invalid-repo-format") is False

    def test_download_model_offline_mock(self, tmp_path):
        """offline_mock=True creates valid snapshot directory with zero socket calls."""
        manager = self._make_manager(cache_dir=tmp_path)
        repo_id = "mlx-community/test-mock-model"
        path = manager.download_model(repo_id, offline_mock=True)
        assert path.exists()
        assert (path / "config.json").exists()
        assert (path / "model.safetensors").exists()
        progress = manager.get_download_progress(repo_id)
        assert progress["status"] == "complete"
        assert progress["percent_complete"] == 100.0

    def test_get_catalog_structure(self, tmp_path):
        manager = self._make_manager(cache_dir=tmp_path)
        catalog = manager.get_catalog()
        assert "models" in catalog
        assert "preset_catalog" in catalog
        assert "cached_models" in catalog
        tiers = {m["tier"] for m in catalog["models"]}
        assert {"entry", "pro", "max"}.issubset(tiers)


# ─────────────────────────────────────────────────────────────────────────────
# Class 3: TestMLXEngine
# ─────────────────────────────────────────────────────────────────────────────


class TestMLXEngine:
    """Tests for MLXEngine offline fallback and aerospace heuristic behaviour."""

    def _make_engine(self, repo_id: str = "test/model"):
        from goddard.copilot.mlx_engine import MLXEngine

        return MLXEngine(repo_id=repo_id)

    def test_is_mlx_available_returns_bool(self):
        from goddard.copilot.mlx_engine import MLXEngine

        result = MLXEngine.is_mlx_available()
        assert isinstance(result, bool)

    def test_generate_without_mlx_returns_nonempty(self):
        """When MLX is not loaded, generate() returns non-empty heuristic."""
        engine = self._make_engine()
        assert engine._loaded is False
        result = engine.generate("optimize apogee for the rocket")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_returns_valid_json(self):
        """Heuristic response must be valid JSON matching review schema."""
        engine = self._make_engine()
        result = engine.generate("check apogee target")
        parsed = json.loads(result)
        assert "summary" in parsed
        assert "modifications" in parsed
        assert "rationale" in parsed
        assert "confidence" in parsed
        assert "engine" in parsed

    def test_offline_heuristic_apogee(self):
        engine = self._make_engine()
        result = engine._offline_heuristic("increase apogee to 45000m")
        parsed = json.loads(result)
        assert "propellant_mass_kg" in parsed["modifications"]
        assert parsed["modifications"]["propellant_mass_kg"]["unit"] == "kg"

    def test_offline_heuristic_stress(self):
        engine = self._make_engine()
        result = engine._offline_heuristic("reduce peak von Mises stress on airframe")
        parsed = json.loads(result)
        assert "wall_thickness_mm" in parsed["modifications"]
        assert parsed["modifications"]["wall_thickness_mm"]["unit"] == "mm"

    def test_offline_heuristic_payload(self):
        engine = self._make_engine()
        result = engine._offline_heuristic("Increase payload mass to 10kg")
        parsed = json.loads(result)
        assert "payload_mass_kg" in parsed["modifications"]
        assert parsed["modifications"]["payload_mass_kg"]["new"] == 10.0
        assert parsed["modifications"]["payload_mass_kg"]["unit"] == "kg"

    def test_offline_heuristic_twr(self):
        engine = self._make_engine()
        result = engine._offline_heuristic("maintain 1.5 liftoff TWR")
        parsed = json.loads(result)
        assert "chamber_pressure_mpa" in parsed["modifications"]
        assert parsed["modifications"]["chamber_pressure_mpa"]["unit"] == "MPa"

    def test_offline_heuristic_flutter(self):
        engine = self._make_engine()
        result = engine._offline_heuristic("minimize fin flutter and aeroelastic instability")
        parsed = json.loads(result)
        assert "fin_root_chord_m" in parsed["modifications"]
        assert parsed["modifications"]["fin_root_chord_m"]["unit"] == "m"

    def test_stream_generate_offline_yields_nonempty(self):
        engine = self._make_engine()
        chunks = list(engine.stream_generate("test prompt"))
        assert len(chunks) >= 1
        assert all(isinstance(c, str) for c in chunks)
        full = "".join(chunks)
        assert len(full) > 0

    def test_load_does_not_raise_without_mlx(self):
        """load() must not raise even when mlx_lm is absent."""
        engine = self._make_engine()
        engine.load()
        assert engine._loaded is False

    def test_default_repo_id_from_profiler(self):
        """When repo_id=None, it picks up recommended repo from VRAMProfiler."""
        from goddard.copilot.mlx_engine import MLXEngine

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = str(int(18.0 * 1024**3))
        with patch("subprocess.run", return_value=mock_result):
            engine = MLXEngine()
        assert "Qwen2.5" in engine.repo_id


# ─────────────────────────────────────────────────────────────────────────────
# Class 4: TestInteractiveReviewEngine
# ─────────────────────────────────────────────────────────────────────────────


class TestInteractiveReviewEngine:
    """Tests for InteractiveReviewEngine propose_review and apply_diff."""

    def _make_review_engine(self):
        from goddard.copilot.interactive_review import InteractiveReviewEngine
        from goddard.copilot.mlx_engine import MLXEngine

        engine = MLXEngine(repo_id="test/model")
        return InteractiveReviewEngine(engine)

    def test_propose_review_returns_required_keys(self):
        review_engine = self._make_review_engine()
        params = {"propellant_mass_kg": 100.0, "wall_thickness_mm": 2.0}
        result = review_engine.propose_review("improve apogee", params)
        assert isinstance(result, dict)
        assert "summary" in result
        assert "modifications" in result
        assert "rationale" in result
        assert "reasoning" in result
        assert "confidence" in result
        assert "engine" in result

    def test_propose_review_modifications_structured_diff(self):
        review_engine = self._make_review_engine()
        params = {"propellant_mass_kg": 100.0}
        result = review_engine.propose_review("apogee target not met", params)
        mods = result["modifications"]
        assert isinstance(mods, dict)
        for _key, diff in mods.items():
            assert "old" in diff and "new" in diff and "unit" in diff

    def test_propose_review_empty_intent_fallback(self):
        review_engine = self._make_review_engine()
        result = review_engine.propose_review("", {"payload_mass_kg": 4.0})
        assert "summary" in result
        assert "modifications" in result

    def test_propose_review_negative_dimensions_rejected(self):
        review_engine = self._make_review_engine()
        with pytest.raises(ValueError, match="negative"):
            review_engine.propose_review("increase apogee", {"body_radius_m": -1.0})

    def test_apply_diff_updates_params(self):
        review_engine = self._make_review_engine()
        params = {"propellant_mass_kg": 100.0, "wall_thickness_mm": 2.0}
        modifications = {
            "propellant_mass_kg": {"old": 100.0, "new": 110.0},
        }
        new_params = review_engine.apply_diff(modifications, params)
        assert new_params["propellant_mass_kg"] == 110.0
        assert new_params["wall_thickness_mm"] == 2.0

    def test_apply_diff_does_not_mutate_original(self):
        review_engine = self._make_review_engine()
        params = {"mass": 50.0}
        mods = {"mass": {"old": 50.0, "new": 60.0}}
        new_params = review_engine.apply_diff(mods, params)
        assert params["mass"] == 50.0
        assert new_params["mass"] == 60.0

    def test_apply_to_cad_and_resimulate_nominal(self, tmp_designs_dir, monkeypatch):
        monkeypatch.setenv("GODDARD_DESIGNS_DIR", str(tmp_designs_dir))
        review_engine = self._make_review_engine()
        mods = {"propellant_mass_kg": {"old": 18.2, "new": 22.0, "unit": "kg"}}
        result = review_engine.apply_to_cad_and_resimulate(mods, base_revision_id=1)
        assert result["status"] == "applied"
        assert result["new_revision_id"] > 1
        assert "sizing_metrics" in result

    def test_apply_to_cad_and_resimulate_zero_changes(self, tmp_designs_dir, monkeypatch):
        monkeypatch.setenv("GODDARD_DESIGNS_DIR", str(tmp_designs_dir))
        review_engine = self._make_review_engine()
        result = review_engine.apply_to_cad_and_resimulate({}, base_revision_id=1)
        assert result["status"] == "no_changes"

    def test_apply_to_cad_and_resimulate_non_numeric_rejected(self, tmp_designs_dir, monkeypatch):
        monkeypatch.setenv("GODDARD_DESIGNS_DIR", str(tmp_designs_dir))
        review_engine = self._make_review_engine()
        mods = {"propellant_mass_kg": {"old": 18.2, "new": "not_a_number"}}
        with pytest.raises(ValueError, match="Non-numeric"):
            review_engine.apply_to_cad_and_resimulate(mods, base_revision_id=1)


# ─────────────────────────────────────────────────────────────────────────────
# Class 5: TestAutonomousGoalEngine
# ─────────────────────────────────────────────────────────────────────────────


class TestAutonomousGoalEngine:
    """Tests for AutonomousGoalEngine closed-loop multi-physics optimisation."""

    def _make_goal_engine(self, physics_runner=None):
        from goddard.copilot.autonomous_goal import AutonomousGoalEngine
        from goddard.copilot.interactive_review import InteractiveReviewEngine
        from goddard.copilot.mlx_engine import MLXEngine

        engine = MLXEngine(repo_id="test/model")
        review_engine = InteractiveReviewEngine(engine)
        return AutonomousGoalEngine(review_engine, physics_runner)

    def test_empty_targets_raises_value_error(self):
        """optimize() with empty targets must raise ValueError."""
        goal_engine = self._make_goal_engine()
        with pytest.raises(ValueError, match="targets cannot be empty"):
            goal_engine.optimize(targets={}, initial_params={"x": 1})

    def test_already_satisfied_converges_at_iteration_0(self):
        """When initial_params already meet all targets, exit immediately."""

        def physics_runner(params):
            return {"apogee_m": 60000.0, "revision_id": 1}

        goal_engine = self._make_goal_engine(physics_runner=physics_runner)
        result = goal_engine.optimize(
            targets={"apogee_m": 50000.0},
            initial_params={"propellant_mass_kg": 100.0},
        )
        assert result["status"] == "converged"
        assert result["iterations"] == 0
        assert result["margins_met"] is True

    def test_directional_constraints_upper_bound_stress(self):
        """Upper bound metrics (e.g. von Mises stress <= 200 MPa) evaluate correctly."""

        def physics_runner(params):
            return {"von_mises_stress_mpa": 150.0, "revision_id": 1}

        goal_engine = self._make_goal_engine(physics_runner=physics_runner)
        result = goal_engine.optimize(
            targets={"von_mises_stress_mpa": 200.0},
            initial_params={"wall_thickness_mm": 2.0},
        )
        assert result["status"] == "converged"
        assert result["iterations"] == 0
        assert result["margins_met"] is True

    def test_unsatisfiable_constraints_fail_after_max_iterations(self):
        """When physics never meets targets, return 'failed' after max_iterations."""

        def physics_runner(params):
            return {"apogee_m": 1000.0}

        goal_engine = self._make_goal_engine(physics_runner=physics_runner)
        result = goal_engine.optimize(
            targets={"apogee_m": 999999.0},
            initial_params={"propellant_mass_kg": 50.0},
            max_iterations=3,
        )
        assert result["status"] == "failed"
        assert result["iterations"] == 3
        assert result["margins_met"] is False

    def test_converges_on_second_iteration(self):
        """Converges when physics meets target on the second iteration."""
        call_count = {"n": 0}

        def physics_runner(params):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                return {"apogee_m": 55000.0, "revision_id": 42}
            return {"apogee_m": 30000.0, "revision_id": 1}

        goal_engine = self._make_goal_engine(physics_runner=physics_runner)
        result = goal_engine.optimize(
            targets={"apogee_m": 50000.0},
            initial_params={"propellant_mass_kg": 80.0},
            max_iterations=5,
        )
        assert result["status"] == "converged"
        assert result["iterations"] <= 5
        assert result["margins_met"] is True

    def test_result_has_required_keys(self):
        def physics_runner(params):
            return {"apogee_m": 1000.0}

        goal_engine = self._make_goal_engine(physics_runner=physics_runner)
        result = goal_engine.optimize(
            targets={"apogee_m": 999999.0},
            initial_params={"x": 1},
            max_iterations=1,
        )
        required_keys = {
            "status",
            "iterations",
            "iterations_run",
            "final_params",
            "margins_met",
            "history",
        }
        assert required_keys.issubset(set(result.keys()))


# ─────────────────────────────────────────────────────────────────────────────
# Class 6: TestCopilotFastAPIEndpoints
# ─────────────────────────────────────────────────────────────────────────────


class TestCopilotFastAPIEndpoints:
    """Tests for all 6 Copilot REST endpoints in goddard/ui/app.py."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_get_copilot_vram_nominal(self, client):
        res = client.get("/api/copilot/vram")
        assert res.status_code == 200
        data = res.json()
        assert "physical_ram_gib" in data
        assert "tier" in data
        assert "recommended_model" in data
        assert "recommended_repo" in data
        assert "default_quantization" in data
        assert "default_context_length" in data
        assert "kv_cache_limit_tokens" in data

    def test_get_copilot_vram_mock_tiers(self, client, monkeypatch):
        # Entry tier: 8 GiB
        monkeypatch.setenv("GODDARD_MOCK_RAM_BYTES", str(int(8.0 * (1024**3))))
        res = client.get("/api/copilot/vram")
        assert res.json()["tier"] == "entry"

        # Pro tier: 18 GiB
        monkeypatch.setenv("GODDARD_MOCK_RAM_BYTES", str(int(18.0 * (1024**3))))
        res = client.get("/api/copilot/vram")
        assert res.json()["tier"] == "pro"

        # Max tier: 48 GiB
        monkeypatch.setenv("GODDARD_MOCK_RAM_BYTES", str(int(48.0 * (1024**3))))
        res = client.get("/api/copilot/vram")
        assert res.json()["tier"] == "max"

    def test_get_copilot_models_catalog(self, client):
        res = client.get("/api/copilot/models")
        assert res.status_code == 200
        data = res.json()
        assert "models" in data
        assert "preset_catalog" in data
        assert "cached_models" in data

    def test_post_copilot_download_offline(self, client):
        res = client.post(
            "/api/copilot/models/download",
            json={"repo_id": "mlx-community/test-model", "offline_mock": True},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "complete"
        assert data["percent_complete"] == 100.0

    def test_post_copilot_download_path_traversal_400(self, client):
        res = client.post(
            "/api/copilot/models/download",
            json={"repo_id": "../../etc/passwd", "offline_mock": True},
        )
        assert res.status_code == 400

    def test_get_copilot_models_progress(self, client):
        res = client.get("/api/copilot/models/progress?repo_id=mlx-community/test-model")
        assert res.status_code == 200
        data = res.json()
        assert "status" in data
        assert "percent_complete" in data

    def test_post_copilot_review_nominal(self, client):
        res = client.post(
            "/api/copilot/review",
            json={
                "intent": "Increase apogee to 45000m",
                "current_params": {"propellant_mass_kg": 18.2, "payload_mass_kg": 4.0},
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert "summary" in data
        assert "modifications" in data
        assert "propellant_mass_kg" in data["modifications"]
        assert "unit" in data["modifications"]["propellant_mass_kg"]

    def test_post_copilot_review_empty_intent_fallback(self, client):
        res = client.post(
            "/api/copilot/review",
            json={"intent": "", "current_params": {"payload_mass_kg": 4.0}},
        )
        assert res.status_code == 200
        assert "summary" in res.json()

    def test_post_copilot_review_negative_dimensions_422(self, client):
        res = client.post(
            "/api/copilot/review",
            json={"intent": "increase payload", "current_params": {"body_radius_m": -1.0}},
        )
        assert res.status_code == 422

    def test_post_copilot_apply_nominal(self, client, tmp_designs_dir, monkeypatch):
        monkeypatch.setenv("GODDARD_DESIGNS_DIR", str(tmp_designs_dir))
        res = client.post(
            "/api/copilot/apply",
            json={
                "base_revision_id": 1,
                "modifications": {"chamber_pressure_mpa": {"old": 3.0, "new": 4.5, "unit": "MPa"}},
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "applied"
        assert "new_revision_id" in data
        assert data["sizing_metrics"]["chamber_pressure_mpa"] == 4.5

    def test_post_copilot_apply_zero_modifications(self, client, tmp_designs_dir, monkeypatch):
        monkeypatch.setenv("GODDARD_DESIGNS_DIR", str(tmp_designs_dir))
        res = client.post(
            "/api/copilot/apply",
            json={"base_revision_id": 1, "modifications": {}},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "no_changes"

    def test_post_copilot_apply_non_numeric_422(self, client, tmp_designs_dir, monkeypatch):
        monkeypatch.setenv("GODDARD_DESIGNS_DIR", str(tmp_designs_dir))
        res = client.post(
            "/api/copilot/apply",
            json={"base_revision_id": 1, "modifications": {"propellant_mass_kg": {"new": "abc"}}},
        )
        assert res.status_code == 422

    def test_post_copilot_optimize_nominal(self, client, tmp_designs_dir, monkeypatch):
        monkeypatch.setenv("GODDARD_DESIGNS_DIR", str(tmp_designs_dir))
        res = client.post(
            "/api/copilot/optimize",
            json={"target_apogee_m": 4500.0, "max_iterations": 2},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ("converged", "failed", "max_iterations_reached")
        assert "iterations_run" in data
        assert "history" in data

    def test_post_copilot_optimize_empty_targets_400(self, client):
        res = client.post("/api/copilot/optimize", json={"targets": {}})
        assert res.status_code == 400

    def test_post_copilot_review_string_negative_dimensions_422(self, client):
        res = client.post(
            "/api/copilot/review",
            json={"intent": "increase payload", "current_params": {"payload_mass_kg": "-5.0"}},
        )
        assert res.status_code == 422

    def test_post_copilot_apply_negative_dimensions_422(self, client, tmp_designs_dir, monkeypatch):
        monkeypatch.setenv("GODDARD_DESIGNS_DIR", str(tmp_designs_dir))
        res = client.post(
            "/api/copilot/apply",
            json={"base_revision_id": 1, "modifications": {"wall_thickness_mm": -2.0}},
        )
        assert res.status_code == 422
        res2 = client.post(
            "/api/copilot/apply",
            json={"base_revision_id": 1, "modifications": {"wall_thickness_mm": "-2.0"}},
        )
        assert res2.status_code == 422

    def test_get_copilot_models_format_list(self, client):
        res = client.get("/api/copilot/models?format=list")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

        res_hdr = client.get(
            "/api/copilot/models", headers={"Accept": "application/json; format=list"}
        )
        assert res_hdr.status_code == 200
        assert isinstance(res_hdr.json(), list)

    def test_validate_repo_id_trailing_newline_rejected(self):
        assert not ModelCacheManager.validate_repo_id("repo/model\n")
        assert not ModelCacheManager.validate_repo_id("repo/model\r")

    def test_vram_profiler_zero_mock_bytes(self, monkeypatch):
        monkeypatch.setenv("GODDARD_MOCK_RAM_BYTES", "0")
        profiler = VRAMProfiler()
        p = profiler.get_profile()
        assert p["physical_ram_gib"] == 0.0
        assert p["tier"] == "entry"

    def test_cache_manager_ignores_incomplete_and_tmp_files(self, tmp_path):
        sub = tmp_path / "test_dir"
        sub.mkdir()
        (sub / "real.bin").write_bytes(b"a" * 1024 * 1024)
        (sub / "file.incomplete").write_bytes(b"b" * 1024 * 1024)
        (sub / "file.tmp").write_bytes(b"c" * 1024 * 1024)
        size_gib = ModelCacheManager._dir_size_gib(sub)
        # Should only count real.bin (1 MB = 1/1024 GiB)
        assert abs(size_gib - (1.0 / 1024)) < 1e-6
