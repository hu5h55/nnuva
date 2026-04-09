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
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from typing import Optional

# ==============================================================================
# CONFIGURATION
# ==============================================================================
VERSION = "2.4.0"

# Changelog:
#   2.4.0 - Remove encryption; revert to pretty-printed JSON for transparency and debugging
#   2.3.0 - Implement native stream cipher to encrypt the local cache file (.enc)
#   2.2.0 - Add explicit consent prompts and path visibility for install/uninstall
#   2.1.0 - Add --uninstall flag to completely remove the executable and cache directory
#   2.0.0 - MILESTONE: Introduce ~/.nnuva/ local database to cache ffprobe scans
#   1.33.0 - Ultimate tree alignment fix; enforce strict 3-char prefix multiples
#   1.32.0 - Final fix for tree alignment; remove dynamic leading spaces
#   1.31.0 - Fix missing vertical pipes in subdirectories; correct parent state tracking
#   1.30.0 - Permanently lock in clean indentation (no vertical pipes) for subfolders
#   1.29.2 - Update L5 to Prestige symbol ✪⬡⬡; retighten math to restore L4 ⬢⬢⬢
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
# LOCAL DATABASE & CACHING
# ==============================================================================

class CacheManager:
    def __init__(self):
        self.dir = Path.home() / '.nnuva'
        self.filepath = self.dir / 'ffprobe_cache.json'
        self.data = {}
        self.lock = threading.Lock()
        self.is_dirty = False
        self.load()

    def load(self):
        # Clean up the old encrypted file from v2.3.0 if it exists
        legacy_enc_file = self.dir / 'ffprobe_cache.enc'
        if legacy_enc_file.exists():
            try:
                legacy_enc_file.unlink()
            except Exception:
                pass

        if self.filepath.exists():
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
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
                # Save as formatted JSON so the user can easily read/grep it
                with open(self.filepath, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, indent=2)
            except Exception as e:
                print(f"{Color.RED}Warning: Could not save cache to {self.filepath} ({e}){Color.RESET}")

global_cache = CacheManager()

# ==============================================================================
# STRING FORMATTING & DISPLAY MATH
# ==============================================================================

def get_display_width(text: str) -> int:
    if not text: return 0
    clean = _ANSI_ESCAPE.sub('', str(text))
    text = unicodedata.normalize('NFC', clean)
    width = 0
    for c in text:
        if unicodedata.category(c) in ('Mn', 'Me', 'Cf'): continue
        width += 2 if unicodedata.east_asian_width(c) in 'WF' else 1
    return width

def align_string(text: str, target_width: int, align: str = 'left') -> str:
    text_str = str(text)
    w = get_display_width(text_str)
    pad = max(0, target_width - w)
    
    if align == 'right':
        return (' ' * pad) + text_str
    elif align == 'center':
        pad_left = pad // 2
        pad_right = pad - pad_left
        return (' ' * pad_left) + text_str + (' ' * pad_right)
    else:
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

# ==============================================================================
# NQI (Nic's Quality Index) ENGINE
# ==============================================================================

