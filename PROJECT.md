# Project: Goddard Native macOS Liquid Glass & MLX Copilot

## Architecture
Goddard is a production-ready aerospace engineering suite combining:
1. **Python Core & Physics Backend**: Multi-stage rocket sizing (`coupled_wer`), structural FEA (`fea_solver`), compressible aerodynamics CFD (`cfd_solver`), 6-DOF trajectory simulation (`flight_sim`), VTVL landing recovery (`vtvl_landing`), and Onshape CAD sync / offline mock mode (`MockOnshapeClient`).
2. **Apple Silicon MLX Copilot Engine**: Embedded in-process LLM agent with Metal GPU acceleration (`mlx-lm`), adaptive hardware VRAM profiling (`sysctl hw.memsize`), HuggingFace model cache management (`~/.cache/huggingface/hub`), Interactive Review Mode (parametric diffs), Autonomous Goal Mode (closed-loop multi-physics optimization), and deterministic offline heuristic fallback.
3. **Web Viewport & HUD Interface**: Single-page AppKit-hosted frontend with Three.js r128 WebGL viewport featuring alpha transparency (`scene.background = null`), floating HUD backdrop pill ("Liquid Glass", "Deep Space Dark", "CAD Studio Neutral"), 4 multi-physics shader overlays (Clean CAD Solid, FEA Stress Heatmap, CFD Cp Pressure, Gmsh Wireframe), 3D Revision Ghosting, CAD cloud sync drawer, Copilot drawer, Web Audio cues, and keyboard shortcuts.
4. **Native macOS AppKit Swift 6 Application (`macos/GoddardApp`)**: Borderless native window with `NSVisualEffectView` (`.behindWindow` blending, `.underWindowBackground` material, `.active` state, `titlebarAppearsTransparent = true`), transparent `WKWebView`, supervisor `DaemonManager` managing local Python FastAPI daemon lifecycle, typed IPC `BridgeHandler` dispatching `NSHapticFeedbackManager` pulses and `NSSound` cues, and standalone release packager/installer `build_app.sh`.

## Code Layout
- `goddard/`:
  - `goddard/ui/app.py`: FastAPI server serving static assets, health endpoints, CAD sync endpoints, mesh surface scalar extraction, and Copilot endpoints.
  - `goddard/ui/static/`: `index.html`, `app.js`, CSS styling, Three.js shaders, HUD controls, and audio/haptics/shortcut handlers.
  - `goddard/copilot/`:
    - `__init__.py`
    - `vram_profiler.py`: Adaptive RAM profiling via `sysctl hw.memsize`.
    - `cache_manager.py`: HuggingFace Hub model inspector & download tracking.
    - `mlx_engine.py`: MLX-LM Metal inference engine + offline heuristic fallback.
    - `interactive_review.py`: Parametric diff generator and CAD modification proposer.
    - `autonomous_goal.py`: Closed-loop iterative physics optimization loop.
- `macos/GoddardApp/`:
  - `Package.swift`: Swift 6 package definition with macOS 14+ deployment target.
  - `Sources/GoddardApp/`:
    - `main.swift`: Entrypoint & NSApplication startup.
    - `AppDelegate.swift`: Application lifecycle and main menu setup.
    - `MainWindowController.swift`: NSWindow + NSVisualEffectView + WKWebView setup.
    - `DaemonManager.swift`: Python daemon supervisor (spawn, `/health` polling, SIGTERM/SIGKILL).
    - `BridgeHandler.swift`: WKScriptMessageHandler handling haptics, sounds, window controls.
    - `VRAMProfiler.swift`: Swift-side hardware memory queries.
  - `scripts/`:
    - `build_app.sh`: Release compilation, `Goddard.app` bundle assembly, `AppIcon.icns` generation, `Info.plist` creation, codesign, and `--install` support.
