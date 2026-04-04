#!/usr/bin/env python3

# NNUVA (Nic's Nearly Universal Video Analyzer)
# Copyright (C) 2026 Nic
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import sys
import os
import json
import subprocess
import shutil
import math
import argparse
import unicodedata
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==============================================================================
# CONFIGURATION
# ==============================================================================
VERSION = "1.6.9"
SUPPORTED_EXTS = {'.mkv', '.mp4', '.avi', '.ts', '.mov', '.webm', '.flv', '.m4v'}
MAX_THREADS = min(32, (os.cpu_count() or 4) * 2)

class Color:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'
    WHITE = '\033[97m'

EXPLANATIONS = {
    'SIZE': 'Size', 'DUR': 'Runtime', 'RES': 'Res', 'NQI': 'NQI',
    'VIDEO': 'Video', 'BITRATE': 'Bitrate', 'FPS': 'FPS', 'DEPTH': 'Depth',
    'AUDIO': 'Audio', 'LANG': 'Lang', 'SUBS': 'Subs', 'HDR': 'HDR'
}

# ==============================================================================
# STRING FORMATTING & DISPLAY MATH (JIS/NFC/ZERO-WIDTH SAFE)
# ==============================================================================

def get_display_width(text):
    if not text: return 0
    # Strip ANSI escape sequences for width calculation to prevent column skew
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_text = ansi_escape.sub('', str(text))
    text = unicodedata.normalize('NFC', clean_text)
    width = 0
    for c in text:
        if unicodedata.category(c) in ('Mn', 'Me', 'Cf'): continue
        width += 2 if unicodedata.east_asian_width(c) in 'WF' else 1
    return width

def pad_string(text, target_width):
    padding_needed = max(0, target_width - get_display_width(text))
    return str(text) + (" " * padding_needed)

def truncate(string, max_width):
    string = unicodedata.normalize('NFC', str(string))
    if get_display_width(string) <= max_width: return string
    keep = (max_width - 3) // 2
    left, left_w = "", 0
    for c in string:
        w = 0 if unicodedata.category(c) in ('Mn', 'Me', 'Cf') else (2 if unicodedata.east_asian_width(c) in 'WF' else 1)
        if left_w + w <= keep: left += c; left_w += w
        else: break
    right, right_w = "", 0
    for c in reversed(string):
        w = 0 if unicodedata.category(c) in ('Mn', 'Me', 'Cf') else (2 if unicodedata.east_asian_width(c) in 'WF' else 1)
        if right_w + w <= keep: right = c + right; right_w += w
        else: break
    return left + "..." + right

# ==============================================================================
# QUALITY SCORING & SIZE FORMATTING
# ==============================================================================

def format_size(size_bytes):
    if size_bytes == 0: return "0B"
    # Logic: Cross 100GB -> Switch to TB (e.g. 102.4GB becomes 0.1TB)
    if size_bytes >= 100 * 1024**3:
        return f"{size_bytes / (1024**4):.1f}TB"
    
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

def calculate_quality_score(bitrate, res_label, v_codec, hdr_label, a_codec):
    if not bitrate or res_label == "N/A": return "N/A"
    eff = 0.5 if any(x in v_codec for x in ["HEVC", "H265"]) else 0.4 if "AV1" in v_codec else 1.0
    target_kbps = 25000 if "4K" in res_label else 7000 if "1080p" in res_label else 3000
    target_kbps *= eff
    actual_kbps = float(bitrate) / 1000
    ratio = actual_kbps / target_kbps
    score = min(3.5, ratio * 3.5)
    if "4K" in res_label: score += 0.5
    if any(x in hdr_label for x in ["HDR", "DV", "10b"]): score += 0.5
    if any(x in a_codec for x in ["TRUEHD", "DTS-HD", "FLAC"]): score += 0.5
    return str(int(round(min(5.0, max(1.0, score)))))

# ==============================================================================
# SYSTEM MANAGEMENT
# ==============================================================================

