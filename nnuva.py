#!/usr/bin/env python3

# NNUVA (Nic's Nearly Universal Video Analyzer)
# Copyright (C) 2026 Nic
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import sys
import os
import json
import subprocess
import shutil
import math
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==============================================================================
# CONFIGURATION
# ==============================================================================
VERSION = "1.0.0"
SUPPORTED_EXTS = {'.mkv', '.mp4', '.avi', '.ts', '.mov', '.webm', '.flv', '.m4v'}
MAX_THREADS = 10 

class Color:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'

EXPLANATIONS = {
    'SIZE': 'File Size', 'DUR': 'Runtime', 'RES': 'Resolution', 'VIDEO': 'Vid Codec',
    'BITRATE': 'Avg Bitrate', 'FPS': 'Framerate', 'DEPTH': 'Color Depth',
    'AUDIO': 'Aud Codec', 'LANG': 'Languages', 'SUBS': 'Subtitles', 'HDR': 'HDR Format'
}

# ==============================================================================
# SYSTEM MANAGEMENT (INSTALL / UNINSTALL)
# ==============================================================================

def get_installed_version(target_path):
    if not os.path.exists(target_path): return None
    try:
        with open(target_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('VERSION ='):
                    return line.split('=')[1].strip().strip('\'"')
    except Exception: return "Unknown"
    return None

def perform_installation(is_update=False):
    current_script = os.path.abspath(__file__)
    target_dir = os.path.expanduser("~/.local/bin")
    target_path = os.path.join(target_dir, "nnuva")

    action = "Updating" if is_update else "Installing"
    print(f"\n{Color.GRAY}{action} to {target_path}...{Color.RESET}")
    os.makedirs(target_dir, exist_ok=True)
    
    try:
        shutil.copy(current_script, target_path)
        os.chmod(target_path, 0o755)
        
        success_msg = "updated" if is_update else "copied"
        print(f"{Color.GREEN}✓ Successfully {success_msg} NNUVA to your local bin.{Color.RESET}")
        
        if target_dir not in os.environ.get('PATH', ''):
            print(f"\n{Color.YELLOW}Almost done!{Color.RESET} {target_dir} is not in your system PATH.")
            print("To finish, run this command or add it to your ~/.bashrc / ~/.zshrc:")
            print(f"{Color.BOLD}export PATH=\"$HOME/.local/bin:$PATH\"{Color.RESET}\n")
        elif not is_update:
            print(f"Installation complete! You can now run {Color.BOLD}nnuva{Color.RESET} from anywhere.\n")
            
        sys.exit(0)
    except Exception as e:
        print(f"{Color.RED}Installation failed: {e}{Color.RESET}\n")
        sys.exit(1)

def handle_uninstall():
    target_path = os.path.expanduser("~/.local/bin/nnuva")
    if os.path.exists(target_path):
        try:
            os.remove(target_path)
            print(f"{Color.GREEN}✓ NNUVA has been successfully uninstalled from {target_path}{Color.RESET}")
        except Exception as e:
            print(f"{Color.RED}Failed to uninstall: {e}{Color.RESET}")
            sys.exit(1)
    else:
        print(f"{Color.YELLOW}NNUVA is not currently installed at {target_path}{Color.RESET}")
    sys.exit(0)

def smart_install_prompt():
    if not sys.stdout.isatty(): return

    target_path = os.path.expanduser("~/.local/bin/nnuva")
    if os.path.abspath(__file__) == target_path: return

    installed_version = get_installed_version(target_path)
    if installed_version == VERSION: return

    print(f"{Color.CYAN}NNUVA is running in standalone mode.{Color.RESET}")
    
    try:
        if installed_version:
            response = input(f"Update global install from v{installed_version} to v{VERSION}? [y/N]: ").strip().lower()
            is_update = True
        else:
            print(f"{Color.GRAY}(Installation safely copies this script to your local bin){Color.RESET}\n")
            response = input(f"Copy NNUVA to {target_path}? [y/N]: ").strip().lower()
            is_update = False
    except KeyboardInterrupt:
        print("\n")
        sys.exit(1)
    
    if response in ['y', 'yes']:
        perform_installation(is_update)
    else:
        print(f"{Color.GRAY}Skipping. Running standalone scan...{Color.RESET}\n")

# ==============================================================================
# CORE SCANNING LOGIC
# ==============================================================================

def check_ffprobe():
    if not shutil.which('ffprobe'):
        print("Error: ffprobe is not installed.")
        sys.exit(1)

def get_files(args):
    """Optimized file gathering using sets and targeted globs."""
    media_files = set()
    paths = args if args else ['.']
    
    for arg in paths:
        p = Path(arg)
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS and not p.name.startswith('._'):
            media_files.add(p)
        elif p.is_dir():
            for ext in SUPPORTED_EXTS:
                media_files.update(f for f in p.glob(f"*{ext}") if f.is_file() and not f.name.startswith('._'))
                media_files.update(f for f in p.glob(f"*/*{ext}") if f.is_file() and not f.name.startswith('._'))
        else:
            for f in Path('.').glob(arg):
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS and not f.name.startswith('._'):
                    media_files.add(f)
                    
    return sorted(list(media_files))

def format_size(size_bytes):
    if size_bytes == 0: return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    return f"{round(size_bytes / p, 1):g}{size_name[i]}"

def format_duration(seconds):
    if not seconds: return "N/A"
    try:
        m, s = divmod(float(seconds), 60)
        h, m = divmod(m, 60)
        return f"{int(h)}:{int(m):02d}:{int(s):02d}" if h > 0 else f"{int(m):02d}:{int(s):02d}"
    except: return "N/A"

def analyze_file(filepath):
    size_str = format_size(os.path.getsize(filepath))
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries', 
        'format=duration,bit_rate:stream=codec_type,codec_name,width,height,color_transfer,color_primaries,channels,r_frame_rate,bits_per_raw_sample,pix_fmt:stream_side_data=side_data_type,dv_profile:stream_tags=language',
        '-print_format', 'json', str(filepath)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0: return {"file": filepath.name, "error": True, "SIZE": size_str}
        data = json.loads(result.stdout)
    except Exception:
        return {"file": filepath.name, "error": True, "SIZE": size_str}

    v_codec, width, height, transfer, primaries, dv_profile, hdr10plus, fps, depth = "N/A", None, None, "", "", None, False, "N/A", "N/A"
    a_codec, a_ch, sub_codecs, audio_langs, sub_langs = "N/A", "", set(), [], []

    fmt = data.get('format', {})
    dur_str = format_duration(fmt.get('duration'))
    bitrate = fmt.get('bit_rate')
    br_str = f"{round(float(bitrate) / 1000000, 1)}M" if bitrate else "N/A"
    has_video = False

    for stream in data.get('streams', []):
        stype = stream.get('codec_type')
        lang = stream.get('tags', {}).get('language', 'und').upper()
        if len(lang) == 3: lang = lang[:2] 
        
        if stype == 'video':
            has_video = True
            if v_codec == "N/A":
                v_codec = stream.get('codec_name', 'N/A').upper()
                width, height = stream.get('width'), stream.get('height')
                transfer, primaries = stream.get('color_transfer', ''), stream.get('color_primaries', '')
                
                if '/' in (r_fps := stream.get('r_frame_rate', '0/1')):
                    n, d = r_fps.split('/')
                    if d != '0': fps = f"{float(n)/float(d):.3f}".rstrip('0').rstrip('.')
                
                pix_fmt = stream.get('pix_fmt', '')
                raw_depth = stream.get('bits_per_raw_sample')
                depth = f"{raw_depth}b" if raw_depth else ("10b" if '10' in pix_fmt else "12b" if '12' in pix_fmt else "8b" if pix_fmt else "N/A")
                
                for sd in stream.get('side_data_list', []):
                    if sd.get('side_data_type') == 'DOVI configuration record': dv_profile = sd.get('dv_profile')
                    if 'HDR10+' in sd.get('side_data_type', ''): hdr10plus = True

        elif stype == 'audio':
            if a_codec == "N/A":
                a_codec = stream.get('codec_name', 'N/A').upper()
                ch = stream.get('channels', 0)
                a_ch = "7.1" if ch == 8 else "5.1" if ch == 6 else "2.0" if ch == 2 else str(ch)
            if lang != 'UN': audio_langs.append(lang)
        
        elif stype == 'subtitle':
            c = stream.get('codec_name', '').lower()
            if 'pgs' in c or 'hdmv_pgs' in c: sub_codecs.add('PGS [BURN]')
            elif 'vobsub' in c or 'dvd_subtitle' in c: sub_codecs.add('VOBSUB [B]')
            elif c: sub_codecs.add('Text')
            if lang != 'UN': sub_langs.append(lang)
            
    if not has_video: return {"skip": True}
    
    s_codec = 'PGS [BURN]' if 'PGS [BURN]' in sub_codecs else 'VOBSUB [B]' if 'VOBSUB [B]' in sub_codecs else 'Text' if 'Text' in sub_codecs else 'None'
    res_label = "4K" if height and height >= 2160 else "1080p" if height and height >= 1080 else "720p" if height and height >= 720 else "480p" if height and height >= 480 else f"{width}x{height}" if width else "N/A"
    
    hdr_label = f"DV P{dv_profile}{' [TRAP!]' if dv_profile == 5 else ''}" if dv_profile else ""
    hdr_label = f"{hdr_label} + HDR10+" if hdr_label and hdr10plus else "HDR10+" if hdr10plus else hdr_label
    base = "HDR10" if transfer == "smpte2084" or primaries == "bt2020" else "SDR"
    hdr_label = f"{hdr_label} ({base} Base)" if hdr_label else base

    a_str = f"A:{','.join(dict.fromkeys(audio_langs))}" if audio_langs else ""
    s_str = f"S:{','.join(dict.fromkeys(sub_langs))}" if sub_langs else ""
    lang_str = f"{a_str} {s_str}".strip() or "None"

    return {
        "file": filepath.name, "error": False, "skip": False, "SIZE": size_str, "DUR": dur_str,
        "RES": res_label, "VIDEO": v_codec, "AUDIO": f"{a_codec} {a_ch}".strip() if a_codec != "N/A" else "N/A",
        "SUBS": s_codec, "HDR": hdr_label, "BITRATE": br_str, "DEPTH": depth, "FPS": fps, "LANG": lang_str
    }

def style_text(text, col_name):
    if not text: return text
    if text in ["ERROR", "CORRUPT"] or "[TRAP!]" in text or "[BURN]" in text: return f"{Color.BOLD}{Color.RED}{text}{Color.RESET}"
    if text == "4K" or text in ["HEVC", "AV1", "10b"] or "TRUEHD" in text or "DTS-HD" in text: return f"{Color.GREEN}{text}{Color.RESET}"
    if col_name == "SIZE": return f"{Color.CYAN}{text}{Color.RESET}"
    if col_name == "HEADER": return f"{Color.BOLD}{text}{Color.RESET}"
    return text

def main():
    smart_install_prompt()
    check_ffprobe()
    
    parser = argparse.ArgumentParser(description="NNUVA - Nic's Nearly Universal Video Analyzer")
    parser.add_argument('-v', '--version', action='version', version=f'NNUVA v{VERSION}')
    parser.add_argument('paths', nargs='*', default=['.'], help="Files or directories to scan")
    
    sys_group = parser.add_argument_group('System Management')
    sys_group.add_argument('--install', action='store_true', help="Install NNUVA globally to ~/.local/bin")
    sys_group.add_argument('--uninstall', action='store_true', help="Remove NNUVA from ~/.local/bin")

    group = parser.add_argument_group('Profiles (Overrides default columns)')
    group.add_argument('--tech', action='store_true', help="Show technical info (Bitrate, FPS, Depth)")
    group.add_argument('--lang', action='store_true', help="Show Audio, Subs, and embedded Language tags")
    group.add_argument('-a', '--all', action='store_true', help="Show all available columns")
    
    c_group = parser.add_argument_group('Individual Columns (Creates a custom view)')
    for col in ['size', 'dur', 'res', 'video', 'audio', 'subs', 'hdr', 'bitrate', 'depth', 'fps']:
        c_group.add_argument(f'--{col}', action='store_true')
    c_group.add_argument('--lang_col', dest='lang_flag', action='store_true')
    
    args = parser.parse_args()
    if args.uninstall: handle_uninstall()
    if args.install: perform_installation()

    ALL_COLS = ['SIZE', 'DUR', 'RES', 'VIDEO', 'BITRATE', 'FPS', 'DEPTH', 'AUDIO', 'LANG', 'SUBS', 'HDR']
    flag_map = {col: getattr(args, col.lower() if col != 'LANG' else 'lang_flag') for col in ALL_COLS}
    
    if any(flag_map.values()): active_cols = [c for c in ALL_COLS if flag_map[c]]
    elif args.all: active_cols = ALL_COLS
    elif args.tech: active_cols = ['SIZE', 'DUR', 'BITRATE', 'RES', 'VIDEO', 'FPS', 'DEPTH', 'HDR', 'AUDIO']
    elif args.lang: active_cols = ['DUR', 'AUDIO', 'LANG', 'SUBS']
    else: active_cols = ['SIZE', 'DUR', 'RES', 'VIDEO', 'AUDIO', 'SUBS', 'HDR']

    files = get_files(args.paths)
    if not files:
        print("Error: No valid media files found.")
        sys.exit(1)
    
    total, raw_results = len(files), []
    sys.stdout.write('\033[?25l') 
    
    try:
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            for i, future in enumerate(as_completed([executor.submit(analyze_file, f) for f in files]), 1):
                raw_results.append(future.result())
                percent = i / total
                filled = int(30 * percent)
                bar = f"{Color.CYAN}{'█' * filled}{Color.GRAY}{'░' * (30 - filled)}{Color.RESET}"
                sys.stdout.write(f"\r{Color.BOLD}Scanning {total} files:{Color.RESET} [{bar}] {i}/{total} ({int(percent * 100)}%)")
                sys.stdout.flush()
    finally:
        sys.stdout.write('\033[?25h\r\033[K') 
            
    results = sorted([r for r in raw_results if not r.get("skip")], key=lambda x: x['file'])
    if not results:
        print("No valid video files found after scanning.")
        sys.exit(0)

    # Calculate dynamic column widths
    col_widths = {col: max(max((len(r.get(col, "N/A")) for r in results if not r['error']), default=max(len(col), len(EXPLANATIONS[col]))), max(len(col), len(EXPLANATIONS[col]))) for col in active_cols}
    file_width = max(20, shutil.get_terminal_size((120, 24)).columns - sum(col_widths.values()) - (len(active_cols) * 3))
    
    sep = f"{Color.GRAY}{'-' * (file_width + sum(col_widths.values()) + (len(active_cols) * 3))}{Color.RESET}"
    divider = f" {Color.GRAY}|{Color.RESET} "
    
    expl_row = f"{' ':<{file_width}}" + "".join([f"{divider}{Color.GRAY}{EXPLANATIONS[c]:<{col_widths[c]}}{Color.RESET}" for c in active_cols])
    header_str = style_text(f"{'FILE':<{file_width}}", "HEADER") + "".join([f"{divider}{style_text(f'{c:<{col_widths[c]}}', 'HEADER')}" for c in active_cols])

    # Print Table
    print(f"{sep}\n{header_str}\n{sep}")
    for r in results:
        name = r['file'][:file_width-3] + "..." if len(r['file']) > file_width else r['file']
        row_str = f"{name:<{file_width}}"
        
        # Consolidated print logic handling both success and error states cleanly
        for idx, col in enumerate(active_cols):
            val = 'ERROR' if r['error'] and idx == 0 else 'CORRUPT' if r['error'] and idx == 1 else 'N/A' if r['error'] else r.get(col, 'N/A')
            row_str += f"{divider}{style_text(f'{val:<{col_widths[col]}}', col)}"
        print(row_str)
        
    print(f"{sep}\n{expl_row}\n{sep}")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt:
        sys.stdout.write('\033[?25h\r\033[K')
        print("\nScan aborted by user.")
        sys.exit(1)
