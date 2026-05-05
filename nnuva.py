#!/usr/bin/env python3

# NNUVA (Nic's Nearly Universal Video Analyzer)
# Copyright (C) 2026 Nic
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# ==============================================================================
# CHANGELOG
# ==============================================================================
# v2.9.32 (2026-05-05) - UI: Reverted NQI indicators to hexagon glyphs (⬡⬢✪) restoring column alignment and brand consistency.
# v2.9.31 (2026-05-05) - SEARCH: Replaced difflib fuzzy with Levenshtein sliding-window + 3-char prefix anchor for far better precision.
# v2.9.30 (2026-05-05) - SEARCH: Added -f/-p short flags and difflib fuzzy fallback for typo tolerance.
# v2.9.29 (2026-05-05) - SEARCH: Added --find for substring path filtering and --paths for piping absolute paths.
# v2.9.28 (2026-04-13) - INFO: Added number of entries to -i
# v2.9.27 (2026-04-13) - CORE: Overhauled NQI engine with FPS scaling, TrueHD payload isolation, and 8-bit HEVC penalties.
# v2.9.26 (2026-04-11) - UI: Simplified progress indicator to a clean, single ⬢
# v2.9.25 (2026-04-11) - FIX: Handled KeyboardInterrupt gracefully during file discovery (os.walk)
# v2.9.24 (2026-04-11) - UI: Implemented the colourful ⬢/⬡ dynamic progress bar
# v2.9.14 (2026-04-11) - UI: Updated NQI 7 (Overkill) visualizer to BOLD WHITE '✪✪✪'
# [ PASTE HISTORICAL CHANGELOGS HERE ]
# ==============================================================================

import sys
import os
import json
import subprocess
import shutil
import math
import argparse
import unicodedata
import re
import threading
import uuid
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from typing import Optional, Dict, Any, Generator

# ==============================================================================
# CONFIGURATION
# ==============================================================================
VERSION = "2.9.32"
CACHE_VERSION = 4

SUPPORTED_EXTS = {'.mkv', '.mp4', '.avi', '.ts', '.mov', '.webm', '.flv', '.m4v'}
MAX_THREADS = min(16, (os.cpu_count() or 4) * 2)

class Color:
    RESET   = '\033[0m'
    BOLD    = '\033[1m'
    BLACK   = '\033[30m'
    RED     = '\033[91m'
    ORANGE  = '\033[38;5;208m'
    GREEN   = '\033[92m'
    YELLOW  = '\033[93m'
    BLUE    = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN    = '\033[96m'
    GRAY    = '\033[90m'
    WHITE   = '\033[97m'

EXPLANATIONS = {
    'SIZE': 'Size', 'DUR': 'Runtime', 'RES': 'Res', 'NQI': 'NQI',
    'VIDEO': 'Video', 'BITRATE': 'Bitrate', 'FPS': 'FPS', 'DEPTH': 'Depth',
    'AUDIO': 'Audio', 'LANG': 'Lang', 'SUBS': 'Subs', 'HDR': 'HDR'
}

_ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# ==============================================================================
# HOMEBASE & CACHING
# ==============================================================================

class HomebaseManager:
    def __init__(self):
        self.dir = Path.home() / '.nnuva'
        self.filepath = self.dir / 'homebase.json'
        self.data = {}
        self.initialize()

    def initialize(self):
        if self.filepath.exists():
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                return
            except Exception:
                pass
        
        raw_uuid = uuid.uuid1()
        self.data = {
            "instance_id": f"NNUVA-{raw_uuid.hex[-12:].upper()}-{raw_uuid.hex[:8].upper()}",
            "installed_at": datetime.datetime.now().isoformat(),
            "version_at_install": VERSION
        }
        
        try:
            self.dir.mkdir(exist_ok=True)
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4)
        except Exception:
            pass

    def display_info(self, cache_filepath: Path, exe_path: str, cached_files_count: int):
        print(f"\n{Color.CYAN}{Color.BOLD}⬢ NNUVA SYSTEM INFO ⬢{Color.RESET}")
        print(f"{Color.GRAY}----------------------------------------{Color.RESET}")
        print(f" {Color.BOLD}Version:{Color.RESET}       v{VERSION}")
        print(f" {Color.BOLD}Binary:{Color.RESET}        {exe_path}")
        print(f" {Color.BOLD}Instance ID:{Color.RESET}   {self.data.get('instance_id', 'UNKNOWN')}")
        print(f" {Color.BOLD}Installed:{Color.RESET}     {self.data.get('installed_at', 'UNKNOWN')[:10]}")
        print(f" {Color.BOLD}Database Path:{Color.RESET} {self.dir.absolute()}")
        cache_size = format_size(cache_filepath.stat().st_size) if cache_filepath.exists() else "0B"
        print(f" {Color.BOLD}Cache Size:{Color.RESET}    {cache_size}")
        print(f" {Color.BOLD}Cached Files:{Color.RESET}  {cached_files_count}")
        print(f"{Color.GRAY}----------------------------------------{Color.RESET}\n")
        
    