def get_installed_version(target_path):
    if not os.path.exists(target_path): return None
    try:
        with open(target_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('VERSION ='):
                    return line.split('=')[1].strip().strip('\'"')
    except: return "Unknown"
    return None

def perform_installation(is_update=False):
    current_script = os.path.abspath(__file__)
    target_path = os.path.expanduser("~/.local/bin/nnuva")
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    shutil.copy(current_script, target_path)
    os.chmod(target_path, 0o755)
    print(f"{Color.GREEN}✓ NNUVA updated to {target_path}{Color.RESET}")
    sys.exit(0)

def smart_install_prompt():
    if not sys.stdout.isatty(): return
    target_path = os.path.expanduser("~/.local/bin/nnuva")
    if os.path.abspath(__file__) == target_path: return
    inst_ver = get_installed_version(target_path)
    if inst_ver == VERSION: return
    print(f"{Color.CYAN}NNUVA v{VERSION} (Current standalone){Color.RESET}")
    try:
        resp = input(f"Update global install from v{inst_ver or 'N/A'} to v{VERSION}? [y/N]: ").strip().lower()
        if resp in ['y', 'yes']: perform_installation()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)

# ==============================================================================
# CORE ENGINE
# ==============================================================================

def analyze_file(filepath):
    try:
        rel_dir = filepath.parent.relative_to(Path.cwd())
        dir_name = str(rel_dir)
    except ValueError: dir_name = str(filepath.parent)
    if dir_name == ".": dir_name = "CURRENT DIRECTORY"
    
    size_bytes = os.path.getsize(filepath)
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration,bit_rate:stream=codec_type,codec_name,width,height,color_transfer,color_primaries,channels,r_frame_rate,bits_per_raw_sample,pix_fmt:stream_side_data=side_data_type,dv_profile:stream_tags=language', '-print_format', 'json', str(filepath)]
    try:
        data = json.loads(subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout)
    except: return {"file": filepath.name, "dir": dir_name, "size_bytes": size_bytes, "error": True, "SIZE": format_size(size_bytes)}

    fmt = data.get('format', {})
    dur_raw = fmt.get('duration')
    bitrate = fmt.get('bit_rate') or ((size_bytes * 8) / float(dur_raw)) if dur_raw else None
    
    v_codec, width, height, transfer, primaries, dv_profile, hdr10plus, fps, depth = "N/A", None, None, "", "", None, False, "N/A", "N/A"
    a_codec, a_ch, audio_langs, sub_langs, sub_codecs = "N/A", "", [], [], set()
    has_video = False
    for stream in data.get('streams', []):
        stype = stream.get('codec_type')
        lang = stream.get('tags', {}).get('language', 'und').upper()[:2]
        if stype == 'video':
            has_video = True
            v_codec = stream.get('codec_name', 'N/A').upper()
            width, height = stream.get('width'), stream.get('height')
            transfer, primaries = stream.get('color_transfer', ''), stream.get('color_primaries', '')
            if '/' in (r_fps := stream.get('r_frame_rate', '0/1')):
                n, d = r_fps.split('/')
                if d != '0': fps = f"{float(n)/float(d):.3f}".rstrip('0').rstrip('.')
            pix_fmt = stream.get('pix_fmt', '')
            depth = f"{stream.get('bits_per_raw_sample')}b" if stream.get('bits_per_raw_sample') else ("10b" if '10' in pix_fmt else "8b")
            for sd in stream.get('side_data_list', []):
                if sd.get('side_data_type') == 'DOVI configuration record': dv_profile = sd.get('dv_profile')
                if 'HDR10+' in sd.get('side_data_type', ''): hdr10plus = True
        elif stype == 'audio':
            if a_codec == "N/A":
                a_codec = stream.get('codec_name', 'N/A').upper()
                ch = stream.get('channels', 0)
                a_ch = "7.1" if ch == 8 else "5.1" if ch == 6 else "2.0"
            if lang != 'UN': audio_langs.append(lang)
        elif stype == 'subtitle':
            c = stream.get('codec_name', '').lower()
            if 'pgs' in c: sub_codecs.add('PGS [BURN]')
            elif c: sub_codecs.add('Text')
            if lang != 'UN': sub_langs.append(lang)

    if not has_video: return {"skip": True}
    res_label = "4K" if (width or 0) >= 3800 else "1080p" if (width or 0) >= 1900 else "720p" if (width or 0) >= 1200 else "480p"
    hdr_label = f"DV P{dv_profile}" if dv_profile else ""
    hdr_label = f"{hdr_label}+" if hdr_label and hdr10plus else "HDR10+" if hdr10plus else hdr_label
    base = "HDR10" if transfer == "smpte2084" or primaries == "bt2020" else "SDR"
    hdr_label = f"{hdr_label} ({base})" if hdr_label else base
    a_uniq, s_uniq = list(dict.fromkeys(audio_langs)), list(dict.fromkeys(sub_langs))
    a_full = f"{a_codec} {a_ch}".strip()
    return {
        "file": filepath.name, "dir": dir_name, "size_bytes": size_bytes, "error": False, "skip": False, 
        "SIZE": format_size(size_bytes), "DUR": format_duration(dur_raw), "RES": res_label, 
        "NQI": calculate_quality_score(bitrate, res_label, v_codec, hdr_label, a_full), "VIDEO": v_codec, 
        "AUDIO": a_full, "SUBS": next(iter(sub_codecs), ""), "HDR": hdr_label, 
        "BITRATE": f"{round(float(bitrate)/1000000,1)}M" if bitrate else "N/A", "DEPTH": depth, "FPS": fps, 
        "LANG": f"A:{','.join(a_uniq[:3])} S:{','.join(s_uniq[:3])}".strip()
    }

