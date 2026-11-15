# Contributing to Goddard

Thank you for your interest in contributing to **Goddard**, the open-source multi-physics generative rocket design platform and CAD-to-Physics copilot.

Aerospace engineering demands the highest standards of numerical precision, physical rigor, and software reliability. This document provides guidelines for environment setup, code style, verification testing, and pull requests.

---

## 1. Development Environment Setup

### Prerequisites
- Python 3.10, 3.11, or 3.12
- Git
- Optional (for local high-fidelity meshing / solvers):
  - [Gmsh](https://gmsh.info/) (`>= 4.11.0`)
  - [CalculiX](http://www.dhondt.de/) (FEA solver `ccx`)
  - [SU2](https://su2code.github.io/) (CFD solver `SU2_CFD`)

### Virtual Environment Setup
Clone the repository and initialize a dedicated virtual environment:

```bash
git clone https://github.com/tarunprakash/Goddard.git
cd Goddard

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Upgrade packaging tools and install in editable mode with dev dependencies
pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
```

### Environment Configuration
Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

If developing without active Onshape API credentials, ensure offline mode is enabled:
```bash
export GODDARD_OFFLINE_MODE=true
```

---

## 2. Code Quality & Standards

Goddard enforces strict formatting and linting standards using [Ruff](https://github.com/astral-sh/ruff).

### Code Formatter and Linter
Run Ruff checks and automated formatting before committing:

```bash
# Run lint check
ruff check .

# Fix auto-fixable lint issues
ruff check --fix .

# Check code formatting
ruff format --check .

# Auto-format all Python files
ruff format .
```

### Engineering and Typing Conventions
1. **Type Hints:** All public functions, dataclasses, Pydantic models, and method signatures must include strict type annotations (`typing` or standard Python 3.10+ types).
2. **Units & Physical Quantities:**
   - Use SI units exclusively in internal calculations (e.g., meters `m`, Pascals `Pa`, Newtons `N`, Kelvin `K`, kilograms `kg`).
   - Suffix variable names with unit identifiers when ambiguous (e.g., `pressure_pa`, `altitude_m`, `thrust_n`).
3. **Safety Margins & Factors:**
   - ASME Section VIII Div 2 pressure vessel burst margins: $\text{SF} \ge 1.5$ (or proof $\ge 1.25$).
   - Aeroelastic flutter margins: $V_{\text{flutter}} / V_{\text{max}} \ge 1.2$.
   - Thermal & structural margins of safety must follow $MS = \frac{\sigma_{\text{allowable}}}{\sigma_{\text{actual}} \times SF} - 1.0 \ge 0.0$.
4. **Deterministic Behavior:** Ensure geometric synthesizers and trajectory seeds produce reproducible outputs. Avoid non-seeded pseudorandomness in core physics pipelines.

---

## 3. Testing and Verification

All code changes must be accompanied by comprehensive unit and integration tests.

### Running Test Suite
Execute tests with `pytest`:

```bash
# Run all tests
pytest tests/ -v

# Run with test coverage report
pytest --cov=goddard tests/ -v

# Run a specific test module
pytest tests/test_physics.py -v
```

### Verification Requirements
- **Aerospace Unit Tests:** Validate structural equations (ASME wall thickness, Blevins flutter velocity) against analytical closed-form solutions.
- **Offline Decoupling:** Every module that interfaces with external services (such as the Onshape REST API) must provide mock or offline pathways so the test suite passes in air-gapped CI environments.

---

## 4. Pull Request Process

1. **Branching Strategy:**
   - Create a feature branch from `main`:
     ```bash
     git checkout -b feature/propulsive-landing-guidance
     ```
   - Use clear branch naming prefixes: `feature/`, `bugfix/`, `docs/`, `refactor/`, `physics/`.

2. **Commit Hygiene:**
   - Write clear, descriptive commit messages summarizing the engineering intent.

3. **Pre-Submission Checklist:**
   - [ ] All tests pass (`pytest tests/ -v`).
   - [ ] Ruff checks pass with zero warnings (`ruff check .` and `ruff format --check .`).
   - [ ] New functionality includes docstrings explaining physics formulas, assumptions, and coordinate frames.
   - [ ] Offline simulation mode functions without external API credentials.

4. **Review & Merge:**
   - Open a Pull Request targeting `main`.
   - Ensure the GitHub Actions CI pipeline passes across Python 3.10, 3.11, and 3.12.
   - Address any reviewer feedback promptly.

---

## 5. Security & Responsible Disclosure

If you discover a security vulnerability or credential leak within the platform or Onshape integration, please report it privately to the maintainers rather than filing a public issue.
