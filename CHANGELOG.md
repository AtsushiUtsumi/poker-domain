# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-07-23

### Changed

- Migrated to a standard `src/` layout (`src/poker_domain/`) in preparation for a future
  PyPI trial release and poly-repo split. The `import poker_domain` path used by consumers
  (e.g. mullhouse) is unchanged.
- Consolidated build/packaging configuration into `pyproject.toml` using `hatchling` as the
  build backend (previously `setuptools`).
- Added `py.typed` marker for PEP 561 inline type-hint support.
- Added `dev` and `test` optional dependency groups (`ruff`, `mypy`, `pytest`).
- Added `ruff` and `mypy` configuration (tooling introduced; not all findings addressed yet).

### Added

- `LICENSE` (MIT).
- `CHANGELOG.md` (this file).

No changes to public API surface or game logic behavior.

## [0.1.0] - Unreleased history prior to this changelog

- Initial flat-layout implementation of the poker domain library (table lifecycle, side pots,
  rake, rebuy/fixed buy-in rules, action log, hand evaluation, etc.). See git history for details.
