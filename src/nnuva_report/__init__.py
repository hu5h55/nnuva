# src/nnuva_report/__init__.py

APP_NAME = "nnuva-report"
VERSION = "6.0.2"

CHANGELOG_LINES = [
    "v6.0.2 (2026-10-23) - FIX: Bundled web dashboard template into repository, robust 1-liner auto-update with branch reset, and fallback full-archive tarball downloads.",
    "v6.0.1 (2026-10-23) - FIX: Sanitized dynamic library path enrichment and installer path defaults.",
    "v6.0.0 (2026-10-23) - MAJOR: Unified under NNUVA Suite monorepo with simultaneous CLI and dashboard release synchronization.",
    "v5.8.1 (2026-10-23) - UI/UX: Added floating theme dock & quick baseline reset button, updated AI-Generated badges with GitHub links, and restored standard CLI help & version flags.",
    "v5.8.0 (2026-10-18) - FEAT: Added 'Storage Footprint & Folder Hogs' 3-tile row (Storage by Category, Top Series & Collection Hogs, Storage Efficiency GB/Hour), a sortable 'Folder Hogs: Top Largest Series & Collections' leaderboard table, total playback runtime telemetry, and Category / Bit Depth / Container filters.",
    "v5.7.0 (2026-10-18) - FEAT: Added 3-mode Theme Engine (Light / Dark / OLED, defaulting to OLED pitch-black #000000) with 1-click header cycle toggle, segmented menu controls, rim-bordered cards, and live Chart.js canvas re-theming.",
    "v5.6.9 (2026-05-13) - UX: Duration radar axis now uses the 75th-percentile of library durations instead of the absolute max. Outlier multi-hour recordings (concerts, batched TV files) no longer crush typical movie scores — a 90-minute film now scores 100% in a TV-heavy library, where it previously scored ~20%.",
    "v5.6.8 (2026-05-13) - UX: Media Footprint radar axes refined. Replaced weak axes (FPS, Audio Channels) with Duration and Bit Depth. Replaced FPS spec card with Size in the Quantifiable Media Specs grid.",
    "v5.6.7 (2026-05-13) - UX: Media Footprint chart rebuilt as 6-axis hexagonal radar. Normalization now uses real library maxes scanned from rawFiles instead of hardcoded thresholds.",
    "v5.6.6 (2026-05-09) - UX: KPI grid restructured. Left column stacks Total Files / Total Storage vertically. Right block is a 2x2 grid: Optimal + Upgrade on top, Transcode + Reclaimable on bottom.",
    "v5.6.5 (2026-05-09) - FIX: Re-applied v5.6.3 expand-button onclick fix that was inadvertently regressed in v5.6.4 modal restyle work.",
    "v5.6.4 (2026-05-09) - UX: Chart fullscreen modal restyled to match file modal — fixed header bar, separate scrollable body wrapper.",
    "v5.6.3 (2026-05-09) - FIX: Chart/trend card expand button (⛶) — onclick attr had a broken multi-line string literal.",
    "v5.6.2 (2026-04-19) - SYS: Finalized modular Python backend with SQLite ETL pipeline.",
    "v5.6.1 (2026-04-19) - FIX: Safe template injection to prevent MemoryError crashes.",
    "v5.6.0 (2026-04-18) - FEAT: Bitrate Analysis row with real data; History panel shows library change deltas."
]