class CacheManager:
    def __init__(self):
        self.dir = Path.home() / '.nnuva'
        self.filepath = self.dir / 'ffprobe_cache.json'
        self.data = {}
        self.lock = threading.Lock()
        self.is_dirty = False
        self.load()

    def load(self):
        legacy_enc = self.dir / 'ffprobe_cache.enc'
        if legacy_enc.exists():
            try: legacy_enc.unlink()
            except Exception: pass

        if self.filepath.exists():
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
                prefix = f"v{CACHE_VERSION}_"
                self.data = {k: v for k, v in raw_data.items() if k.startswith(prefix)}
                if len(self.data) < len(raw_data):
                    self.is_dirty = True
            except Exception:
                self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, val):
        with self.lock:
            self.data[key] = val
            self.is_dirty = True

    def save(self):
        if self.is_dirty:
            try:
                self.dir.mkdir(exist_ok=True)
                with open(self.filepath, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, indent=2)
            except Exception as e:
                print(f"{Color.RED}Warning: Could not save cache to {self.filepath} ({e}){Color.RESET}")

global_homebase = HomebaseManager()
global_cache = CacheManager()

# ==============================================================================
# DISPLAY & STRING UTILITIES
# ==============================================================================

def get_display_width(text: str) -> int:
    if not text: return 0
    clean = _ANSI_ESCAPE.sub('', str(text))
    text = unicodedata.normalize('NFC', clean)
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in text if unicodedata.category(c) not in ('Mn', 'Me', 'Cf'))

def align_string(text: str, target_width: int, align: str = 'left') -> str:
    text_str = str(text)
    pad = max(0, target_width - get_display_width(text_str))
    if align == 'right': return (' ' * pad) + text_str
    elif align == 'center': return (' ' * (pad // 2)) + text_str + (' ' * (pad - pad // 2))
    return text_str + (' ' * pad)

def truncate(string: str, max_width: int) -> str:
    string = unicodedata.normalize('NFC', str(string))
    if get_display_width(string) <= max_width: return string
    keep = (max_width - 3) // 2
    left, left_w = '', 0
    for c in string:
        w = 2 if unicodedata.east_asian_width(c) in 'WF' else 1
        if left_w + w <= keep: left += c; left_w += w
        else: break
    right, right_w = '', 0
    for c in reversed(string):
        w = 2 if unicodedata.east_asian_width(c) in 'WF' else 1
        if right_w + w <= keep: right = c + right; right_w += w
        else: break
    return left + '...' + right

def format_size(size_bytes: int) -> str:
    if size_bytes == 0: return '0B'
    if size_bytes >= 100 * 1024**3: return f'{size_bytes / (1024**4):.1f}TB'
    size_name = ('B', 'KB', 'MB', 'GB', 'TB')
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    return f'{round(size_bytes / p, 1):g}{size_name[i]}'

def format_duration(seconds: Optional[str]) -> str:
    if not seconds: return 'N/A'
    try:
        m, s = divmod(float(seconds), 60)
        h, m = divmod(m, 60)
        return f'{int(h)}:{int(m):02d}:{int(s):02d}' if h > 0 else f'{int(m):02d}:{int(s):02d}'
    except Exception: return 'N/A'

def style_text(text: str, col_name: str) -> str:
    if not text: return text
    s = text.strip()
    if col_name == 'NQI' and s.isdigit():
        indicators = ['⬡⬡⬡', '⬢⬡⬡', '⬢⬢⬡', '⬢⬢⬢', '✪⬡⬡', '✪✪⬡', '✪✪✪']
        colors = [Color.RED, Color.ORANGE, Color.YELLOW, Color.GREEN, Color.CYAN, Color.MAGENTA, f"{Color.WHITE}{Color.BOLD}"]
        idx = min(6, max(0, int(s) - 1))
        return f'{colors[idx]}{indicators[idx]}{Color.RESET}'
    if s == '1080p': return f'{Color.YELLOW}{text}{Color.RESET}'
    if s in ('720p', '480p'): return f'{Color.RED}{text}{Color.RESET}'
    if any(x in text for x in ('ERROR', 'CORRUPT', '[BURN]')): return f'{Color.BOLD}{Color.RED}{text}{Color.RESET}'
    if any(x in text for x in ('4K', 'HEVC', 'AV1', '10b')): return f'{Color.GREEN}{text}{Color.RESET}'
    return text

def style_folder_line(path_str: str, file_width: int, prefix: str) -> str:
    folder_name = './' if path_str == 'CURRENT DIRECTORY' else f'{Path(path_str).name}/'
    full_string = f'{prefix}{folder_name}'
    if get_display_width(full_string) > file_width:
        full_string = truncate(full_string, file_width)
    
    if full_string.startswith(prefix) and len(prefix) > 0:
        styled = f'{Color.GRAY}{prefix}{Color.RESET}{Color.WHITE}{Color.BOLD}{full_string[len(prefix):]}{Color.RESET}'
    else:
        styled = f'{Color.WHITE}{Color.BOLD}{full_string}{Color.RESET}'
    return align_string(styled, file_width)

def render_columns(data_dict: Dict, cw: Dict, cols: list, div: str) -> str:
    row = ""
    for c in cols:
        if 'is_dir_size' in data_dict and c == 'SIZE':
            aligned = align_string(data_dict['is_dir_size'], cw[c], "right")
            row += f'{div}{Color.WHITE}{Color.BOLD}{aligned}{Color.RESET}'
        elif 'is_dir_size' in data_dict:
            row += f'{div}{align_string("", cw[c])}'
        else:
            raw_val = data_dict.get(c, "N/A")
            styled_val = style_text(str(raw_val), c)
            row += f'{div}{align_string(styled_val, cw[c], "right" if c in ("SIZE", "DUR") else "center")}'
    return row

def prompt_yes_no(prompt: str) -> bool:
    try:
        resp = input(prompt).strip().lower()
        if resp not in ['y', 'yes']:
            print(f"{Color.GRAY}Operation aborted.{Color.RESET}")
            return False
        return True
    except KeyboardInterrupt:
        print(f"\n{Color.RED}Aborted.{Color.RESET}")
        return False

def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b): a, b = b, a
    if not b: return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]