def style_text(text, col_name):
    if not text: return text
    s = text.strip()
    if col_name == "NQI" and s.isdigit():
        c = Color.GREEN if int(s) >= 4 else Color.YELLOW if int(s) >= 3 else Color.RED
        return f"{c}■{Color.RESET}" + (" " * (len(text)-1))
    if s == "1080p": return f"{Color.YELLOW}{text}{Color.RESET}"
    if s in ["720p", "480p"]: return f"{Color.RED}{text}{Color.RESET}"
    if any(x in text for x in ["ERROR", "CORRUPT", "[BURN]"]): return f"{Color.BOLD}{Color.RED}{text}{Color.RESET}"
    if any(x in text for x in ["4K", "HEVC", "AV1", "10b"]): return f"{Color.GREEN}{text}{Color.RESET}"
    return text

def style_folder_line(path_str, file_width, prefix=" ┌─ "):
    path_obj = Path(path_str)
    folder_name = f"{path_obj.name}/"
    parent_path = str(path_obj.parent)
    if parent_path == ".": parent_path = ""
    else: parent_path += "/"
    # Build styled version
    styled = f"{Color.GRAY}{Color.BOLD}{prefix}{parent_path}{Color.RESET}{Color.WHITE}{Color.BOLD}{folder_name}{Color.RESET}"
    # Padding math using visual width only
    vis_width = get_display_width(f"{prefix}{parent_path}{folder_name}")
    return styled + (" " * max(0, file_width - vis_width))

