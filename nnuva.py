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
VERSION = "1.9.0"

# Changelog:
#   1.9.0 - Add -v / --version flag; truncate long folder names to fit columns
#   1.8.0 - Perf & correctness pass: module-level regex, O(n) dir_sizes,
#            typed signatures, fix bare except, ordered sub_codecs, explicit
#            bitrate fallback, progress bar try/finally, --install flag
#   1.7.0 - Initial public release
SUPPORTED_EXTS = {'.mkv', '.mp4', '.avi', '.ts', '.mov', '.webm', '.flv', '.m4v'}
# ffprobe is I/O-bound (subprocess + disk reads), not CPU-bound, so a thread
# count above cpu_count*2 is fine; cap at 16 to avoid saturating the disk.
MAX_THREADS = min(16, (os.cpu_count() or 4) * 2)

class Color:
    RESET  = '\033[0m'
    BOLD   = '\033[1m'
    RED    = '\033[91m'
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    CYAN   = '\033[96m'
    GRAY   = '\033[90m'
    WHITE  = '\033[97m'

EXPLANATIONS = {
    'SIZE': 'Size', 'DUR': 'Runtime', 'RES': 'Res', 'NQI': 'NQI',
    'VIDEO': 'Video', 'BITRATE': 'Bitrate', 'FPS': 'FPS', 'DEPTH': 'Depth',
    'AUDIO': 'Audio', 'LANG': 'Lang', 'SUBS': 'Subs', 'HDR': 'HDR'
}

# Compiled once at module level — reused on every get_display_width call.
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

def pad_string(text: str, target_width: int) -> str:
    return str(text) + (' ' * max(0, target_width - get_display_width(text)))

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
) -> str:
    if not bitrate or res_label == 'N/A':
        return 'N/A'

    # Efficiency factor: modern codecs deliver equivalent quality at lower bitrates.
    if any(x in v_codec for x in ['HEVC', 'H265']):
        eff = 0.5   # ~50% more efficient than H.264
    elif 'AV1' in v_codec:
        eff = 0.4   # ~60% more efficient than H.264
    else:
        eff = 1.0   # H.264 / baseline reference

    # Reference "good quality" kbps targets for H.264; scaled down by eff for modern codecs.
    if '4K' in res_label:
        target_kbps = 25000
    elif '1080p' in res_label:
        target_kbps = 7000
    else:
        target_kbps = 3000
    target_kbps *= eff

    actual_kbps = float(bitrate) / 1000
    ratio = actual_kbps / target_kbps
    score = min(3.5, ratio * 3.5)   # bitrate contribution caps at 3.5

    # Bonus points for premium attributes (total possible: 5.0)
    if '4K' in res_label:
        score += 0.5
    if any(x in hdr_label for x in ['HDR', 'DV', '10b']):
        score += 0.5
    if any(x in a_codec for x in ['TRUEHD', 'DTS-HD', 'FLAC']):
        score += 0.5   # lossless audio

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
    """Copy this script to ~/.local/bin/nnuva. Returns True on success."""
    current_script = os.path.abspath(__file__)
    target_path = os.path.expanduser('~/.local/bin/nnuva')
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    shutil.copy(current_script, target_path)
    os.chmod(target_path, 0o755)
    print(f'{Color.GREEN}✓ NNUVA updated to {target_path}{Color.RESET}')
    return True

def smart_install_prompt() -> None:
    """Offer an interactive update when running as a standalone script."""
    if not sys.stdout.isatty(): return
    target_path = os.path.expanduser('~/.local/bin/nnuva')
    if os.path.abspath(__file__) == target_path: return
    inst_ver = get_installed_version(target_path)
    if inst_ver == VERSION: return
    print(f'{Color.CYAN}NNUVA v{VERSION} (Current standalone){Color.RESET}')
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