def _fuzzy_token_match(token: str, words: list, max_dist: int = 1) -> bool:
    """Return True if any sliding window of any candidate word is within max_dist edits of token.
    Tokens under 4 chars are skipped. Candidate words must contain token's first 3 chars (prefix anchor)."""
    if len(token) < 4: return False
    n = len(token)
    prefix = token[:3]
    candidates = [w for w in words if prefix in w]
    if not candidates: return False
    for w in candidates:
        for wl in (n - 1, n, n + 1):
            if wl < 1 or len(w) < wl: continue
            for i in range(len(w) - wl + 1):
                if _levenshtein(token, w[i:i + wl]) <= max_dist:
                    return True
    return False

# ==============================================================================
# QUALITY INDEX
# ==============================================================================

class NQI:
    DB = {
        'base_scores': {'4K': 3.0, '1080p': 2.0, '720p': 1.0, '480p': 0.0, 'N/A': 0.0},
        'bitrate_targets_kbps': {
            '4K':    {'efficient': 15000, 'standard': 35000},
            '1080p': {'efficient': 5000,  'standard': 12000},
            '720p':  {'efficient': 2500,  'standard': 5000},
            '480p':  {'efficient': 1000,  'standard': 2000},
            'N/A':   {'efficient': 1000,  'standard': 1000}
        },
        'bonuses': {'modern_codec': 0.5, 'color_volume': 0.5, 'surround': 0.5, 'lossless_extra': 0.5},
        'labels': {
            'efficient_codecs': ['HEVC', 'H265', 'AV1'],
            'color_volume': ['HDR', 'DV', '10b'],
            'surround': ['5.1', '7.1', 'TRUEHD', 'DTS-HD', 'FLAC', 'EAC3', 'ATMOS'],
            'lossless': ['TRUEHD', 'DTS-HD', 'FLAC']
        }
    }

    @classmethod
    def calculate(cls, total_bitrate: Optional[float], res_label: str, v_codec: str, hdr_label: str, a_codec: str, fps_str: str, depth_str: str, score_audio: bool = False) -> str:
        if not total_bitrate or res_label == 'N/A': return 'N/A'
        actual_total_kbps = float(total_bitrate) / 1000
        res_key = next((k for k in ['4K', '1080p', '720p', '480p'] if k in res_label), 'N/A')
        
        # --- MODULE 1: Audio Discrepancy Isolation ---
        audio_deduction_kbps = 192 # Default stereo assumption
        if any(x in a_codec for x in cls.DB['labels']['lossless']): audio_deduction_kbps = 3500
        elif any(x in a_codec for x in ['EAC3', 'DTS', 'PCM']): audio_deduction_kbps = 768
        elif '5.1' in a_codec or '7.1' in a_codec: audio_deduction_kbps = 448
        
        est_video_kbps = max(100, actual_total_kbps - audio_deduction_kbps)

        # --- MODULE 2: FPS Target Scaling ---
        try: fps_val = float(fps_str)
        except Exception: fps_val = 24.0
        fps_multiplier = 1.5 if fps_val >= 48 else 1.0

        # --- MODULE 3: Core Health Calculation ---
        is_eff = any(x in v_codec for x in cls.DB['labels']['efficient_codecs'])
        base_target_kbps = cls.DB['bitrate_targets_kbps'][res_key]['efficient' if is_eff else 'standard']
        adjusted_target = base_target_kbps * fps_multiplier
        
        bitrate_ratio = est_video_kbps / adjusted_target
        health_modifier = math.log10(bitrate_ratio * 9 + 1)
        score = cls.DB['base_scores'][res_key] * health_modifier
        
        # --- MODULE 4: Bonuses and Penalties ---
        if is_eff: score += cls.DB['bonuses']['modern_codec']
        if any(x in hdr_label for x in cls.DB['labels']['color_volume']): score += cls.DB['bonuses']['color_volume']
        if any(x in a_codec for x in cls.DB['labels']['surround']): score += cls.DB['bonuses']['surround']
        if score_audio and any(x in a_codec for x in cls.DB['labels']['lossless']): score += cls.DB['bonuses']['lossless_extra']
        
        # Penalty: HEVC/AV1 encoded in 8-bit is an anti-pattern that introduces banding.
        if is_eff and '8b' in depth_str: score -= 0.5 

        final_score = int(math.floor(score + 0.5))
        return str(min(7, max(1, final_score)))

