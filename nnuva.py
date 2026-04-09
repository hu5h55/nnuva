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
from collections import defaultdict
from typing import Optional

# ==============================================================================
# CONFIGURATION
# ==============================================================================
VERSION = "1.23.0"

# Changelog:
#   1.23.0 - Fix rogue space causing misalignment in sub-folder tree branches
#   1.22.0 - Simplify tree rendering to use clean indents without vertical lines
#   1.21.0 - Remove top-level line prefix; align all items to left edge
#   1.20.4 - Style folder names as bold white, prefix as gray; fix left border breaks
#   1.20.3 - Simplify and fix tree view prefixes so directory blocks close correctly
#   1.20.2 - Fix tree view prefix rendering; ensure continuous connecting lines
#   1.20.1 - Fix gray folder bug on truncated names; properly indent tree view
#   1.20.0 - Implement nested tree-view for subfolders to prevent broken layout blocks
#   1.19.1 - Fix default arguments: make `nnuva` manually expand like `nnuva *`
#   1.19.0 - Normalize default path behavior; ignore "Sample" folders and files
#   1.17.0 - Handle PermissionError on iterdir; use os.walk for robust recursive scans
#   1.16.0 - Change default scan depth to 1; remove "Unscanned Subdirectories" UI
#   1.15.1 - Fix duplicate skipped directory listing; limit install changelog to 5 lines
#   1.15.0 - Overhaul NQI visuals to 3-char "Tech Nodes" with starburst tier 5
#   1.14.0 - Experimental branch: 2-character geometric indicators (superseded)
SUPPORTED_EXTS = {'.mkv', '.mp4', '.avi', '.ts', '.mov', '.webm', '.flv', '.m4v'}
MAX_THREADS = min(16, (os.cpu_count() or 4) * 2)

class Color:
    RESET   = '\033[0m'
    BOLD    = '\033[1m'
    BLACK   = '\033[30m'
    RED     = '\033[91m'
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
# QUALITY SCORING & SIZE FORMATTING
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

def calculate_quality_score(
    bitrate: Optional[float],
    res_label: str,
    v_codec: str,
    hdr_label: str,
    a_codec: str,
    score_audio: bool = False
) -> str:
    if not bitrate or res_label == 'N/A':
        return 'N/A'

    if any(x in v_codec for x in ['HEVC', 'H265']):
        eff = 0.5
    elif 'AV1' in v_codec:
        eff = 0.4
    else:
        eff = 1.0

    if '4K' in res_label:
        target_kbps = 25000
    elif '1080p' in res_label:
        target_kbps = 7000
    else:
        target_kbps = 3000
    target_kbps *= eff

    actual_kbps = float(bitrate) / 1000
    ratio = actual_kbps / target_kbps
    
    base_max = 3.5 if score_audio else 4.0
    score = min(base_max, ratio * base_max)

    if '4K' in res_label:
        score += 0.5
    if any(x in hdr_label for x in ['HDR', 'DV', '10b']):
        score += 0.5
    if score_audio and any(x in a_codec for x in ['TRUEHD', 'DTS-HD', 'FLAC']):
        score += 0.5

    return str(int(round(min(5.0, max(1.0, score)))))

# ==============================================================================
# SYSTEM MANAGEMENT
# ==============================================================================

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

def perform_installation() -> bool:
    current_script = os.path.abspath(__file__)
    target_path = os.path.expanduser('~/.local/bin/nnuva')
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    shutil.copy(current_script, target_path)
    os.chmod(target_path, 0o755)
    print(f'{Color.GREEN}✓ NNUVA updated to {target_path}{Color.RESET}')
    return True