def analyze_file(filepath: Path) -> dict:
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

    # Explicit precedence: prefer container-reported bitrate, fall back to
    # size/duration estimate, then give up.
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
    # List (not set) so insertion order is preserved and output is deterministic.
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
        'NQI':     calculate_quality_score(bitrate, res_label, v_codec, hdr_label, a_full),
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
        c = Color.GREEN if int(s) >= 4 else Color.YELLOW if int(s) >= 3 else Color.RED
        return f'{c}■{Color.RESET}' + (' ' * (len(text) - 1))
    if s == '1080p': return f'{Color.YELLOW}{text}{Color.RESET}'
    if s in ('720p', '480p'): return f'{Color.RED}{text}{Color.RESET}'
    if any(x in text for x in ('ERROR', 'CORRUPT', '[BURN]')): return f'{Color.BOLD}{Color.RED}{text}{Color.RESET}'
    if any(x in text for x in ('4K', 'HEVC', 'AV1', '10b')): return f'{Color.GREEN}{text}{Color.RESET}'
    return text

def style_folder_line(path_str: str, file_width: int, prefix: str = ' ┌─ ') -> str:
    # Guard: "CURRENT DIRECTORY" is a sentinel, not a real filesystem path.
    if path_str == 'CURRENT DIRECTORY':
        full      = f'{prefix}./'
        truncated = truncate(full, file_width)
        styled    = f'{Color.GRAY}{Color.BOLD}{prefix}{Color.RESET}{Color.WHITE}{Color.BOLD}./{Color.RESET}'
        if get_display_width(full) > file_width:
            styled = f'{Color.GRAY}{Color.BOLD}{truncated}{Color.RESET}'
        return pad_string(styled, file_width)

    path_obj    = Path(path_str)
    folder_name = f'{path_obj.name}/'
    parent_path = str(path_obj.parent)
    parent_path = '' if parent_path == '.' else parent_path + '/'
    full        = f'{prefix}{parent_path}{folder_name}'

    # No truncation needed — use the original two-tone styling.
    if get_display_width(full) <= file_width:
        styled = f'{Color.GRAY}{Color.BOLD}{prefix}{parent_path}{Color.RESET}{Color.WHITE}{Color.BOLD}{folder_name}{Color.RESET}'
        return pad_string(styled, file_width)

    # Truncate first (plain text), then re-apply styling.
    # truncate() preserves both ends, so folder_name at the tail is kept when
    # it fits in the keep-right half — restore two-tone if we can detect the split.
    truncated = truncate(full, file_width)
    if truncated.endswith(folder_name):
        pre    = truncated[: -len(folder_name)]
        styled = f'{Color.GRAY}{Color.BOLD}{pre}{Color.RESET}{Color.WHITE}{Color.BOLD}{folder_name}{Color.RESET}'
    else:
        # folder_name itself was truncated — uniform style is the only safe option.
        styled = f'{Color.GRAY}{Color.BOLD}{truncated}{Color.RESET}'
    return pad_string(styled, file_width)

