# src/nnuva_report/engine.py
import sys
import json
import copy
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from importlib.machinery import SourceFileLoader
import importlib.util
from .system import Color

def load_nnuva_module(sys_mgr):
    repo_root = Path(__file__).resolve().parent.parent.parent
    candidates = [
        repo_root / 'nnuva.py',
        repo_root / 'nnuva',
        sys_mgr.target_dir / 'nnuva',
        Path.cwd() / 'nnuva',
        Path.cwd() / 'nnuva.py'
    ]
    for target_path in candidates:
        if target_path.exists():
            try:
                loader = SourceFileLoader("nnuva", str(target_path))
                spec = importlib.util.spec_from_loader(loader.name, loader)
                nnuva = importlib.util.module_from_spec(spec)
                sys.modules["nnuva"] = nnuva
                loader.exec_module(nnuva)
                return nnuva
            except Exception:
                continue
    return None

def init_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS files (
        file_path TEXT PRIMARY KEY, dir_name TEXT, file_name TEXT,
        size_bytes INTEGER, size_str TEXT, mtime TEXT, res TEXT,
        nqi TEXT, video TEXT, audio TEXT, audio_base TEXT,
        hdr TEXT, dur TEXT, bitrate TEXT, fps TEXT, depth TEXT,
        lang TEXT, subs TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS history (
        date TEXT PRIMARY KEY, snapshot_json TEXT
    )''')
    conn.commit()
    return conn

def gather_metrics(sys_mgr):
    nnuva = load_nnuva_module(sys_mgr)
    if not nnuva:
        print(f"{sys_mgr.brand} {Color.RED}Error: 'nnuva' core engine missing.{Color.RESET}")
        return None

    cache_file = sys_mgr.db_dir / 'ffprobe_cache.json'
    db_path = sys_mgr.db_dir / 'nnuva.db'
    
    if not cache_file.exists():
        print(f"{sys_mgr.brand} {Color.RED}Error: Cache not found. Run a scan first.{Color.RESET}")
        return None

    # 1. Read JSON Cache
    try:
        cache_stat = cache_file.stat()
        cache_size_mb = round(cache_stat.st_size / (1024 * 1024), 2)
        cache_mtime = datetime.fromtimestamp(cache_stat.st_mtime).strftime('%Y-%m-%d %H:%M')
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
    except Exception as e:
        print(f"{sys_mgr.brand} Error reading cache: {e}")
        return None

    # 2. Sync to SQLite
    conn = init_db(db_path)
    c = conn.cursor()
    c.execute("SELECT file_path, size_bytes, mtime FROM files")
    existing_files = {row['file_path']: {'size': row['size_bytes'], 'mtime': row['mtime']} for row in c.fetchall()}
    
    current_paths = set()
    added_paths = []
    to_insert = []

    prefix = f"v{nnuva.CACHE_VERSION}_"
    cache_items = list(cache_data.items())
    total_items = len(cache_items)

    sys.stdout.write(f"{sys_mgr.brand} {Color.CYAN}Syncing cache to SQLite database...{Color.RESET}\n")

    for i, (key, raw_ffprobe) in enumerate(cache_items, 1):
        if i % 100 == 0 or i == total_items:
            pct = i / total_items
            sys.stdout.write(f'\r{sys_mgr.brand} {Color.CYAN}Processing {i}/{total_items} ... {Color.BOLD}{int(pct * 100)}%{Color.RESET} ')
            sys.stdout.flush()

        if not key.startswith(prefix):
            continue 
            
        try:
            parts = key[len(prefix):].split('_')
            mtime_str = parts.pop()
            size_bytes = int(parts.pop())
            file_path = Path('_'.join(parts))
            full_path_str = str(file_path)
            
            if not file_path.exists():
                continue
                
            current_paths.add(full_path_str)

            is_new = full_path_str not in existing_files
            is_updated = not is_new and (existing_files[full_path_str]['size'] != size_bytes or existing_files[full_path_str]['mtime'] != mtime_str)

            if is_new or is_updated:
                parsed_data = nnuva.parse_ffprobe_data(
                    data=raw_ffprobe, filepath=file_path, size_bytes=size_bytes, 
                    dir_name=str(file_path.parent), nqi_audio=False
                )
                if parsed_data.get('error') or parsed_data.get('skip'): continue

                raw_audio = parsed_data.get('AUDIO', 'Unknown')
                base_audio = raw_audio.split(' ')[0] if raw_audio != 'N/A' else 'Unknown'

                to_insert.append((
                    full_path_str, parsed_data.get('dir', 'Unknown'), parsed_data.get('file', 'Unknown'),
                    size_bytes, parsed_data.get('SIZE', '0B'), mtime_str, parsed_data.get('RES', 'Unknown'), 
                    str(parsed_data.get('NQI', 'Unknown')), parsed_data.get('VIDEO', 'Unknown'), 
                    parsed_data.get('AUDIO', 'Unknown'), base_audio, parsed_data.get('HDR', 'Unknown'), 
                    parsed_data.get('DUR', 'N/A'), parsed_data.get('BITRATE', 'N/A'), parsed_data.get('FPS', 'N/A'), 
                    parsed_data.get('DEPTH', 'N/A'), parsed_data.get('LANG', 'N/A'), parsed_data.get('SUBS', 'N/A')
                ))
                if is_new: added_paths.append(full_path_str)
        except Exception:
            continue

    sys.stdout.write('\n')

    # Commit Inserts & Deletions
    if to_insert:
        c.executemany('''REPLACE INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', to_insert)
    
    removed_paths = {p for p in (set(existing_files.keys()) - current_paths) if not Path(p).exists()}
    if removed_paths:
        c.executemany("DELETE FROM files WHERE file_path = ?", [(p,) for p in removed_paths])
    conn.commit()

    # 3. Fast SQL Queries for the Dashboard
    c.execute("SELECT COUNT(*), SUM(size_bytes) FROM files")
    total_files, total_bytes = c.fetchone()
    total_bytes = total_bytes or 0
    total_gb = int(total_bytes / (1024**3))

    c.execute("SELECT nqi, COUNT(*), SUM(size_bytes) FROM files GROUP BY nqi")
    nqi_rows = c.fetchall()
    nqi_counts = {row['nqi']: row[1] for row in nqi_rows}
    nqi_size_bytes = {row['nqi']: row[2] for row in nqi_rows}

    optimal_count = nqi_counts.get('4', 0) + nqi_counts.get('5', 0)
    transcode_count = nqi_counts.get('6', 0) + nqi_counts.get('7', 0)
    upgrade_count = nqi_counts.get('1', 0) + nqi_counts.get('2', 0)

    added_gb = sum(st.stat().st_size for p in added_paths if (st:=Path(p)).exists()) / (1024**3)
    removed_gb = sum(existing_files[p]['size'] for p in removed_paths) / (1024**3)

    delta = None
    if existing_files:
        delta = {
            "added": len(added_paths), "removed": len(removed_paths),
            "added_gb": round(added_gb, 2), "removed_gb": round(removed_gb, 2),
            "sample_added": [Path(p).name for p in sorted(added_paths)[:10]],
            "sample_removed": [Path(p).name for p in sorted(removed_paths)[:10]],
        }

    current_snapshot = {
        "date": datetime.now().strftime('%Y-%m-%d'), "total_files": total_files, "total_gb": total_gb,
        "optimal": optimal_count, "transcode": transcode_count, "upgrade": upgrade_count,
        "nqi": {"counts": nqi_counts, "sizes_gb": {k: round(v / (1024**3), 2) for k, v in nqi_size_bytes.items()}}
    }
    if delta is not None: current_snapshot["delta"] = delta

    # Log History
    c.execute("REPLACE INTO history VALUES (?, ?)", (current_snapshot['date'], json.dumps(current_snapshot)))
    conn.commit()

    c.execute("SELECT snapshot_json FROM (SELECT date, snapshot_json FROM history ORDER BY date DESC LIMIT 90) ORDER BY date ASC")
    history_log = [json.loads(row[0]) for row in c.fetchall()]

    if len(history_log) == 1:
        fake_entry = copy.deepcopy(history_log[0])
        curr_date = datetime.strptime(fake_entry['date'], '%Y-%m-%d')
        fake_entry['date'] = (curr_date - timedelta(days=1)).strftime('%Y-%m-%d')
        history_log.insert(0, fake_entry)
        
    db_stat = db_path.stat()
    db_size_kb = round(db_stat.st_size / 1024, 2)
    db_mtime = datetime.fromtimestamp(db_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')

    c.execute("""
        SELECT dir_name as dir, file_name as file, res as RES, nqi as NQI, 
               video as VIDEO, audio as AUDIO, audio_base as AUDIO_BASE, 
               hdr as HDR, size_bytes, size_str as SIZE, dur as DUR, 
               bitrate as BITRATE, fps as FPS, depth as DEPTH, 
               lang as LANG, subs as SUBS FROM files
    """)
    minified_files = [dict(row) for row in c.fetchall()]
    conn.close()

    return {
        "nnuva_cache_version": nnuva.CACHE_VERSION, "cache_size_mb": cache_size_mb, "cache_mtime": cache_mtime,
        "hist_entries": len(history_log), "hist_size_kb": db_size_kb, "hist_mtime": db_mtime,
        "history_log": history_log, "minified_files": minified_files, "current_snapshot": current_snapshot
    }