class NQI:
    """Modular engine for calculating media quality scores based on modern standards."""
    
    DB = {
        'base_scores': {
            '4K': 2.5,
            '1080p': 1.5,
            '720p': 0.5,
            '480p': 0.0,
            'N/A': 0.0
        },
        'bitrate_targets_kbps': {
            '4K':    {'efficient': 8000,  'standard': 25000},
            '1080p': {'efficient': 3000,  'standard': 8000},
            '720p':  {'efficient': 1500,  'standard': 3000},
            '480p':  {'efficient': 800,   'standard': 1500},
            'N/A':   {'efficient': 1000,  'standard': 1000}
        },
        'bonuses': {
            'modern_codec': 0.5,
            'color_volume': 0.5,
            'surround': 0.5,
            'lossless_extra': 0.5
        },
        'labels': {
            'efficient_codecs': ['HEVC', 'H265', 'AV1'],
            'color_volume': ['HDR', 'DV', '10b'],
            'surround': ['5.1', '7.1', 'TRUEHD', 'DTS-HD', 'FLAC'],
            'lossless': ['TRUEHD', 'DTS-HD', 'FLAC']
        }
    }

    @classmethod
    def calculate(cls, bitrate: Optional[float], res_label: str, v_codec: str, hdr_label: str, a_codec: str, score_audio: bool = False) -> str:
        if not bitrate or res_label == 'N/A':
            return 'N/A'

        actual_kbps = float(bitrate) / 1000
        score = 0.0

        res_key = 'N/A'
        for key in ['4K', '1080p', '720p', '480p']:
            if key in res_label:
                res_key = key
                break

        base_res_score = cls.DB['base_scores'][res_key]
        
        is_efficient = any(x in v_codec for x in cls.DB['labels']['efficient_codecs'])
        codec_type = 'efficient' if is_efficient else 'standard'
        target_kbps = cls.DB['bitrate_targets_kbps'][res_key][codec_type]

        health_ratio = min(1.0, actual_kbps / target_kbps)
        health_modifier = math.log10(health_ratio * 9 + 1)
        score += (base_res_score * health_modifier)

        if is_efficient:
            score += cls.DB['bonuses']['modern_codec']
            
        if any(x in hdr_label for x in cls.DB['labels']['color_volume']):
            score += cls.DB['bonuses']['color_volume']
            
        if any(x in a_codec for x in cls.DB['labels']['surround']):
            score += cls.DB['bonuses']['surround']
            
        if score_audio and any(x in a_codec for x in cls.DB['labels']['lossless']):
            score += cls.DB['bonuses']['lossless_extra']

        final_score = int(round(score))
        return str(min(5, max(1, final_score)))


# ==============================================================================
# GENERAL UTILITIES
# ==============================================================================

def format_size(size_bytes: int) -> str:
    if size_bytes == 0: return '0B'
    if size_bytes >= 100 * 1024**3:
        return f'{size_bytes / (1024**4):.1f}TB'
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
    except Exception:
        return 'N/A'

# ==============================================================================
# SYSTEM MANAGEMENT
# ==============================================================================

def get_system_paths():
    """Returns (bin_dir, bin_path, cache_dir) tailored for the active OS."""
    home_dir = Path.home()
    target_dir = home_dir / '.local' / 'bin'
    
    if 'ios' in sys.platform.lower() or '/var/mobile' in str(home_dir):
        target_dir = home_dir / 'bin'
    elif not target_dir.exists() and (home_dir / 'bin').exists():
        target_dir = home_dir / 'bin'
        
    target_path = target_dir / 'nnuva'
    cache_dir = home_dir / '.nnuva'
    
    return target_dir, target_path, cache_dir

