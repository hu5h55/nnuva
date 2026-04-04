# NNUVA (Nic's Nearly Universal Video Analyzer)

NNUVA is a lightning-fast, multithreaded CLI tool built to scan your local media library and output a perfectly aligned, color-coded grid of video codecs, bitrates, HDR profiles, and audio tracks. 

Instead of dealing with unreadable JSON dumps or running manual `ffprobe` commands file by file, NNUVA processes entire directories concurrently and scales its output dynamically to fit your terminal.

## Features
* **Multithreaded Scanning:** Processes hundreds of files concurrently (default: 10 threads).
* **Dynamic Grid Layout:** Automatically calculates the exact mathematical width needed for your specific filenames and codecs.
* **Color-Coded Output:** Visually flags 4K, HEVC, TrueHD, 10-bit color, and corrupted files.
* **HDR & Dolby Vision Detection:** Explicitly calls out HDR10, HDR10+, and Dolby Vision (including Trap Profile 5).

## Prerequisites
* **Python 3** (No external `pip` libraries required)
* **FFmpeg / ffprobe** installed and available in your system path.

## Installation
Clone the repository and make the script executable. 
For global use, simply symlink it to your local bin:

\`\`\`bash
git clone https://github.com/yourusername/nnuva.git
cd nnuva
chmod +x nnuva.py
sudo ln -s $(pwd)/nnuva.py /usr/local/bin/nnuva
\`\`\`

## Usage
Run NNUVA against a specific file, directory, or wildcard pattern. If no path is provided, it scans the current directory.

\`\`\`bash
# Scan current directory
nnuva

# Scan a specific folder
nnuva /path/to/movies

# Scan using wildcards (wrap in quotes to prevent shell expansion)
nnuva "*.mkv"
\`\`\`

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



## License
This project is licensed under the GNU General Public License v3.0 (GPLv3). See the `LICENSE` file for details.