- `tests/`:
  - Existing: `test_fea_cfd.py`, `test_mcp_server.py`, `test_sizing.py`, `test_ui_endpoints.py`, `test_vtvl.py`, `conftest.py`.
  - New Backend & Copilot tests: `test_health_cad.py`, `test_copilot.py`.
  - E2E Test Suite: `tests/e2e/`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Daemon Lifecycle & Health API | `/api/health` and `/api/lifecycle/shutdown` for supervisor tracking | M1 | Survey 1, Survey 3 |
| 2 | CAD Cloud Sync & Offline Mock API | `/api/cad/status`, `/api/cad/config`, `/api/cad/mode` and MockOnshapeClient integration | M1 | Survey 1, Survey 2 |
| 3 | 3D Multi-Physics Surface Scalar Data | Normalized von Mises stress field and CFD Cp pressure field in mesh extraction API | M1 | Survey 1, Survey 2 |
| 4 | Design Bundle ZIP Export Endpoint | Complete design bundle export endpoint and CLI export support | M1 | Survey 1 |
| 5 | Adaptive VRAM Profiler | Physical RAM auto-detection via `sysctl hw.memsize` to configure quantization and context length | M2 | Survey 1, Survey 3 |
| 6 | In-App Model Cache Manager | Manage `~/.cache/huggingface/hub` and track model downloads with live progress | M2 | Survey 1, Survey 3 |
| 7 | MLX Metal Engine & Offline Fallback | Metal-accelerated inference with offline aerospace heuristic fallback | M2 | Survey 1, Survey 3 |
| 8 | Interactive Review Mode | Parametric diff generation with "Apply to CAD & Re-Simulate" | M2 | Survey 1, Survey 2, Survey 3 |
| 9 | Autonomous Goal Mode | Closed-loop iterative physics optimization invoking sizing, FEA, and RocketPy | M2 | Survey 1, Survey 3 |
| 10 | Transparent WebGL Viewport | `scene.background = null`, `alpha: true`, transparent CSS for Liquid Glass desktop blur passthrough | M3 | Survey 2, Survey 3 |
| 11 | Floating 3D HUD Backdrop Pill | Toggles between Liquid Glass (blur), Deep Space Dark (#080c14), and CAD Studio Neutral (#222834) | M3 | Survey 2, Survey 3 |
| 12 | 3D Multi-Physics Overlays | HUD toggles for Clean CAD Solid, FEA Stress Heatmap, CFD Cp Pressure, and Gmsh Wireframe | M3 | Survey 2 |
| 13 | 3D Revision Ghosting | Translucent neon ghost of prior revision geometry behind active model | M3 | Survey 2 |
| 14 | In-App CAD Connection Drawer | Glass drawer with Connected vs Offline Mock status pills and credentials sheet | M4 | Survey 2 |
| 15 | Copilot Drawer & Diff Modal UI | Interactive Review Mode diff view, "Apply to CAD" button, and Autonomous Goal Mode panel | M4 | Survey 2, Survey 3 |
| 16 | Aerospace Audio Cues & Mute | Sound cues for simulation touchdown, completion, margin violations, with global mute | M4 | Survey 2, Survey 3 |
| 17 | Tactile Haptic Feedback | NSHapticFeedbackManager pulses triggered on button and CAD interactions | M4 | Survey 2, Survey 3 |
| 18 | Global Keyboard Shortcuts | Cmd+K, Cmd+R, Cmd+D, Cmd+E, Spacebar, Escape handling | M4 | Survey 2, Survey 3 |
| 19 | Swift 6 AppKit Application | Native macOS app with NSVisualEffectView, transparent WKWebView, and IPC bridge | M5 | Survey 3 |
| 20 | Subprocess Daemon Supervisor | Swift DaemonManager managing python daemon spawn, health polling, and clean SIGTERM/SIGKILL | M5 | Survey 3 |
| 21 | Standalone Build & App Packaging | `build_app.sh` compiling release binary, Info.plist with ATS allowances, AppIcon.icns | M5 | Survey 3 |
| 22 | System Installation (`--install`) | Copies `build/Goddard.app` into `/Applications/Goddard.app` with LaunchServices refresh | M5 | Survey 3 |
| 23 | E2E Opaque-Box Test Suite | 4-tier requirement-driven test suite validating all user requirements offline | E2E (DONE - published in TEST_READY.md) | Dual Track |
| 24 | Final Milestone Verification | 100% E2E test pass + Tier-5 adversarial coverage hardening | M6 | Final Gate |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Backend Daemon, CAD Sync & Physics Scalars | Health API, CAD status/config/mode, mesh scalar fields, bundle export | none | DONE |
| M2 | Embedded Apple Silicon MLX Copilot Engine | VRAM profiler, model cache manager, MLX engine + offline fallback, review & goal modes | M1 | DONE |
| M3 | 3D Viewport, Liquid Glass & Physics Overlays | Transparent WebGL canvas, HUD backdrop pill, 4 physics overlays, 3D revision ghosting | M1 | DONE |
| M4 | CAD Drawer, Copilot UI, Audio, Haptics & Shortcuts | In-app drawers, diff modal, audio synthesizer, IPC bridge, keyboard shortcuts | M2, M3 | IN_PROGRESS (sub_orch: sub_orch_m4) |
| M5 | Native Swift 6 AppKit App & Packaging / Install | Package.swift, NSVisualEffectView, DaemonManager, BridgeHandler, build_app.sh, --install | M1, M4 | PLANNED |
| M6 | Final Milestone: 100% E2E Test Pass & Hardening | Pass 100% of Tiers 1-4 E2E tests, Tier 5 adversarial testing, acceptance criteria validation | M1-M5, E2E | PLANNED |

## Interface Contracts

### 1. Daemon Health & CAD Sync (`GET /api/health`, `/api/cad/*`)
```json
// GET /api/health
{
  "status": "ok",
  "version": "0.1.0",
  "pid": 12345,
  "cad_mode": "mock",
  "copilot_ready": true
}

// GET /api/cad/status
{
  "connected": false,
  "mode": "mock",
  "document_id": "mock-doc-001",
  "access_key_configured": false
}

// POST /api/cad/mode -> {"mode": "mock" | "live"}
// POST /api/cad/config -> {"access_key": "...", "secret_key": "...", "document_id": "..."}
```

### 2. Mesh Surface Scalars (`GET /api/revisions/{rev_id}/mesh`)
```json
{
  "rev_id": 1,
  "vertices": [x0, y0, z0, x1, y1, z1, ...],
  "normals": [nx0, ny0, nz0, ...],
  "stress_field": [s0, s1, ...], // Normalized von Mises stress in [0.0, 1.0]
  "cp_field": [cp0, cp1, ...],     // Pressure coefficient in [-1.0, 1.0]
  "peak_von_mises_mpa": 185.4,
  "yield_strength_mpa": 276.0,
  "yield_fos": 1.49,
  "triangle_count": 12480
}
```

### 3. MLX Copilot Engine Endpoints
```json
// GET /api/copilot/vram
{
  "physical_ram_gib": 18.0,
  "tier": "pro",
  "default_quantization": "4-bit",
  "default_context_length": 8192,
  "recommended_repo": "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
}

// POST /api/copilot/review -> body: {"intent": "...", "current_params": {...}}
{
  "summary": "...",
  "modifications": {"param_key": {"old": val, "new": val}},
  "rationale": "..."
}

// POST /api/copilot/optimize -> body: {"targets": {"apogee": 5000, "von_mises_stress": 200}}
{
  "status": "converged" | "failed",
  "iterations": 3,
  "final_revision_id": 13,
  "margins_met": true
}
```

### 4. IPC WebKit Bridge Contract (`window.webkit.messageHandlers.goddardBridge.postMessage`)
```typescript
interface GoddardIPCMessage {
  action: "haptic" | "playSound" | "toggleMute" | "exportBundle" | "windowControl";
  style?: "generic" | "alignment" | "levelChange";
  sound?: "touchdown" | "complete" | "alert" | "warning" | "click";
  muted?: boolean;
  revisionId?: number;
  command?: "minimize" | "zoom" | "close";
}
```