def main():
    smart_install_prompt()
    if not shutil.which('ffprobe'): print("Error: ffprobe missing"); sys.exit(1)
    parser = argparse.ArgumentParser()
    parser.add_argument('paths', nargs='*', default=['.'])
    parser.add_argument('-R', '--recursive', action='store_true')
    parser.add_argument('-a', '--all', action='store_true')
    args = parser.parse_args()

    files, skipped = [], []
    for p_str in args.paths:
        p = Path(p_str)
        if not p.exists():
            for f in Path('.').glob(p_str):
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS: files.append(f)
            continue
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS: files.append(p)
        elif p.is_dir():
            search = p.rglob("*") if args.recursive else p.glob("*")
            for f in search:
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS: files.append(f)
                elif f.is_dir() and not args.recursive: skipped.append(f.name)
    
    if not files and not skipped: print("Error: Nothing found"); sys.exit(1)
    
    results = []
    if files:
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as ex:
            futures = [ex.submit(analyze_file, f) for f in files]
            for i, f in enumerate(as_completed(futures), 1):
                res = f.result()
                if not res.get("skip"): results.append(res)
                sys.stdout.write(f"\r{Color.BOLD}Scanning {len(files)} files... {int(i/len(files)*100)}%{Color.RESET}")
                sys.stdout.flush()
        sys.stdout.write('\r\033[K')

    results.sort(key=lambda x: (0 if x['dir'] == "CURRENT DIRECTORY" else 1, x['dir'], x['file']))
    dir_sizes = {d: sum(r['size_bytes'] for r in results if r['dir'] == d) for d in set(r['dir'] for r in results)}

    cols = ['SIZE', 'DUR', 'RES', 'NQI', 'VIDEO', 'AUDIO', 'SUBS', 'HDR']
    if args.all: cols = ['SIZE', 'DUR', 'RES', 'NQI', 'VIDEO', 'BITRATE', 'FPS', 'DEPTH', 'AUDIO', 'LANG', 'SUBS', 'HDR']
    
    tw = shutil.get_terminal_size().columns - 1
    cw = {c: max(get_display_width(c), get_display_width(EXPLANATIONS[c]), max((get_display_width(r.get(c, "")) for r in results), default=0)) for c in cols}
    fw = max(20, tw - sum(cw.values()) - (len(cols) * 3))
    sep = f"{Color.GRAY}{'-' * tw}{Color.RESET}"
    div = f" {Color.GRAY}|{Color.RESET} "

    print(f"{sep}\n{Color.BOLD}{pad_string('FILE', fw)}{Color.RESET}" + "".join([f"{div}{Color.BOLD}{pad_string(c, cw[c])}{Color.RESET}" for c in cols]) + f"\n{sep}")
    
    dir_names = list(dict.fromkeys(r['dir'] for r in results))
    for i, d in enumerate(dir_names):
        if i > 0: print((" " * fw) + "".join([f"{div}{' ' * cw[c]}" for c in cols]))
        row_str = style_folder_line(d, fw)
        for c in cols:
            if c == 'SIZE': row_str += f"{div}{Color.GRAY}{Color.BOLD}{pad_string(format_size(dir_sizes[d]), cw[c])}{Color.RESET}"
            else: row_str += f"{div}{pad_string('', cw[c])}"
        print(row_str)

        files_in_dir = [r for r in results if r['dir'] == d]
        for j, r in enumerate(files_in_dir):
            prefix = " └─ " if j == len(files_in_dir) - 1 else " ├─ "
            row_str = pad_string(truncate(f"{prefix}{r['file']}", fw), fw)
            for c in cols:
                row_str += f"{div}{style_text(pad_string(r.get(c, 'N/A'), cw[c]), c)}"
            print(row_str)

    if skipped and not args.recursive:
        print((" " * fw) + "".join([f"{div}{' ' * cw[c]}" for c in cols]))
        print(f"{Color.GRAY}{Color.BOLD}{pad_string(' ┌─ Unscanned Subdirectories/', fw)}{Color.RESET}" + "".join([f"{div}{' '*cw[c]}" for c in cols]))
        for k, s in enumerate(skipped):
            prefix = " └─ " if k == len(skipped)-1 else " ├─ "
            print(f"{Color.GRAY}{Color.BOLD}{pad_string(prefix+s+'/', fw)}{Color.RESET}" + "".join([f"{div}{' '*cw[c]}" for c in cols]))
    print(f"{sep}\n{pad_string(' ', fw)}" + "".join([f"{div}{Color.GRAY}{pad_string(EXPLANATIONS[c], cw[c])}{Color.RESET}" for c in cols]) + f"\n{sep}")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: sys.stdout.write('\033[?25h\r\033[K'); print("\nAborted."); sys.exit(1)