# ==============================================================================
# SYSTEM MANAGEMENT
# ==============================================================================

def get_system_paths():
    home_dir = Path.home()
    target_dir = home_dir / '.local' / 'bin'
    if 'ios' in sys.platform.lower() or '/var/mobile' in str(home_dir): target_dir = home_dir / 'bin'
    elif not target_dir.exists() and (home_dir / 'bin').exists(): target_dir = home_dir / 'bin'
    return target_dir, target_dir / 'nnuva', home_dir / '.nnuva'

def get_installed_version(target_path: str) -> Optional[str]:
    if not os.path.exists(target_path): return None
    try:
        with open(target_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('VERSION ='): return line.split('=')[1].strip().strip('\'"')
    except Exception: return 'Unknown'
    return None

def check_write_access(p: Path) -> bool:
    curr = p
    while not curr.exists() and curr.parent != curr: curr = curr.parent
    return os.access(curr, os.W_OK)

def perform_installation(force=False) -> bool:
    target_dir, target_path, cache_dir = get_system_paths()
    inst_ver = get_installed_version(str(target_path))
    bin_ok, cache_ok = check_write_access(target_dir), check_write_access(cache_dir)

    print(f"\n{Color.CYAN}{Color.BOLD}=== NNUVA SYSTEM INSTALLER ==={Color.RESET}")
    print(f"  {Color.BOLD}Current Version:{Color.RESET}  {f'v{inst_ver}' if inst_ver else 'Not installed'}")
    print(f"  {Color.BOLD}Proposed Version:{Color.RESET} v{VERSION}\n")
    print(f"  {Color.BOLD}Target Binary:{Color.RESET}    {target_path}")
    print(f"  {Color.BOLD}Target Homebase:{Color.RESET}  {cache_dir}\n")

    if not (bin_ok and cache_ok) and not force:
        print(f"{Color.RED}Error: Insufficient permissions.{Color.RESET}")
        return False

    if not force and not prompt_yes_no(f"Install NNUVA v{VERSION} globally? [y/N]: "):
        return False

    try:
        os.makedirs(target_dir, exist_ok=True)
        shutil.copy(os.path.abspath(__file__), target_path)
        os.chmod(target_path, 0o755)
        print(f'{Color.GREEN}✓ Executable installed.{Color.RESET}')
        cache_dir.mkdir(exist_ok=True)
        global_homebase.initialize()
        print(f'{Color.GREEN}✓ Homebase established.{Color.RESET}')
        return True
    except Exception as e:
        print(f'{Color.RED}Install failed: {e}{Color.RESET}')
        return False

def perform_uninstallation(force=False) -> None:
    _, target_path, cache_dir = get_system_paths()
    paths_to_remove = [p for p in [target_path, Path.home() / '.local' / 'bin' / 'nnuva'] if p.exists()]
    
    if not force:
        print(f"\n{Color.RED}{Color.BOLD}=== NNUVA UNINSTALLATION ==={Color.RESET}")
        for p in paths_to_remove: print(f"  {Color.BOLD}Binary:{Color.RESET}   {p}")
        print(f"  {Color.BOLD}Homebase:{Color.RESET} {cache_dir if cache_dir.exists() else 'Not found'}\n")
        
        if not paths_to_remove and not cache_dir.exists():
            print(f"{Color.GREEN}NNUVA is not installed.{Color.RESET}")
            return
        if not prompt_yes_no(f"{Color.RED}Absolutely sure you want to delete these? [y/N]: {Color.RESET}"):
            return
            
    for p in paths_to_remove:
        try: p.unlink(); print(f'{Color.GREEN}✓ Removed {p}{Color.RESET}')
        except Exception as e: print(f'{Color.RED}Failed to remove {p}: {e}{Color.RESET}')
                
    if cache_dir.exists():
        try: shutil.rmtree(cache_dir); print(f'{Color.GREEN}✓ Destroyed Homebase{Color.RESET}')
        except Exception as e: print(f'{Color.RED}Failed to remove Homebase: {e}{Color.RESET}')

def smart_install_prompt() -> None:
    if not sys.stdout.isatty(): return
    _, target_path, _ = get_system_paths()
    if os.path.abspath(__file__) == str(target_path): return
    inst_ver = get_installed_version(str(target_path))
    if inst_ver == VERSION: return
    
    print(f'{Color.CYAN}NNUVA v{VERSION} (Current script){Color.RESET}')
    if inst_ver:
        print(f'{Color.YELLOW}Your installed NNUVA is running v{inst_ver}. An update is available.{Color.RESET}')
    if perform_installation(force=False):
        sys.exit(0)
    else:
        print()

# ==============================================================================
# FFPROBE PARSER & ENGINE
# ==============================================================================

def is_valid_dir(dirpath: Path) -> bool:
    if dirpath.name.lower() == 'sample': return False
    return True

def is_valid_media(filepath: Path) -> bool:
    if not filepath.is_file() or filepath.suffix.lower() not in SUPPORTED_EXTS: return False
    path_lower = str(filepath).lower()
    return not ('sample' in path_lower and re.search(r'(^|[\W_])sample([\W_]|$)', path_lower))

def parse_ffprobe_data(data: dict, filepath: Path, size_bytes: int, dir_name: str, nqi_audio: bool) -> dict:
    fmt = data.get('format', {})
    dur_raw = fmt.get('duration')
    bitrate = float(fmt['bit_rate']) if fmt.get('bit_rate') else ((size_bytes * 8) / float(dur_raw) if dur_raw and size_bytes else None)

    v_codec, width, height, dv_profile, hdr10plus, fps, depth = 'N/A', 0, 0, None, False, 'N/A', 'N/A'
    transfer, primaries, a_codec, a_ch = '', '', 'N/A', ''
    a_langs, s_langs, s_codecs = [], [], []
    has_video = False

    for s in data.get('streams', []):
        stype = s.get('codec_type')
        lang = s.get('tags', {}).get('language', 'und').upper()[:2]

        if stype == 'video':
            has_video = True
            curr_w = s.get('width') or 0
            curr_h = s.get('height') or 0
            if (curr_w * curr_h) >= (width * height):
                width, height = curr_w, curr_h
                v_codec = s.get('codec_name', 'N/A').upper()
                transfer, primaries = s.get('color_transfer', ''), s.get('color_primaries', '')
                if '/' in (rf := s.get('r_frame_rate', '0/1')):
                    n, d = rf.split('/')
                    if d != '0': fps = f'{float(n)/float(d):.3f}'.rstrip('0').rstrip('.')
                depth = f"{s.get('bits_per_raw_sample')}b" if s.get('bits_per_raw_sample') else ('10b' if '10' in s.get('pix_fmt', '') else '8b')
                for sd in s.get('side_data_list', []):
                    if sd.get('side_data_type') == 'DOVI configuration record': dv_profile = sd.get('dv_profile')
                    if 'HDR10+' in sd.get('side_data_type', ''): hdr10plus = True

        elif stype == 'audio':
            if a_codec == 'N/A':
                a_codec = s.get('codec_name', 'N/A').upper()
                ch = s.get('channels', 0)
                a_ch = '7.1' if ch == 8 else '5.1' if ch == 6 else '2.0'
            if lang != 'UN': a_langs.append(lang)

        elif stype == 'subtitle':
            c = s.get('codec_name', '').lower()
            label = 'PGS [BURN]' if 'pgs' in c else (c.upper() if c else '')
            if label and label not in s_codecs: s_codecs.append(label)
            if lang != 'UN': s_langs.append(lang)

    if not has_video: return {'skip': True}

    if width >= 3800 or height >= 2100: res_label = '4K'
    elif width >= 1900 or height >= 1000: res_label = '1080p'
    elif width >= 1200 or height >= 700: res_label = '720p'
    else: res_label = '480p'
    
    hdr_label = f'DV P{dv_profile}' if dv_profile else ''
    hdr_label = f'{hdr_label}+' if hdr_label and hdr10plus else 'HDR10+' if hdr10plus else hdr_label
    base = 'HDR10' if transfer == 'smpte2084' or primaries == 'bt2020' else 'SDR'
    hdr_label = f'{hdr_label} ({base})' if hdr_label else base

    a_uniq = list(dict.fromkeys(a_langs))
    s_uniq = list(dict.fromkeys(s_langs))
    a_full = f'{a_codec} {a_ch}'.strip()

    return {
        'file': filepath.name, 'dir': dir_name, 'size_bytes': size_bytes, 'error': False, 'skip': False,
        'SIZE': format_size(size_bytes), 'DUR': format_duration(dur_raw), 'RES': res_label,
        'NQI': NQI.calculate(bitrate, res_label, v_codec, hdr_label, a_full, fps, depth, nqi_audio),
        'VIDEO': v_codec, 'AUDIO': a_full, 'SUBS': s_codecs[0] if s_codecs else '', 'HDR': hdr_label,
        'BITRATE': f'{round(bitrate / 1_000_000, 1)}M' if bitrate else 'N/A',
        'DEPTH': depth, 'FPS': fps, 'LANG': f"A:{','.join(a_uniq[:3])} S:{','.join(s_uniq[:3])}".strip(),
    }

def analyze_file(filepath: Path, nqi_audio: bool = False) -> dict:
    try: dir_name = str(filepath.parent.relative_to(Path.cwd()))
    except ValueError: dir_name = str(filepath.parent)
    if dir_name == '.': dir_name = 'CURRENT DIRECTORY'

    try: st = filepath.stat(); size_bytes, mtime = st.st_size, st.st_mtime
    except Exception: size_bytes, mtime = 0, 0

    err_res = {'file': filepath.name, 'dir': dir_name, 'size_bytes': size_bytes, 'error': True, 'SIZE': format_size(size_bytes), 'NQI': 'ERR'}
    
    cache_key = f"v{CACHE_VERSION}_{filepath.absolute()}_{size_bytes}_{mtime}"
    
    if cached_data := global_cache.get(cache_key):
        return parse_ffprobe_data(cached_data, filepath, size_bytes, dir_name, nqi_audio)

    cmd = ['ffprobe', '-v', 'error', '-show_entries', 
           'format=duration,bit_rate:stream=codec_type,codec_name,width,height,color_transfer,color_primaries,channels,r_frame_rate,bits_per_raw_sample,pix_fmt:stream_side_data=side_data_type,dv_profile:stream_tags=language', 
           '-print_format', 'json', str(filepath)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        data = json.loads(proc.stdout)
        global_cache.set(cache_key, data)
        return parse_ffprobe_data(data, filepath, size_bytes, dir_name, nqi_audio)
    except Exception:
        return err_res

# ==============================================================================
# N-TIER TREE DISPLAY GENERATOR
# ==============================================================================

class TreeNode:
    def __init__(self, name, is_dir=False):
        self.name = name
        self.is_dir = is_dir
        self.children = {}
        self.size = 0
        self.file_data = None

def calc_tree_size(node: TreeNode) -> int:
    if not node.is_dir: return node.size
    node.size = sum(calc_tree_size(c) for c in node.children.values())
    return node.size

def build_and_yield_tree(grouped_results: dict, top_dirs: list) -> Generator[Dict, None, None]:
    def traverse(node: TreeNode, prefix_list: list):
        files = []
        dirs = []
        for c in node.children.values():
            if c.is_dir: dirs.append(c)
            else: files.append(c)
            
        files.sort(key=lambda x: x.name.lower())
        dirs.sort(key=lambda x: x.name.lower())
        children = files + dirs
        total = len(children)
        
        for i, child in enumerate(children):
            is_last = (i == total - 1)
            base_pref = "".join(prefix_list)
            branch = "└─ " if is_last else "├─ "
            full_pref = base_pref + branch
            
            if child.is_dir:
                yield {
                    'type': 'sub_dir',
                    'name': child.name,
                    'size': child.size,
                    'prefix': full_pref
                }
                next_pref = "   " if is_last else "│  "
                yield from traverse(child, prefix_list + [next_pref])
            else:
                yield {
                    'type': 'file',
                    'name': child.name,
                    'data': child.file_data,
                    'prefix': full_pref
                }

    for td in top_dirs:
        td_size = sum(r['size_bytes'] for r in grouped_results[td])
        yield {'type': 'top_dir', 'name': td, 'size': td_size}
        
        td_root = TreeNode(td, is_dir=True)
        for r in grouped_results[td]:
            sp = r['sub_path']
            parts = list(Path(sp).parts) if sp else []
            
            curr = td_root
            for p in parts:
                if p not in curr.children:
                    curr.children[p] = TreeNode(p, is_dir=True)
                curr = curr.children[p]
                
            curr.children[r['file']] = TreeNode(r['file'], is_dir=False)
            curr.children[r['file']].file_data = r
            curr.children[r['file']].size = r['size_bytes']
            
        calc_tree_size(td_root)
        yield from traverse(td_root, [])

# ==============================================================================
# MAIN ENTRY
# ==============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description=f'NNUVA v{VERSION} — video file analyzer')
    parser.add_argument('paths', nargs='*', default=[])
    parser.add_argument('-R', '--recursive', action='store_true')
    parser.add_argument('-a', '--all', action='store_true')
    parser.add_argument('-v', '--version', action='version', version=f'NNUVA v{VERSION}')
    parser.add_argument('-l', '--list', action='store_true', help='Output a flat, sorted table without tree rendering')
    parser.add_argument('-f', '--find', metavar='QUERY', help='Filter to files whose path contains QUERY (case-insensitive)')
    parser.add_argument('-p', '--paths', action='store_true', dest='emit_paths', help='Output matching absolute file paths, one per line (skips analysis)')
    parser.add_argument('--nqi-audio', action='store_true', help='Include lossless audio bonus in NQI')
    parser.add_argument('-i', '--info', action='store_true', help='Show cache stats and install details')
    parser.add_argument('--install', action='store_true', help='Install NNUVA globally')
    parser.add_argument('--clear-cache', action='store_true', help='Clear local database cache')
    parser.add_argument('--uninstall', action='store_true', help='Remove NNUVA entirely')
    args = parser.parse_args()

    if args.uninstall: sys.exit(0 if perform_uninstallation() else 1)
    if args.clear_cache:
        if (p := global_cache.filepath).exists(): p.unlink(); print(f'{Color.GREEN}✓ Cache cleared.{Color.RESET}')
        else: print(f'{Color.GRAY}Cache already empty.{Color.RESET}')
        sys.exit(0)
    if args.info: 
        global_homebase.display_info(global_cache.filepath, os.path.abspath(__file__), len(global_cache.data))
        sys.exit(0)
    if args.install: perform_installation(force=True); sys.exit(0)

    smart_install_prompt()
    if not shutil.which('ffprobe'): sys.exit("Error: ffprobe missing")

    if not args.paths:
        try: args.paths = [f.name for f in Path('.').iterdir() if not f.name.startswith('.')]
        except Exception: pass

    files = []
    
    try:
        if not args.emit_paths:
            sys.stdout.write(f'{Color.CYAN}Discovering files...{Color.RESET}')
            sys.stdout.flush()
        
        for p_str in args.paths:
            p = Path(p_str)
            if '*' in p_str or '?' in p_str or not p.exists():
                for f in Path('.').glob(p_str):
                    if is_valid_media(f): files.append(f)
                    elif f.is_dir() and is_valid_dir(f):
                        for sub in f.iterdir():
                            if is_valid_media(sub): files.append(sub)
                continue
                
            if p.is_file() and is_valid_media(p): files.append(p)
            elif p.is_dir() and is_valid_dir(p):
                for root, dirs, files_in_root in os.walk(p):
                    dirs[:] = [d for d in dirs if is_valid_dir(Path(root) / d)]
                    files.extend(Path(root) / fname for fname in files_in_root if is_valid_media(Path(root) / fname))
                    
        if not args.emit_paths:
            sys.stdout.write('\r\033[K')
            sys.stdout.flush()
        
    except KeyboardInterrupt:
        sys.stdout.write('\r\033[K\n')
        sys.exit(f'{Color.RED}Aborted during file discovery.{Color.RESET}')

    unique_files = list(set(files))
    if not unique_files: sys.exit(f'{Color.YELLOW}No supported video files found.{Color.RESET}')

    if args.find:
        tokens = args.find.lower().split()
        exact = [f for f in unique_files if all(t in str(f).lower() for t in tokens)]
        
        if exact:
            unique_files = exact
        else:
            # Fuzzy fallback: each token must be substring OR within 1 edit of some windowed substring of a path word
            fuzzy = []
            for f in unique_files:
                path_lower = str(f).lower()
                words = [w for w in re.split(r'[\s/_.\-\[\]\(\)]+', path_lower) if w]
                if all(t in path_lower or _fuzzy_token_match(t, words) for t in tokens):
                    fuzzy.append(f)
            if fuzzy:
                print(f'{Color.GRAY}(no exact matches; showing fuzzy results for "{args.find}"){Color.RESET}', file=sys.stderr)
            unique_files = fuzzy
        
        if not unique_files: sys.exit(f'{Color.YELLOW}No files match: {args.find}{Color.RESET}')

    if args.emit_paths:
        for f in sorted(unique_files, key=lambda p: str(p).lower()):
            print(f.absolute())
        sys.exit(0)

    results = []
    executor = ThreadPoolExecutor(max_workers=MAX_THREADS)
    try:
        for i, fut in enumerate(as_completed([executor.submit(analyze_file, f, args.nqi_audio) for f in unique_files]), 1):
            if not (res := fut.result()).get('skip'): results.append(res)
            pct = i / len(unique_files)
            sys.stdout.write(f'\r{Color.CYAN}{Color.BOLD}⬢ NNUVA{Color.RESET} Scanning {i}/{len(unique_files)} ... {Color.BOLD}{int(pct * 100)}%{Color.RESET} ')
            sys.stdout.flush()
    except KeyboardInterrupt:
        sys.stdout.write('\r\033[K\n')
        executor.shutdown(wait=False, cancel_futures=True)
        sys.exit(f'{Color.RED}Aborted.{Color.RESET}')
    finally:
        sys.stdout.write('\r\033[K')
        sys.stdout.flush()
        executor.shutdown(wait=False)
        global_cache.save()

    grouped = defaultdict(list)
    top_sizes = defaultdict(int)
    
    for r in results:
        parts = Path(r['dir']).parts if r['dir'] != 'CURRENT DIRECTORY' else []
        td = parts[0] if parts else 'CURRENT DIRECTORY'
        sp = str(Path(*parts[1:])) if len(parts) > 1 else ''
        r['top_dir'], r['sub_path'] = td, sp
        grouped[td].append(r)
        top_sizes[td] += r['size_bytes']

    top_dirs = sorted(grouped.keys(), key=lambda x: (0 if x == 'CURRENT DIRECTORY' else 1, x.lower()))
    cols = ['SIZE', 'DUR', 'RES', 'NQI', 'VIDEO', 'BITRATE', 'FPS', 'DEPTH', 'AUDIO', 'LANG', 'SUBS', 'HDR'] if args.all else ['SIZE', 'DUR', 'RES', 'NQI', 'VIDEO', 'AUDIO', 'SUBS', 'HDR']

    try:
        tw = os.get_terminal_size().columns - 1
    except OSError:
        tw = int(os.environ.get('COLUMNS', 120)) - 1

    cw = {c: max([get_display_width(c), get_display_width(EXPLANATIONS[c])] + [get_display_width(str(r.get(c, ''))) for r in results] + ([get_display_width(format_size(sz)) for sz in top_sizes.values()] if c == 'SIZE' else [0])) for c in cols}
    fw  = max(20, tw - sum(cw.values()) - (len(cols) * 3))
    sep, div = f'{Color.GRAY}{"-" * tw}{Color.RESET}', f' {Color.GRAY}|{Color.RESET} '

    print(f'{sep}\n{Color.BOLD}{align_string("FILE", fw)}{Color.RESET}' + ''.join(f'{div}{Color.BOLD}{align_string(c, cw[c], "right" if c in ("SIZE", "DUR") else "center")}{Color.RESET}' for c in cols) + f'\n{sep}')

    if args.list:
        flat_results = sorted(results, key=lambda x: x['file'].lower())
        for r in flat_results:
            flat_name = f"{r['dir']}/{r['file']}" if r['dir'] != 'CURRENT DIRECTORY' else r['file']
            if get_display_width(flat_name) > fw:
                truncated_name = truncate(flat_name, fw)
                name_styled = align_string(f'{Color.WHITE}{Color.BOLD}{truncated_name}{Color.RESET}', fw)
            else:
                if r['dir'] != 'CURRENT DIRECTORY':
                    name_styled = align_string(f'{Color.GRAY}{r["dir"]}/{Color.RESET}{Color.WHITE}{Color.BOLD}{r["file"]}{Color.RESET}', fw)
                else:
                    name_styled = align_string(f'{Color.WHITE}{Color.BOLD}{r["file"]}{Color.RESET}', fw)
            
            print(name_styled + render_columns(r, cw, cols, div))
    else:
        for idx, item in enumerate(build_and_yield_tree(grouped, top_dirs)):
            if item['type'] == 'top_dir':
                if idx > 0: print((' ' * fw) + ''.join(f'{div}{" " * cw[c]}' for c in cols))
                print(style_folder_line(item['name'], fw, '') + render_columns({'is_dir_size': format_size(item['size'])}, cw, cols, div))
            
            elif item['type'] == 'sub_dir':
                print(style_folder_line(item['name'], fw, prefix=item['prefix']) + render_columns({'is_dir_size': format_size(item['size'])}, cw, cols, div))
            
            elif item['type'] == 'file':
                pref = item['prefix']
                display_str = f"{pref}{item['name']}"
                if get_display_width(display_str) > fw:
                    truncated_name = truncate(display_str, fw)[len(pref):]
                    name_styled = align_string(f'{Color.GRAY}{pref}{Color.RESET}{truncated_name}', fw)
                else:
                    name_styled = align_string(f'{Color.GRAY}{pref}{Color.RESET}{item["name"]}', fw)
                
                print(name_styled + render_columns(item['data'], cw, cols, div))

    print(f'{sep}\n{align_string(" ", fw)}' + ''.join(f'{div}{Color.GRAY}{align_string(EXPLANATIONS[c], cw[c], "right" if c in ("SIZE", "DUR") else "center")}{Color.RESET}' for c in cols) + f'\n{sep}')

if __name__ == '__main__':
    main()
