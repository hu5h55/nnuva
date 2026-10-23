# NNUVA Suite (v6.0.0)

**NNUVA** (`Nic's Nearly Universal Video Analyzer`) is a high-performance, multithreaded media analyzer and interactive dashboard generator.

It brings together:
1. **`nnuva`**: Lightning-fast CLI terminal analyzer that outputs dynamically aligned, color-coded matrices of codecs, bitrates, HDR profiles, and audio tracks.
2. **`nnuva-report`**: Automated SQLite analytics engine and interactive HTML5 web dashboard with multi-mode themes (OLED / Dark / Light), Chart.js visualizations, and media health metrics.

---

## Installation

### 1. The 1-Line Installer (Recommended)
Installs `nnuva` CLI and optional `nnuva-report` dashboard with interactive configuration for automated cron jobs:
```bash
curl -fsSL https://raw.githubusercontent.com/hu5h55/nnuva/main/install.sh | bash
```

### 2. Standalone / Zero-Install Mode
No installation or root required. Runs entirely in-memory without polluting your filesystem:
```bash
curl -O https://raw.githubusercontent.com/hu5h55/nnuva/main/nnuva.py
chmod +x nnuva.py
./nnuva.py /path/to/media
```

### 3. Git Clone & Local Install
```bash
git clone https://github.com/hu5h55/nnuva.git
cd nnuva
./install.sh
```

To cleanly uninstall at any time:
```bash
nnuva --uninstall
# or: ./install.sh --uninstall
```

## Usage
Run NNUVA against a specific file, directory, or wildcard pattern. If no path is provided, it scans the current directory.

nnuva
# Scan current directory
nnuva

# Scan a specific folder
nnuva /path/to/movies

# Scan using wildcards (wrap in quotes to prevent shell expansion)
nnuva "*.mkv"

### Profiles & Options
NNUVA includes custom profiles to swap which columns are displayed without cluttering smaller monitors:

* `nnuva` : Default view (Size, Runtime, Resolution, Video, Audio, Subs, HDR).
* `nnuva --tech` : Swap out Subs/HDR for Bitrate, Framerate, and Color Depth.
* `nnuva --lang` : Focus entirely on Audio, Subtitles, and embedded language tracks.
* `nnuva -a` : Flood the terminal with every available data column.

Want to build your own view? Just pass the exact columns you want to see:
\`\`\`bash
nnuva --res --video --bitrate --audio
\`\`\`



### Maintenance & Cache Management
* `nnuva --prune` : Automatically removes stale cache entries for files that have been deleted, moved, or renamed.
* `nnuva --clear-cache` : Resets the entire local cache database.
* `nnuva -i` / `nnuva --info` : Inspect system installation paths, cache sizes, and instance IDs.

## License
This project is licensed under the GNU General Public License v3.0 (GPLv3). See the `LICENSE` file for details.