def smart_install_prompt() -> None:
    if not sys.stdout.isatty(): return
    target_path = os.path.expanduser('~/.local/bin/nnuva')
    if os.path.abspath(__file__) == target_path: return
    inst_ver = get_installed_version(target_path)
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
            perform_installation()
            sys.exit(0)
    except KeyboardInterrupt:
        print('\nAborted.')
        sys.exit(1)

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

    size_bytes = os.path.getsize(filepath)
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

    error_result = {
        'file': filepath.name, 'dir': dir_name,
        'size_bytes': size_bytes, 'error': True,
        'SIZE': format_size(size_bytes), 'NQI': 'ERR',
    }

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        data = json.loads(proc.stdout)
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
    elif dur_raw:
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
        'NQI':     calculate_quality_score(bitrate, res_label, v_codec, hdr_label, a_full, nqi_audio),
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
        indicators = ['⬡⬡⬡', '⬢⬡⬡', '⬢⬢⬡', '⬢⬢⬢', '✸✸✸']
        colors = [Color.RED, Color.MAGENTA, Color.YELLOW, Color.GREEN, Color.BLUE]
        
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
    args = parser.parse_args()

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
                try:
                    for item in p.iterdir():
                        if is_valid_media(item):
                            files.append(item)
                        elif item.is_dir() and is_valid_dir(item):
                            try:
                                for sub_item in item.iterdir():
                                    if is_valid_media(sub_item):
                                        files.append(sub_item)
                            except PermissionError:
                                pass
                except PermissionError:
                    pass

    unique_files = list(set(files))
    
    if not unique_files:
        print(f'{Color.YELLOW}Error: No supported video files found in target paths{Color.RESET}')
        sys.exit(1)

    results: list[dict] = []
    try:
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as ex:
            futures = [ex.submit(analyze_file, f, args.nqi_audio) for f in unique_files]
            for i, fut in enumerate(as_completed(futures), 1):
                res = fut.result()
                if not res.get('skip'):
                    results.append(res)
                sys.stdout.write(
                    f'\r{Color.BOLD}Scanning {len(unique_files)} files... '
                    f'{int(i / len(unique_files) * 100)}%{Color.RESET}'
                )
                sys.stdout.flush()
    finally:
        sys.stdout.write('\r\033[K')
        sys.stdout.flush()

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

    for td_idx, td in enumerate(top_dirs):
        if td_idx > 0:
            print((' ' * fw) + ''.join(f'{div}{" " * cw[c]}' for c in cols))
            
        td_prefix = ' ' 
        row_str = style_folder_line(td, fw, prefix=td_prefix)
        for c in cols:
            if c == 'SIZE':
                row_str += f'{div}{Color.GRAY}{Color.BOLD}{align_string(format_size(top_dir_sizes[td]), cw[c], "right")}{Color.RESET}'
            else:
                row_str += f'{div}{align_string("", cw[c])}'
        print(row_str)
        
        files_in_td = grouped_results[td]
        
        loose_files = [r for r in files_in_td if r['sub_path'] == '']
        sub_dirs = sorted(list(set(r['sub_path'] for r in files_in_td if r['sub_path'] != '')), key=str.lower)
        
        direct_children = []
        for lf in loose_files:
            direct_children.append({'type': 'file', 'name': lf['file'], 'data': lf})
        for sd in sub_dirs:
            direct_children.append({'type': 'dir', 'name': sd})
            
        direct_children.sort(key=lambda x: x['name'].lower())
        
        for c_idx, child in enumerate(direct_children):
            is_last_child = (c_idx == len(direct_children) - 1)
            child_prefix = ' └─ ' if is_last_child else ' ├─ '
            
            if child['type'] == 'file':
                r = child['data']
                styled_prefix = f'{Color.GRAY}{child_prefix}{Color.RESET}'
                display_name = f'{child_prefix}{r["file"]}'
                
                if get_display_width(display_name) <= fw:
                    padded_name = r["file"]
                else:
                    truncated = truncate(display_name, fw)
                    padded_name = truncated[len(child_prefix):]
                    
                row_str = align_string(f'{styled_prefix}{padded_name}', fw)
                for c in cols:
                    raw_val = r.get(c, "N/A")
                    styled_val = style_text(str(raw_val), c)
                    row_str += f'{div}{align_string(styled_val, cw[c], get_align(c))}'
                print(row_str)
                
            elif child['type'] == 'dir':
                sd_name = child['name']
                sd_row_str = style_folder_line(sd_name, fw, prefix=child_prefix)
                for c in cols:
                    if c == 'SIZE':
                        sd_size = sub_dir_sizes[(td, sd_name)]
                        sd_row_str += f'{div}{Color.GRAY}{Color.BOLD}{align_string(format_size(sd_size), cw[c], "right")}{Color.RESET}'
                    else:
                        sd_row_str += f'{div}{align_string("", cw[c])}'
                print(sd_row_str)
                
                sd_files = [r for r in files_in_td if r['sub_path'] == sd_name]
                sd_files.sort(key=lambda x: x['file'].lower())
                
                for f_idx, r in enumerate(sd_files):
                    is_last_sub_file = (f_idx == len(sd_files) - 1)
                    
                    gc_base = '    ' if is_last_child else ' │  '
                    gc_branch = '└─ ' if is_last_sub_file else '├─ '
                    
                    # Removed the rogue space: f'{gc_base}{gc_branch}' instead of f' {gc_base}{gc_branch}'
                    gc_prefix = f'{gc_base}{gc_branch}'
                    
                    styled_prefix = f'{Color.GRAY}{gc_prefix}{Color.RESET}'
                    display_name = f'{gc_prefix}{r["file"]}'
                    
                    if get_display_width(display_name) <= fw:
                        padded_name = r["file"]
                    else:
                        truncated = truncate(display_name, fw)
                        padded_name = truncated[len(gc_prefix):]
                        
                    f_row_str = align_string(f'{styled_prefix}{padded_name}', fw)
                    for c in cols:
                        raw_val = r.get(c, "N/A")
                        styled_val = style_text(str(raw_val), c)
                        f_row_str += f'{div}{align_string(styled_val, cw[c], get_align(c))}'
                    print(f_row_str)

    print(
        f'{sep}\n{align_string(" ", fw)}'
        + ''.join(f'{div}{Color.GRAY}{align_string(EXPLANATIONS[c], cw[c], get_align(c))}{Color.RESET}' for c in cols)
        + f'\n{sep}'
    )


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nAborted.')
        sys.exit(1)
