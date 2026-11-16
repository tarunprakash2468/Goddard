# E2E Test Infra: Goddard Native macOS Liquid Glass & MLX Copilot

## Test Philosophy
- Opaque-box, requirement-driven. No dependency on implementation design.
- Methodology: Category-Partition + Boundary Value Analysis (BVA) + Pairwise Combinatorial Testing + Real-World Workload Testing.
- 100% offline verification in `tests/`: Zero external network calls; all mock modes, MLX heuristic fallbacks, and fixture caches operate strictly local.

## Feature Inventory & Requirement Traceability
| # | Feature | Source (Requirement) | Tier 1 | Tier 2 | Tier 3 |
|---|---------|----------------------|:------:|:------:|:------:|
| 1 | Native Liquid Glass AppKit Window | R1 | 5 | 5 | ✓ |
| 2 | Transparent WebGL Viewport & Backdrop Modes | R1 | 5 | 5 | ✓ |
| 3 | 3D Multi-Physics Overlays (Solid, Stress, Cp, Gmsh) | R2 | 5 | 5 | ✓ |
| 4 | 3D Revision Ghosting | R2 | 5 | 5 | ✓ |
| 5 | Adaptive VRAM Profiler | R3 | 5 | 5 | ✓ |
| 6 | In-App Model Cache Manager & Downloader | R3 | 5 | 5 | ✓ |
| 7 | MLX Interactive Review Mode & Parametric Diff | R3 | 5 | 5 | ✓ |
| 8 | MLX Autonomous Goal Mode Optimization | R3 | 5 | 5 | ✓ |
| 9 | CAD Cloud Sync & Offline Mock Mode | R4 | 5 | 5 | ✓ |
| 10 | Aerospace Audio, Haptics & Shortcuts | R5 | 5 | 5 | ✓ |
| 11 | Subprocess Daemon Supervisor & Lifecycle | R6 | 5 | 5 | ✓ |
| 12 | Standalone Build Script & Installation | R6 | 5 | 5 | ✓ |

## Test Architecture
- **Runner**: `pytest` using Python 3.11 virtualenv with `tests/e2e/`.
- **Packaging & Swift Test Runner**: Swift test executable / bash script test executing `build_app.sh`, inspecting bundle structure, plist validation via `plutil`, and binary execution.
- **Pass/Fail Semantics**: All test suites must exit with returncode 0.
- **Offline Assurance**: `os.environ["GODDARD_OFFLINE_MODE"] = "true"` enforced in all test runs.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Full Offline Lifecycle | Daemon launch -> Health check -> Offline Mock CAD sync -> Revision inspection -> Design bundle export | High |
| 2 | Autonomous Design Optimization Loop | Copilot Autonomous Goal Mode -> Sizing -> FEA -> Trajectory -> Margin pass -> New Revision commit | High |
| 3 | Interactive Review & Parameter Diff | User intent prompt -> Copilot parametric diff -> "Apply to CAD & Re-Simulate" -> Haptic dispatch -> Ledger update | High |
| 4 | 3D Multi-Physics & Ghosting Visual Flow | Load rev 12 -> Toggle Solid, Stress heatmap, CFD Cp, Gmsh wireframe -> Activate Revision Ghosting of rev 11 | High |
| 5 | Packaging, Info.plist & Install Verification | `build_app.sh` compile -> Verify `Goddard.app/Contents/MacOS/GoddardApp`, `Info.plist`, `AppIcon.icns` -> `build_app.sh --install` -> Verify `/Applications/Goddard.app` | High |

## Coverage Thresholds
- Tier 1: Feature Coverage (>=5 tests per feature = 60+ tests)
- Tier 2: Boundary & Corner Cases (>=5 tests per feature = 60+ tests)
- Tier 3: Cross-Feature Combinations (Pairwise feature interaction suites)
- Tier 4: Real-World Application Scenarios (5 comprehensive multi-module end-to-end integration flows)
- Tier 5: Adversarial Coverage Hardening (White-box edge cases and gap elimination)
