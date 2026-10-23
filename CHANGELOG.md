# Changelog

All notable changes to the **NNUVA Suite** (`nnuva` & `nnuva-report`) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [6.0.4] - 2026-10-23

### Changed
- **Footer Kebab Menu Integration**: Replaced floating action button with a sleek circular kebab menu button (`#footerKebabBtn`, `⋮`) positioned cleanly in the bottom footer row directly next to the theme toggle pill.
- **Dynamic Popup Anchoring**: Positioned the quick actions menu (`#meatballMenu`) to anchor smoothly right above the circular footer kebab button based on real-time viewport coordinates.
- **Cleaned Footer Geometry**: Restored standard footer padding and body bottom spacing, removing unnecessary empty space and margin offsets formerly required by the floating button.

---

## [6.0.3] - 2026-10-23

### Added
- **Modern Floating Hex Button with Halo Glow**: Replaced bottom-right squircle FAB with a standalone geometric hexagon icon that rotates 30° on hover and triggers an expanding circular white/cyan halo glow (`.hex-halo`).
- **Dedicated System & Database Health Modal**: Transformed the awkward collapsible accordion at the page footer into a modal (`#sysHealthModal`) accessible directly from the single-line footer and quick actions menu.

### Changed
- **Unified Header & Sticky Search Alignment**: Aligned the static top hero search bar (`#heroSearch`) and sticky scrolling search bar (`#globalSearch`) to identical right-centered pixel coordinates across all screen widths.
- **Single-Line Streamlined Footer**: Cleaned up the dashboard footer into a clean single line with pill theme toggles (`Light` / `Dark` / `OLED`) and removed the duplicate floating theme dock.
- **Unified Suite Documentation**: Cleaned up project modal links and repository references to point to the unified `nnuva` monorepo.

### Fixed
- **Hero Header Width Constraint**: Resolved `display: flex` on `.header-section` which previously caused `.hero-bar` to shrink-wrap rather than spanning the full 1400px container width.
- **Reset to Baseline Exception**: Removed broken legacy `resetToBaseline` reference and implemented smooth reset/top scroll handler.

---

## [6.0.2] - 2026-10-23

### Fixed
- **Dashboard Web Template Missing**: Added whitelist exception `!src/**/templates/*.html` to `.gitignore` and bundled `src/nnuva_report/templates/index.html` into repository tracking to prevent runtime file missing errors upon clean installation.
- **Installer Auto-Sync & Fallback**: Updated `install.sh` remote 1-liner mode to cleanly reset against upstream `origin/main` on existing installations (`git fetch && git reset --hard`), avoiding diverged branch hangs.
- **Zero-Git Fallback**: Added automated GitHub tarball archive extraction fallback in `install.sh` for systems without `git` installed.

---

## [6.0.1] - 2026-10-23

### Fixed
- **Path Sanitization**: Removed all local machine paths, user folders, and network mount specifics from defaults in `install.sh` and codebase.
- **Dynamic Mount Discovery**: Enhanced disk / volume path inference in dashboard analytics to dynamically inspect `/mnt` and `/media` rather than static volume paths.

---

## [6.0.0] - 2026-10-23

### Added
- **Monorepo Suite Architecture**: Unified `nnuva` CLI and `nnuva-report` into a single coordinated repository.
- **Universal 1-Line Installer**: Introduced interactive one-liner (`curl -fsSL ... | bash`) supporting modular installation (all, nnuva CLI only, or report dashboard only), uninstall, and cron scheduling.
- **Dynamic Terminal Matrix Output**: Upgraded CLI engine with dynamic terminal width wrapping, column profiles (`--tech`, `--lang`), and custom column filters.
- **SQLite Analytics Engine**: Backed dashboard generation with high-performance SQLite caching alongside JSON cache compatibility.