def main() -> None:
    parser = argparse.ArgumentParser(description=f'NNUVA v{VERSION} — video file analyzer')
    parser.add_argument('paths', nargs='*', default=['.'])
    parser.add_argument('-R', '--recursive', action='store_true')
    parser.add_argument('-a', '--all', action='store_true')
    parser.add_argument('-v', '--version', action='version', version=f'NNUVA v{VERSION}')
    parser.add_argument(
        '--install', action='store_true',
        help='Install/update NNUVA to ~/.local/bin/nnuva and exit',
    )
    args = parser.parse_args()

    # Explicit install flag — no side-effectful auto-prompt needed here.
    if args.install:
        perform_installation()
        sys.exit(0)

    # Interactive prompt only when running as a one-off standalone script.
    smart_install_prompt()

    if not shutil.which('ffprobe'):
        print('Error: ffprobe missing')
        sys.exit(1)

    files:   list[Path] = []
    skipped: list[str]  = []

    for p_str in args.paths:
        p = Path(p_str)
        if not p.exists():
            for f in Path('.').glob(p_str):
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS:
                    files.append(f)
            continue
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            files.append(p)
        elif p.is_dir():
            search = p.rglob('*') if args.recursive else p.glob('*')
            for f in search:
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS:
                    files.append(f)
                elif f.is_dir() and not args.recursive:
                    skipped.append(f.name)

    if not files and not skipped:
        print('Error: Nothing found')
        sys.exit(1)

    results: list[dict] = []
    if files:
        try:
            with ThreadPoolExecutor(max_workers=MAX_THREADS) as ex:
                futures = [ex.submit(analyze_file, f) for f in files]
                for i, fut in enumerate(as_completed(futures), 1):
                    res = fut.result()
                    if not res.get('skip'):
                        results.append(res)
                    sys.stdout.write(
                        f'\r{Color.BOLD}Scanning {len(files)} files... '
                        f'{int(i / len(files) * 100)}%{Color.RESET}'
                    )
                    sys.stdout.flush()
        finally:
            # Always clear the progress line, even when interrupted mid-scan.
            sys.stdout.write('\r\033[K')
            sys.stdout.flush()

    # Alphabetical sort: force CURRENT DIRECTORY to top, then dir, then filename.
    results.sort(key=lambda x: (
        0 if x['dir'] == 'CURRENT DIRECTORY' else 1,
        x['dir'].lower(),
        x['file'].lower(),
    ))
    skipped.sort(key=str.lower)

    # Single-pass O(n) aggregation instead of the original O(n²) comprehension.
    dir_sizes: defaultdict[str, int] = defaultdict(int)
    for r in results:
        dir_sizes[r['dir']] += r['size_bytes']

    cols = ['SIZE', 'DUR', 'RES', 'NQI', 'VIDEO', 'AUDIO', 'SUBS', 'HDR']
    if args.all:
        cols = ['SIZE', 'DUR', 'RES', 'NQI', 'VIDEO', 'BITRATE', 'FPS', 'DEPTH', 'AUDIO', 'LANG', 'SUBS', 'HDR']

    tw = shutil.get_terminal_size().columns - 1
    cw = {
        c: max(
            get_display_width(c),
            get_display_width(EXPLANATIONS[c]),
            max((get_display_width(r.get(c, '')) for r in results), default=0),
        )
        for c in cols
    }
    fw  = max(20, tw - sum(cw.values()) - (len(cols) * 3))
    sep = f'{Color.GRAY}{"-" * tw}{Color.RESET}'
    div = f' {Color.GRAY}|{Color.RESET} '

    print(
        f'{sep}\n{Color.BOLD}{pad_string("FILE", fw)}{Color.RESET}'
        + ''.join(f'{div}{Color.BOLD}{pad_string(c, cw[c])}{Color.RESET}' for c in cols)
        + f'\n{sep}'
    )

    grouped_dirs = list(dict.fromkeys(r['dir'] for r in results))
    for i, d in enumerate(grouped_dirs):
        if i > 0:
            print((' ' * fw) + ''.join(f'{div}{" " * cw[c]}' for c in cols))
        row_str = style_folder_line(d, fw)
        for c in cols:
            if c == 'SIZE':
                row_str += f'{div}{Color.GRAY}{Color.BOLD}{pad_string(format_size(dir_sizes[d]), cw[c])}{Color.RESET}'
            else:
                row_str += f'{div}{pad_string("", cw[c])}'
        print(row_str)

        files_in_dir = [r for r in results if r['dir'] == d]
        for j, r in enumerate(files_in_dir):
            prefix  = ' └─ ' if j == len(files_in_dir) - 1 else ' ├─ '
            row_str = pad_string(truncate(f'{prefix}{r["file"]}', fw), fw)
            for c in cols:
                row_str += f'{div}{style_text(pad_string(r.get(c, "N/A"), cw[c]), c)}'
            print(row_str)

    if skipped and not args.recursive:
        if results:
            print((' ' * fw) + ''.join(f'{div}{" " * cw[c]}' for c in cols))
        print(
            f'{Color.GRAY}{Color.BOLD}{pad_string(" ┌─ Unscanned Subdirectories/", fw)}{Color.RESET}'
            + ''.join(f'{div}{" " * cw[c]}' for c in cols)
        )
        for k, s in enumerate(skipped):
            prefix = ' └─ ' if k == len(skipped) - 1 else ' ├─ '
            print(
                f'{Color.GRAY}{Color.BOLD}{pad_string(prefix + s + "/", fw)}{Color.RESET}'
                + ''.join(f'{div}{" " * cw[c]}' for c in cols)
            )

    print(
        f'{sep}\n{pad_string(" ", fw)}'
        + ''.join(f'{div}{Color.GRAY}{pad_string(EXPLANATIONS[c], cw[c])}{Color.RESET}' for c in cols)
        + f'\n{sep}'
    )


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nAborted.')
        sys.exit(1)