def get_installed_version(target_path: str) -> Optional[str]:
    if not os.path.exists(target_path): return None
    try:
        with open(target_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('VERSION ='):
                    return line.split('=')[1].strip().strip('\'"')
    except Exception:
        return 'Unknown'
    return None

def perform_installation(force=False) -> bool:
    target_dir, target_path, cache_dir = get_system_paths()
    current_script = os.path.abspath(__file__)

    if not force:
        print(f"\n{Color.CYAN}{Color.BOLD}=== NNUVA INSTALLATION ==={Color.RESET}")
        print("NNUVA will be copied to your system to allow global execution.")
        print("It will also establish a local cache directory for faster rescans.\n")
        print(f"  {Color.BOLD}Executable:{Color.RESET} {target_path}")
        print(f"  {Color.BOLD}Database:  {Color.RESET} {cache_dir}\n")
        try:
            resp = input(f"Proceed with installation? [y/N]: ").strip().lower()
            if resp not in ['y', 'yes']:
                print(f"{Color.GRAY}Installation aborted.{Color.RESET}")
                return False
        except KeyboardInterrupt:
            print(f"\n{Color.RED}Aborted.{Color.RESET}")
            return False

    try:
        os.makedirs(target_dir, exist_ok=True)
        shutil.copy(current_script, target_path)
    except Exception as e:
        print(f'{Color.RED}Install failed: Could not write to {target_dir}. ({e}){Color.RESET}')
        return False

    try:
        os.chmod(target_path, 0o755)
    except Exception:
        pass

    print(f'{Color.GREEN}✓ NNUVA executable installed to {target_path}{Color.RESET}')
    
    try:
        cache_dir.mkdir(exist_ok=True)
        print(f'{Color.GREEN}✓ NNUVA package database initialized at {cache_dir}{Color.RESET}')
    except Exception:
        pass
    
    if str(target_dir) not in os.environ.get('PATH', ''):
        print(f'{Color.YELLOW}Note: {target_dir} is not currently in your PATH.{Color.RESET}')
        print(f'{Color.YELLOW}You may need to add it manually or restart your terminal app.{Color.RESET}')
        
    return True

def perform_uninstallation(force=False) -> None:
    target_dir, target_path, cache_dir = get_system_paths()
    
    alt_target_path = Path.home() / '.local' / 'bin' / 'nnuva'
    
    paths_to_remove = [p for p in [target_path, alt_target_path] if p.exists()]
    
    if not force:
        print(f"\n{Color.RED}{Color.BOLD}=== NNUVA UNINSTALLATION ==={Color.RESET}")
        print("This will completely remove the NNUVA executable and your local scan database.\n")
        
        if paths_to_remove:
            for p in paths_to_remove:
                print(f"  {Color.BOLD}Removing Executable:{Color.RESET} {p}")
        else:
             print(f"  {Color.GRAY}Executable: Not found{Color.RESET}")
             
        if cache_dir.exists():
            print(f"  {Color.BOLD}Removing Database:  {Color.RESET} {cache_dir}")
        else:
            print(f"  {Color.GRAY}Database: Not found{Color.RESET}")
            
        print()
        
        if not paths_to_remove and not cache_dir.exists():
            print(f"{Color.GREEN}NNUVA is not installed on this system.{Color.RESET}")
            return

        try:
            resp = input(f"{Color.RED}Are you absolutely sure you want to delete these files? [y/N]: {Color.RESET}").strip().lower()
            if resp not in ['y', 'yes']:
                print(f"{Color.GRAY}Uninstallation aborted.{Color.RESET}")
                return
        except KeyboardInterrupt:
            print(f"\n{Color.RED}Aborted.{Color.RESET}")
            return
            
    removed_bin = False
    for p in paths_to_remove:
        try:
            p.unlink()
            removed_bin = True
            print(f'{Color.GREEN}✓ Removed executable from {p}{Color.RESET}')
        except Exception as e:
            print(f'{Color.RED}Failed to remove {p}: {e}{Color.RESET}')
                
    if cache_dir.exists():
        try:
            shutil.rmtree(cache_dir)
            print(f'{Color.GREEN}✓ Removed package database and cache at {cache_dir}{Color.RESET}')
        except Exception as e:
            print(f'{Color.RED}Failed to remove cache dir {cache_dir}: {e}{Color.RESET}')
        
    print(f'{Color.BOLD}NNUVA has been completely uninstalled.{Color.RESET}')

def smart_install_prompt() -> None:
    if not sys.stdout.isatty(): return
    
    target_dir, target_path, cache_dir = get_system_paths()
    if os.path.abspath(__file__) == str(target_path): return
    
    inst_ver = get_installed_version(str(target_path))
    if inst_ver == VERSION: return
    print(f'{Color.CYAN}NNUVA v{VERSION} (Current standalone){Color.RESET}')
    
    if inst_ver:
        try:
            with open(os.path.abspath(__file__), 'r', encoding='utf-8') as f:
                in_changelog = False
                changes_found = False
                lines_printed = 0
                for line in f:
                    if line.startswith('# Changelog:'):
                        in_changelog = True
                        continue
                    if in_changelog:
                        if not line.startswith('#'):
                            break
                        match = re.search(r'#\s+([0-9]+\.[0-9]+\.[0-9]+)', line)
                        if match and match.group(1) == inst_ver:
                            break
                            
                        if lines_printed >= 5:
                            print(f'{Color.GRAY}  ...and earlier changes.{Color.RESET}')
                            break
                            
                        if not changes_found:
                            print(f'\n{Color.BOLD}What\'s new:{Color.RESET}')
                            changes_found = True
                            
                        print(line.replace('#', '', 1).rstrip('\n'))
                        lines_printed += 1
                if changes_found:
                    print()
        except Exception:
            pass

    try:
        resp = input(f'Update global install from v{inst_ver or "N/A"} to v{VERSION}? [y/N]: ').strip().lower()
        if resp in ['y', 'yes']:
            perform_installation(force=True)
            sys.exit(0)
    except KeyboardInterrupt:
        print('\nAborted.')
        os._exit(1)

# ==============================================================================
# CORE ENGINE
# ==============================================================================

def is_valid_media(filepath: Path) -> bool:
    if not filepath.is_file():
        return False
    if filepath.suffix.lower() not in SUPPORTED_EXTS:
        return False
    path_lower = str(filepath).lower()
    if 'sample' in path_lower:
        if re.search(r'(^|[\W_])sample([\W_]|$)', path_lower):
            return False
    return True

def is_valid_dir(dirpath: Path) -> bool:
    if dirpath.name.lower() == 'sample':
        return False
    return True

def analyze_file(filepath: Path, nqi_audio: bool = False) -> dict:
    try:
        rel_dir = filepath.parent.relative_to(Path.cwd())
        dir_name = str(rel_dir)
    except ValueError:
        dir_name = str(filepath.parent)
    if dir_name == '.':
        dir_name = 'CURRENT DIRECTORY'

    try:
        file_stat = filepath.stat()
        size_bytes = file_stat.st_size
        mtime = file_stat.st_mtime
    except Exception:
        size_bytes = 0
        mtime = 0

    error_result = {
        'file': filepath.name, 'dir': dir_name,
        'size_bytes': size_bytes, 'error': True,
        'SIZE': format_size(size_bytes), 'NQI': 'ERR',
    }

    cache_key = f"{filepath.absolute()}_{size_bytes}_{mtime}"
    cached_ffprobe = global_cache.get(cache_key)

    if cached_ffprobe:
        data = cached_ffprobe
    else:
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries',
            'format=duration,bit_rate:'
            'stream=codec_type,codec_name,width,height,color_transfer,color_primaries,'
            'channels,r_frame_rate,bits_per_raw_sample,pix_fmt:'
            'stream_side_data=side_data_type,dv_profile:'
            'stream_tags=language',
            '-print_format', 'json', str(filepath),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            data = json.loads(proc.stdout)
            global_cache.set(cache_key, data)
        except subprocess.TimeoutExpired:
            return error_result
        except json.JSONDecodeError:
            return error_result
        except Exception:
            return error_result

    fmt     = data.get('format', {})
    dur_raw = fmt.get('duration')

    raw_bitrate = fmt.get('bit_rate')
    if raw_bitrate:
        bitrate: Optional[float] = float(raw_bitrate)
    elif dur_raw and size_bytes > 0:
        bitrate = (size_bytes * 8) / float(dur_raw)
    else:
        bitrate = None

    v_codec, width, height   = 'N/A', None, None
    transfer, primaries       = '', ''
    dv_profile, hdr10plus    = None, False
    fps, depth               = 'N/A', 'N/A'
    a_codec, a_ch            = 'N/A', ''
    audio_langs: list[str]   = []
    sub_langs:   list[str]   = []
    sub_codecs:  list[str]   = []
    has_video = False

    for stream in data.get('streams', []):
        stype = stream.get('codec_type')
        lang  = stream.get('tags', {}).get('language', 'und').upper()[:2]

        if stype == 'video':
            has_video = True
            v_codec   = stream.get('codec_name', 'N/A').upper()
            width, height = stream.get('width'), stream.get('height')
            transfer  = stream.get('color_transfer', '')
            primaries = stream.get('color_primaries', '')
            r_fps     = stream.get('r_frame_rate', '0/1')
            if '/' in r_fps:
                n, d = r_fps.split('/')
                if d != '0':
                    fps = f'{float(n)/float(d):.3f}'.rstrip('0').rstrip('.')
            pix_fmt = stream.get('pix_fmt', '')
            depth = (
                f"{stream.get('bits_per_raw_sample')}b"
                if stream.get('bits_per_raw_sample')
                else ('10b' if '10' in pix_fmt else '8b')
            )
            for sd in stream.get('side_data_list', []):
                if sd.get('side_data_type') == 'DOVI configuration record':
                    dv_profile = sd.get('dv_profile')
                if 'HDR10+' in sd.get('side_data_type', ''):
                    hdr10plus = True

        elif stype == 'audio':
            if a_codec == 'N/A':
                a_codec = stream.get('codec_name', 'N/A').upper()
                ch      = stream.get('channels', 0)
                a_ch    = '7.1' if ch == 8 else '5.1' if ch == 6 else '2.0'
            if lang != 'UN':
                audio_langs.append(lang)

        elif stype == 'subtitle':
            c = stream.get('codec_name', '').lower()
            label = 'PGS [BURN]' if 'pgs' in c else ('Text' if c else '')
            if label and label not in sub_codecs:
                sub_codecs.append(label)
            if lang != 'UN':
                sub_langs.append(lang)

    if not has_video:
        return {'skip': True}

    res_label = (
        '4K'    if (width or 0) >= 3800 else
        '1080p' if (width or 0) >= 1900 else
        '720p'  if (width or 0) >= 1200 else
        '480p'
    )
    hdr_label = f'DV P{dv_profile}' if dv_profile else ''
    hdr_label = (
        f'{hdr_label}+' if hdr_label and hdr10plus
        else 'HDR10+'   if hdr10plus
        else hdr_label
    )
    base      = 'HDR10' if transfer == 'smpte2084' or primaries == 'bt2020' else 'SDR'
    hdr_label = f'{hdr_label} ({base})' if hdr_label else base

    a_uniq = list(dict.fromkeys(audio_langs))
    s_uniq = list(dict.fromkeys(sub_langs))
    a_full = f'{a_codec} {a_ch}'.strip()

    return {
        'file': filepath.name, 'dir': dir_name, 'size_bytes': size_bytes,
        'error': False, 'skip': False,
        'SIZE':    format_size(size_bytes),
        'DUR':     format_duration(dur_raw),
        'RES':     res_label,
        'NQI':     NQI.calculate(bitrate, res_label, v_codec, hdr_label, a_full, nqi_audio),
        'VIDEO':   v_codec,
        'AUDIO':   a_full,
        'SUBS':    sub_codecs[0] if sub_codecs else '',
        'HDR':     hdr_label,
        'BITRATE': f'{round(bitrate / 1_000_000, 1)}M' if bitrate else 'N/A',
        'DEPTH':   depth,
        'FPS':     fps,
        'LANG':    f"A:{','.join(a_uniq[:3])} S:{','.join(s_uniq[:3])}".strip(),
    }

def style_text(text: str, col_name: str) -> str:
    if not text: return text
    s = text.strip()
    if col_name == 'NQI' and s.isdigit():
        nqi_val = int(s)
        indicators = ['⬡⬡⬡', '⬢⬡⬡', '⬢⬢⬡', '⬢⬢⬢', '✪⬡⬡']
        colors = [Color.RED, Color.ORANGE, Color.YELLOW, Color.GREEN, Color.CYAN]
        
        idx = min(4, max(0, nqi_val - 1))
        symbol = indicators[idx]
        c = colors[idx]
        
        return f'{c}{symbol}{Color.RESET}'
        
    if s == '1080p': return f'{Color.YELLOW}{text}{Color.RESET}'
    if s in ('720p', '480p'): return f'{Color.RED}{text}{Color.RESET}'
    if any(x in text for x in ('ERROR', 'CORRUPT', '[BURN]')): return f'{Color.BOLD}{Color.RED}{text}{Color.RESET}'
    if any(x in text for x in ('4K', 'HEVC', 'AV1', '10b')): return f'{Color.GREEN}{text}{Color.RESET}'
    return text

def style_folder_line(path_str: str, file_width: int, prefix: str) -> str:
    if path_str == 'CURRENT DIRECTORY':
        folder_name = './'
    else:
        path_obj = Path(path_str)
        folder_name = f'{path_obj.name}/'

    full_string = f'{prefix}{folder_name}'

    if get_display_width(full_string) <= file_width:
        styled = f'{Color.GRAY}{prefix}{Color.RESET}{Color.WHITE}{Color.BOLD}{folder_name}{Color.RESET}'
        return align_string(styled, file_width)

    truncated = truncate(full_string, file_width)
    prefix_len = len(prefix)
    if truncated.startswith(prefix):
        rest_of_string = truncated[prefix_len:]
        styled = f'{Color.GRAY}{prefix}{Color.RESET}{Color.WHITE}{Color.BOLD}{rest_of_string}{Color.RESET}'
    else:
        styled = f'{Color.WHITE}{Color.BOLD}{truncated}{Color.RESET}'
        
    return align_string(styled, file_width)

def main() -> None:
    parser = argparse.ArgumentParser(description=f'NNUVA v{VERSION} — video file analyzer')
    
    parser.add_argument('paths', nargs='*', default=[])
    parser.add_argument('-R', '--recursive', action='store_true')
    parser.add_argument('-a', '--all', action='store_true')
    parser.add_argument('-v', '--version', action='version', version=f'NNUVA v{VERSION}')
    parser.add_argument('--nqi-audio', action='store_true', help='Include lossless audio bonus in NQI calculation')
    parser.add_argument(
        '--install', action='store_true',
        help='Install/update NNUVA to ~/.local/bin/nnuva and exit',
    )
    parser.add_argument(
        '--clear-cache', action='store_true',
        help='Clear the local NNUVA database cache and exit'
    )
    parser.add_argument(
        '--uninstall', action='store_true',
        help='Remove NNUVA and its cache from your system'
    )
    args = parser.parse_args()

    if args.uninstall:
        perform_uninstallation()
        sys.exit(0)

    if args.clear_cache:
        cache_dir = Path.home() / '.nnuva'
        cleared = False
        for ext in ['ffprobe_cache.json', 'ffprobe_cache.enc']:
            cache_path = cache_dir / ext
            if cache_path.exists():
                cache_path.unlink()
                cleared = True
        
        if cleared:
            print(f'{Color.GREEN}✓ NNUVA package cache cleared.{Color.RESET}')
        else:
            print(f'{Color.GRAY}Cache is already empty.{Color.RESET}')
        sys.exit(0)

    if args.install:
        perform_installation()
        sys.exit(0)

    smart_install_prompt()

    if not shutil.which('ffprobe'):
        print('Error: ffprobe missing')
        sys.exit(1)

    if not args.paths:
        try:
            args.paths = [f.name for f in Path('.').iterdir() if not f.name.startswith('.')]
        except Exception:
            pass

    files:   list[Path] = []

    for p_str in args.paths:
        p = Path(p_str)
        if '*' in p_str or '?' in p_str or not p.exists():
            for f in Path('.').glob(p_str):
                if is_valid_media(f):
                    files.append(f)
                elif f.is_dir() and is_valid_dir(f):
                    try:
                        for sub_item in f.iterdir():
                            if is_valid_media(sub_item):
                                files.append(sub_item)
                    except PermissionError:
                        pass
            continue
            
        if p.is_file():
            if is_valid_media(p):
                files.append(p)
            
        elif p.is_dir():
            if not is_valid_dir(p):
                continue
                
            if args.recursive:
                for root, dirs, files_in_root in os.walk(p):
                    dirs[:] = [d for d in dirs if is_valid_dir(Path(d))]
                    for fname in files_in_root:
                        fpath = Path(root) / fname
                        if is_valid_media(fpath):
                            files.append(fpath)
            else:
                base_depth = len(p.parts)
                for root, dirs, files_in_root in os.walk(p):
                    current_depth = len(Path(root).parts)
                    depth_diff = current_depth - base_depth
                    
                    if depth_diff >= 2:
                        dirs[:] = []
                        continue
                        
                    dirs[:] = [d for d in dirs if is_valid_dir(Path(root) / d)]
                    
                    for fname in files_in_root:
                        fpath = Path(root) / fname
                        if is_valid_media(fpath):
                            files.append(fpath)

    unique_files = list(set(files))
    
    if not unique_files:
        print(f'{Color.YELLOW}Error: No supported video files found in target paths{Color.RESET}')
        sys.exit(1)

    results: list[dict] = []
    
    executor = ThreadPoolExecutor(max_workers=MAX_THREADS)
    futures = [executor.submit(analyze_file, f, args.nqi_audio) for f in unique_files]
    
    try:
        for i, fut in enumerate(as_completed(futures), 1):
            res = fut.result()
            if not res.get('skip'):
                results.append(res)
            sys.stdout.write(
                f'\r{Color.BOLD}Scanning {len(unique_files)} files... '
                f'{int(i / len(unique_files) * 100)}%{Color.RESET}'
            )
            sys.stdout.flush()
    except KeyboardInterrupt:
        sys.stdout.write('\r\033[K')
        sys.stdout.flush()
        print(f'{Color.RED}Aborted by user. Halting background tasks...{Color.RESET}')
        executor.shutdown(wait=False, cancel_futures=True)
        os._exit(1)
    finally:
        sys.stdout.write('\r\033[K')
        sys.stdout.flush()
        executor.shutdown(wait=False)
        global_cache.save()

    for r in results:
        if r['dir'] == 'CURRENT DIRECTORY':
            r['top_dir'] = 'CURRENT DIRECTORY'
            r['sub_path'] = ''
        else:
            parts = Path(r['dir']).parts
            r['top_dir'] = parts[0]
            r['sub_path'] = str(Path(*parts[1:])) if len(parts) > 1 else ''

    grouped_results = defaultdict(list)
    for r in results:
        grouped_results[r['top_dir']].append(r)

    top_dirs = sorted(list(grouped_results.keys()), key=lambda x: (0 if x == 'CURRENT DIRECTORY' else 1, x.lower()))

    top_dir_sizes = defaultdict(int)
    sub_dir_sizes = defaultdict(int)
    for r in results:
        top_dir_sizes[r['top_dir']] += r['size_bytes']
        if r['sub_path']:
            sub_key = (r['top_dir'], r['sub_path'])
            sub_dir_sizes[sub_key] += r['size_bytes']

    cols = ['SIZE', 'DUR', 'RES', 'NQI', 'VIDEO', 'AUDIO', 'SUBS', 'HDR']
    if args.all:
        cols = ['SIZE', 'DUR', 'RES', 'NQI', 'VIDEO', 'BITRATE', 'FPS', 'DEPTH', 'AUDIO', 'LANG', 'SUBS', 'HDR']

    tw = shutil.get_terminal_size().columns - 1
    cw = {
        c: max(
            get_display_width(c),
            get_display_width(EXPLANATIONS[c]),
            max((get_display_width(str(r.get(c, ''))) for r in results), default=0),
            max((get_display_width(format_size(sz)) for sz in top_dir_sizes.values()), default=0) if c == 'SIZE' else 0,
            max((get_display_width(format_size(sz)) for sz in sub_dir_sizes.values()), default=0) if c == 'SIZE' else 0
        )
        for c in cols
    }
    fw  = max(20, tw - sum(cw.values()) - (len(cols) * 3))
    sep = f'{Color.GRAY}{"-" * tw}{Color.RESET}'
    div = f' {Color.GRAY}|{Color.RESET} '

    get_align = lambda c: 'right' if c in ('SIZE', 'DUR') else 'center'

    print(
        f'{sep}\n{Color.BOLD}{align_string("FILE", fw)}{Color.RESET}'
        + ''.join(f'{div}{Color.BOLD}{align_string(c, cw[c], get_align(c))}{Color.RESET}' for c in cols)
        + f'\n{sep}'
    )

    display_items = []
    
    for td in top_dirs:
        files_in_td = grouped_results[td]
        
        display_items.append({
            'type': 'top_dir',
            'name': td,
            'size': top_dir_sizes[td]
        })
        
        loose_files = sorted([r for r in files_in_td if r['sub_path'] == ''], key=lambda x: x['file'].lower())
        sub_dirs = sorted(list(set(r['sub_path'] for r in files_in_td if r['sub_path'] != '')), key=str.lower)
        
        total_items = len(loose_files) + len(sub_dirs)
        
        for i, lf in enumerate(loose_files):
            is_absolute_last = (i == total_items - 1)
            display_items.append({
                'type': 'file',
                'name': lf['file'],
                'data': lf,
                'depth': 0,
                'is_absolute_last': is_absolute_last
            })
            
        for i, sd in enumerate(sub_dirs):
            is_absolute_last_sd = (i + len(loose_files) == total_items - 1)
            
            display_items.append({
                'type': 'sub_dir',
                'name': sd,
                'size': sub_dir_sizes[(td, sd)],
                'is_absolute_last': is_absolute_last_sd
            })
            
            sd_files = sorted([r for r in files_in_td if r['sub_path'] == sd], key=lambda x: x['file'].lower())
            
            for j, sdf in enumerate(sd_files):
                is_last_in_sub = (j == len(sd_files) - 1)
                display_items.append({
                    'type': 'file',
                    'name': sdf['file'],
                    'data': sdf,
                    'depth': 1,
                    'parent_is_absolute_last': is_absolute_last_sd,
                    'is_last_in_sub': is_last_in_sub
                })

    for idx, item in enumerate(display_items):
        if item['type'] == 'top_dir':
            if idx > 0:
                print((' ' * fw) + ''.join(f'{div}{" " * cw[c]}' for c in cols))
            
            row_str = style_folder_line(item['name'], fw, prefix='')
            for c in cols:
                if c == 'SIZE':
                    row_str += f'{div}{Color.GRAY}{Color.BOLD}{align_string(format_size(item["size"]), cw[c], "right")}{Color.RESET}'
                else:
                    row_str += f'{div}{align_string("", cw[c])}'
            print(row_str)
            
        elif item['type'] == 'sub_dir':
            is_absolute_last = item.get('is_absolute_last', False)
            prefix = '└─ ' if is_absolute_last else '├─ '
            
            row_str = style_folder_line(item['name'], fw, prefix=prefix)
            for c in cols:
                if c == 'SIZE':
                    row_str += f'{div}{Color.GRAY}{Color.BOLD}{align_string(format_size(item["size"]), cw[c], "right")}{Color.RESET}'
                else:
                    row_str += f'{div}{align_string("", cw[c])}'
            print(row_str)
            
        elif item['type'] == 'file':
            depth = item['depth']
            
            if depth == 0:
                is_absolute_last = item.get('is_absolute_last', False)
                prefix = '└─ ' if is_absolute_last else '├─ '
            else:
                parent_is_absolute_last = item.get('parent_is_absolute_last', False)
                is_last_in_sub = item.get('is_last_in_sub', False)
                
                gc_base = '   ' if parent_is_absolute_last else '│  '
                gc_branch = '└─ ' if is_last_in_sub else '├─ '
                prefix = f'{gc_base}{gc_branch}'

            styled_prefix = f'{Color.GRAY}{prefix}{Color.RESET}'
            display_name = f'{prefix}{item["name"]}'
            
            if get_display_width(display_name) <= fw:
                padded_name = item["name"]
            else:
                truncated = truncate(display_name, fw)
                padded_name = truncated[len(prefix):]
                
            row_str = align_string(f'{styled_prefix}{padded_name}', fw)
            for c in cols:
                raw_val = item['data'].get(c, "N/A")
                styled_val = style_text(str(raw_val), c)
                row_str += f'{div}{align_string(styled_val, cw[c], get_align(c))}'
            print(row_str)

    print(
        f'{sep}\n{align_string(" ", fw)}'
        + ''.join(f'{div}{Color.GRAY}{align_string(EXPLANATIONS[c], cw[c], get_align(c))}{Color.RESET}' for c in cols)
        + f'\n{sep}'
    )


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f'\n{Color.RED}Aborted.{Color.RESET}')
        os._exit(1)
