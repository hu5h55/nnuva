import json
import base64
import gzip
from pathlib import Path
from .system import Color
from . import VERSION, CHANGELOG_LINES

def safe_inject(template_str, tag, replacement_data):
    """Memory-safe string injection."""
    if not tag or tag not in template_str:
        return template_str
    parts = template_str.split(tag)
    return str(replacement_data).join(parts)

def compress_to_b64(data_object):
    """Converts a Python object to JSON, gzips it, and encodes to Base64."""
    json_str = json.dumps(data_object)
    compressed_bytes = gzip.compress(json_str.encode('utf-8'))
    return base64.b64encode(compressed_bytes).decode('utf-8')

def generate_html(sys_mgr, args, metrics):
    ui_changelog = "".join([f"<li>{line}</li>" for line in CHANGELOG_LINES])

    json_history_b64 = compress_to_b64(metrics.get("history_log", []))
    json_files_b64 = compress_to_b64(metrics.get("minified_files", []))

    tpl_dir = Path(__file__).parent / 'templates'
    
    try:
        with open(tpl_dir / 'index.html', 'r', encoding='utf-8') as f:
            html = f.read()
        with open(tpl_dir / 'style.css', 'r', encoding='utf-8') as f:
            css = f.read()
        with open(tpl_dir / 'app.js', 'r', encoding='utf-8') as f:
            js = f.read()
    except FileNotFoundError as e:
        print(f"{sys_mgr.brand} {Color.RED}Error: Template file missing: {e}{Color.RESET}")
        return

    # 1. Inject CSS/JS into the skeleton
    html = safe_inject(html, "__NNUVA_CSS__", f"<style>\n{css}\n</style>")
    html = safe_inject(html, "__NNUVA_JS__", f"<script>\n{js}\n</script>")
    
    # 2. Inject Variables (MUST USE THESE EXACT STRINGS)
    html = safe_inject(html, "__VERSION__", VERSION)
    html = safe_inject(html, "__CACHE_MTIME__", metrics.get("cache_mtime", "Unknown"))
    html = safe_inject(html, "__NNUVA_CACHE_VERSION__", str(metrics.get("nnuva_cache_version", "1")))
    html = safe_inject(html, "__CACHE_SIZE_MB__", str(metrics.get("cache_size_mb", "0")))
    html = safe_inject(html, "__HIST_ENTRIES__", str(metrics.get("hist_entries", "0")))
    html = safe_inject(html, "__HIST_SIZE_KB__", str(metrics.get("hist_size_kb", "0")))
    html = safe_inject(html, "__HIST_MTIME__", str(metrics.get("hist_mtime", "Unknown")))
    html = safe_inject(html, "__UI_CHANGELOG__", ui_changelog)
    
    # 3. Inject the Heavy Payloads
    html = safe_inject(html, "__JSON_HISTORY_B64__", json_history_b64)
    html = safe_inject(html, "__JSON_FILES_B64__", json_files_b64)

    if args.output:
        out_path = Path(args.output)
        if out_path.is_dir() or args.output.endswith('/'):
            output_file = out_path / 'index.html'
        else:
            output_file = out_path
    else:
        output_file = Path.cwd() / 'nnuva_report.html'

    json_output_file = output_file.with_name('nnuva.json')

    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        with open(json_output_file, 'w', encoding='utf-8') as f:
            json.dump(metrics.get("current_snapshot", {}), f, indent=4)
            f.write('\n')
            
        print(f"\n{Color.GREEN}✓ Success! Report generated at:{Color.RESET} {output_file}")
        print(f"{Color.GREEN}✓ Success! API Data generated at:{Color.RESET} {json_output_file}")
    except Exception as e:
        print(f"{sys_mgr.brand} {Color.RED}Error saving report: {e}{Color.RESET}")
