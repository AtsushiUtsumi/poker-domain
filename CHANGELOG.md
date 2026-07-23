# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-07-23

### Fixed

- Fixed a bug where collecting antes leaked into `Player.current_bet`, causing the table's
  `current_bet` and the big blind player's `current_bet` to disagree. In rare cases this let
  a `Call()` be applied with a negative amount, raising an unhandled `ValueError` and freezing
  the hand. `Player._contribute()` now takes an `affects_current_bet` flag, and ante collection
  passes `affects_current_bet=False` so antes only add to the pot/`total_contributed`, not to
  `current_bet`. Added a defensive guard in `PokerTable._validate_action` that rejects `Call()`
  with `InvalidActionError` instead of crashing if a player has already contributed more than
  the table's `current_bet` (should no longer be reachable, but fails safely if it recurs).

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
