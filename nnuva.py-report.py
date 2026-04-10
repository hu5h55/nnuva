#!/usr/bin/env python3

# NNUVA Static Report Generator
# Parses the local NNUVA cache using nnuva's internal engine to generate a zero-server HTML dashboard.

import sys
import json
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
from collections import Counter, defaultdict

VERSION = "2.9.5"

# --- Dynamic Import of NNUVA ---
def load_nnuva_module():
    home_dir = Path.home()
    target_path = home_dir / '.local' / 'bin' / 'nnuva'
    
    if not target_path.exists():
        target_path = home_dir / 'bin' / 'nnuva'
        
    if not target_path.exists():
        target_path = Path.cwd() / 'nnuva'
        
    if not target_path.exists():
        return None

    loader = SourceFileLoader("nnuva", str(target_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    nnuva = importlib.util.module_from_spec(spec)
    sys.modules["nnuva"] = nnuva
    loader.exec_module(nnuva)
    
    return nnuva

def get_top_categories(counter_obj, max_categories=5):
    """
    Groups a Counter object into a maximum number of categories.
    If there are more items than max_categories, it takes the top (max-1) 
    and groups the rest into an 'Others' category.
    """
    if len(counter_obj) <= max_categories:
        labels = list(counter_obj.keys())
        data = list(counter_obj.values())
        return labels, data
    
    most_common = counter_obj.most_common(max_categories - 1)
    labels = [k for k, v in most_common]
    data = [v for k, v in most_common]
    
    others_sum = sum(v for k, v in counter_obj.most_common()[max_categories - 1:])
    labels.append("Others")
    data.append(others_sum)
    
    return labels, data

def generate_report():
    print(f"NNUVA Report Generator v{VERSION}")
    
    nnuva = load_nnuva_module()
    if not nnuva:
        print("Error: Could not locate the 'nnuva' executable to load parsing engine.")
        print("Please ensure NNUVA is installed globally or exists in the current directory.")
        return

    cache_file = Path.home() / '.nnuva' / 'ffprobe_cache.json'
    
    if not cache_file.exists():
        print("Error: NNUVA cache not found. Run a scan with nnuva first.")
        return

    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
    except Exception as e:
        print(f"Error reading cache: {e}")
        return

    if not cache_data:
        print("Cache is empty. Nothing to report.")
        return

    print("Parsing raw ffprobe data...")
    
    total_files = 0
    total_bytes = 0
    
    res_counts = Counter()
    res_size_bytes = defaultdict(int)
    video_counts = Counter()
    hdr_counts = Counter()
    audio_counts = Counter()
    nqi_counts = Counter()
    
    all_files = []

    prefix = f"v{nnuva.CACHE_VERSION}_"
    
    for key, raw_ffprobe in cache_data.items():
        if not key.startswith(prefix):
            continue 
            
        try:
            parts = key[len(prefix):].split('_')
            mtime = parts.pop()
            size_bytes = int(parts.pop())
            file_path = Path('_'.join(parts))
        except Exception:
            continue

        parsed_data = nnuva.parse_ffprobe_data(
            data=raw_ffprobe, 
            filepath=file_path, 
            size_bytes=size_bytes, 
            dir_name=str(file_path.parent), 
            nqi_audio=False
        )
        
        if parsed_data.get('error') or parsed_data.get('skip'):
            continue
            
        total_files += 1
        total_bytes += size_bytes
        
        res = parsed_data.get('RES', 'Unknown')
        res_counts[res] += 1
        res_size_bytes[res] += size_bytes
        
        video_counts[parsed_data.get('VIDEO', 'Unknown')] += 1
        hdr_counts[parsed_data.get('HDR', 'Unknown')] += 1
        
        raw_audio = parsed_data.get('AUDIO', 'Unknown')
        base_audio = raw_audio.split(' ')[0] if raw_audio != 'N/A' else 'Unknown'
        audio_counts[base_audio] += 1
        
        nqi_counts[str(parsed_data.get('NQI', 'Unknown'))] += 1
        
        all_files.append(parsed_data)

    all_files_sorted = sorted(all_files, key=lambda x: x.get('size_bytes', 0), reverse=True)
    
    top_files = all_files_sorted[:10]
    transcode_candidates = [f for f in all_files_sorted if f.get('NQI') in ('6', '7')][:10]
    upgrade_candidates = [f for f in all_files_sorted if f.get('NQI') in ('1', '2')][:10]
    
    optimal_count = nqi_counts.get('4', 0) + nqi_counts.get('5', 0)
    transcode_count = nqi_counts.get('6', 0) + nqi_counts.get('7', 0)
    upgrade_count = nqi_counts.get('1', 0) + nqi_counts.get('2', 0)
    
    total_gb = int(total_bytes / (1024**3))

    res_order = ['4K', '1080p', '720p', '480p']
    res_labels = [r for r in res_order if r in res_counts] + [r for r in res_counts if r not in res_order]
    res_data = [res_counts[r] for r in res_labels]
    res_size_data = [round(res_size_bytes.get(r, 0) / (1024**3), 1) for r in res_labels]
    
    nqi_order = ['7', '6', '5', '4', '3', '2', '1']
    nqi_labels = [n for n in nqi_order if n in nqi_counts] + [n for n in nqi_counts if n not in nqi_order]
    nqi_data = [nqi_counts[n] for n in nqi_labels]

    video_labels, video_data = get_top_categories(video_counts, max_categories=5)
    audio_labels, audio_data = get_top_categories(audio_counts, max_categories=5)
    hdr_labels, hdr_data = get_top_categories(hdr_counts, max_categories=5)

    # --- HTML & JS Template ---
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NNUVA Library Dashboard v{VERSION}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            background-color: #0f172a;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 40px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .header-section {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            border-bottom: 1px solid #334155;
            padding-bottom: 10px;
            margin-bottom: 30px;
        }}
        h1 {{
            color: #38bdf8;
            margin: 0;
            font-size: 2.5rem;
        }}
        .version-badge {{
            color: #94a3b8;
            font-size: 1rem;
            font-weight: bold;
        }}
        h2 {{
            color: #e2e8f0;
            margin-top: 50px;
            font-weight: 500;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 20px;
            margin-bottom: 40px;
        }}
        @media (max-width: 1024px) {{
            .kpi-grid {{ grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }}
        }}
        .kpi-card {{
            background-color: #1e293b;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            border-top: 4px solid #334155;
        }}
        .kpi-card.blue {{ border-top-color: #38bdf8; }}
        .kpi-card.green {{ border-top-color: #34d399; }}
        .kpi-card.magenta {{ border-top-color: #d946ef; }}
        .kpi-card.orange {{ border-top-color: #f97316; }}
        
        .kpi-value {{
            font-size: 1.8rem;
            font-weight: bold;
            margin-top: 10px;
            white-space: nowrap;
        }}
        .kpi-label {{
            color: #94a3b8;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .chart-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 30px;
            margin-bottom: 50px;
        }}
        @media (max-width: 1200px) {{
            .chart-grid {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        .chart-container {{
            background-color: #1e293b;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            position: relative;
            height: 300px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background-color: #1e293b;
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 40px;
            font-size: 0.95rem;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #334155;
        }}
        th {{
            background-color: #0f172a;
            color: #38bdf8;
            font-weight: 600;
        }}
        tr:hover td {{ background-color: #334155; }}
        tr:last-child td {{ border-bottom: none; }}
        .text-right {{ text-align: right; }}
        .badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 0.85rem;
            color: #0f172a;
        }}
        .nqi-7, .nqi-6 {{ background-color: #d946ef; color: white; }}
        .nqi-5 {{ background-color: #22d3ee; }}
        .nqi-4 {{ background-color: #34d399; }}
        .nqi-3 {{ background-color: #fbbf24; }}
        .nqi-2 {{ background-color: #fb923c; }}
        .nqi-1 {{ background-color: #f87171; color: white; }}
        .nqi-NA {{ background-color: #64748b; color: white; }}
        
        .action-section {{
            background-color: #1e293b;
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 30px;
            border-left: 4px solid #38bdf8;
        }}
        .action-section h3 {{
            color: #f8fafc;
            margin-top: 0;
            margin-bottom: 15px;
        }}
        pre {{
            background-color: #0f172a;
            padding: 15px;
            border-radius: 6px;
            overflow-x: auto;
            color: #34d399;
            border: 1px solid #334155;
            margin-bottom: 0;
        }}
        code {{
            font-family: 'Courier New', Courier, monospace;
            font-size: 0.95rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header-section">
            <h1>⬢ NNUVA Library Dashboard</h1>
            <div class="version-badge">v{VERSION}</div>
        </div>
        
        <div class="kpi-grid">
            <div class="kpi-card blue">
                <div class="kpi-label">Total Files</div>
                <div class="kpi-value">{total_files:,}</div>
            </div>
            <div class="kpi-card blue">
                <div class="kpi-label">Total Storage</div>
                <div class="kpi-value">{total_gb:,} GB</div>
            </div>
            <div class="kpi-card green">
                <div class="kpi-label">Optimal Encodes (NQI 4-5)</div>
                <div class="kpi-value">{optimal_count:,}</div>
            </div>
            <div class="kpi-card magenta">
                <div class="kpi-label">Transcode Targets (NQI 6-7)</div>
                <div class="kpi-value">{transcode_count:,}</div>
            </div>
            <div class="kpi-card orange">
                <div class="kpi-label">Upgrade Targets (NQI 1-2)</div>
                <div class="kpi-value">{upgrade_count:,}</div>
            </div>
        </div>

        <div class="chart-grid">
            <div class="chart-container">
                <canvas id="resChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="nqiChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="resSizeChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="codecChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="audioChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="hdrChart"></canvas>
            </div>
        </div>

        <h2>🚨 Action Required: Top Transcode Candidates (Overkill Bitrates)</h2>
        <table>
            <thead>
                <tr><th>Filename</th><th>Resolution</th><th>Video</th><th>HDR/SDR</th><th>Audio</th><th>NQI</th><th class="text-right">Size</th></tr>
            </thead>
            <tbody>
                {''.join(f'''<tr>
                    <td>{f.get('file')}</td><td>{f.get('RES')}</td><td>{f.get('VIDEO')}</td><td>{f.get('HDR')}</td><td>{f.get('AUDIO')}</td>
                    <td><span class="badge nqi-{f.get('NQI')}">{f.get('NQI')}</span></td><td class="text-right">{f.get('SIZE')}</td>
                </tr>''' for f in transcode_candidates) if transcode_candidates else "<tr><td colspan='7'>No transcode candidates found! Your library is highly efficient.</td></tr>"}
            </tbody>
        </table>

        <h2>⚠️ Action Required: Top Upgrade Candidates (Low Quality)</h2>
        <table>
            <thead>
                <tr><th>Filename</th><th>Resolution</th><th>Video</th><th>HDR/SDR</th><th>Audio</th><th>NQI</th><th class="text-right">Size</th></tr>
            </thead>
            <tbody>
                {''.join(f'''<tr>
                    <td>{f.get('file')}</td><td>{f.get('RES')}</td><td>{f.get('VIDEO')}</td><td>{f.get('HDR')}</td><td>{f.get('AUDIO')}</td>
                    <td><span class="badge nqi-{f.get('NQI')}">{f.get('NQI')}</span></td><td class="text-right">{f.get('SIZE')}</td>
                </tr>''' for f in upgrade_candidates) if upgrade_candidates else "<tr><td colspan='7'>No low-quality candidates found!</td></tr>"}
            </tbody>
        </table>

        <h2>💾 Top 10 Largest Files Overall</h2>
        <table>
            <thead>
                <tr><th>Filename</th><th>Resolution</th><th>Video</th><th>HDR/SDR</th><th>Audio</th><th>NQI</th><th class="text-right">Size</th></tr>
            </thead>
            <tbody>
                {''.join(f'''<tr>
                    <td>{f.get('file')}</td><td>{f.get('RES')}</td><td>{f.get('VIDEO')}</td><td>{f.get('HDR')}</td><td>{f.get('AUDIO')}</td>
                    <td><span class="badge nqi-{f.get('NQI')}">{f.get('NQI')}</span></td><td class="text-right">{f.get('SIZE')}</td>
                </tr>''' for f in top_files)}
            </tbody>
        </table>

        <h2 style="color: #38bdf8; margin-top: 50px;">🛠️ Recommended Actions</h2>
        
        <div class="action-section" style="border-left-color: #d946ef;">
            <h3>1. Shrink Transcode Targets (NQI 6-7)</h3>
            <p style="color: #94a3b8; margin-top: 0; margin-bottom: 15px;">Navigate to the directories containing your massive Remuxes and run this HandBrake loop. It compresses the video via NVENC hardware acceleration and downmixes the audio to a standard 640kbps 5.1 track, appending <code>_optimal</code> to the file so you can verify the results before deleting the originals.</p>
            <pre><code>for f in *.mkv; do
    if [[ "$f" != *"_optimal"* ]]; then
        echo "Transcoding: $f"
        HandBrakeCLI -i "$f" -o "${{f%.mkv}}_optimal.mkv" \\
        --encoder nvenc_h265 --encoder-preset slower --quality 22 \\
        --all-audio --aencoder ffac3 --ab 640 --mixdown 5point1 --all-subtitles
    fi
done</code></pre>
        </div>

        <div class="action-section" style="border-left-color: #f97316;">
            <h3>2. Purge & Upgrade Low-Quality Files (NQI 1-2)</h3>
            <p style="color: #94a3b8; margin-top: 0; margin-bottom: 15px;">Rather than fixing old 480p/720p H.264 files manually, generate a flat list of your worst offenders. You can plug this list into automation tools like Sonarr/Radarr to search for better HEVC/x265 Web-DL replacements.</p>
            <pre><code>nnuva --list | grep -E "⬡⬡⬡|⬢⬡⬡"</code></pre>
        </div>

    </div>

    <script>
        Chart.defaults.color = '#94a3b8';
        Chart.defaults.maintainAspectRatio = false;
        
        const palette = ['#38bdf8', '#818cf8', '#2dd4bf', '#f472b6', '#64748b'];

        new Chart(document.getElementById('resChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(res_labels)},
                datasets: [{{
                    label: 'Files',
                    data: {json.dumps(res_data)},
                    backgroundColor: '#38bdf8',
                    borderRadius: 4
                }}]
            }},
            options: {{ plugins: {{ title: {{ display: true, text: 'Library Resolution (File Count)' }} }}, scales: {{ y: {{ beginAtZero: true }} }} }}
        }});

        const nqiColors = {json.dumps(nqi_labels)}.map(nqi => {{
            if(nqi === '7' || nqi === '6') return '#d946ef'; 
            if(nqi === '5') return '#22d3ee'; 
            if(nqi === '4') return '#34d399'; 
            if(nqi === '3') return '#fbbf24'; 
            if(nqi === '2') return '#fb923c'; 
            if(nqi === '1') return '#f87171'; 
            return '#64748b'; 
        }});

        new Chart(document.getElementById('nqiChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(nqi_labels)}.map(n => 'Score ' + n),
                datasets: [{{
                    label: 'Files',
                    data: {json.dumps(nqi_data)},
                    backgroundColor: nqiColors,
                    borderRadius: 4
                }}]
            }},
            options: {{ plugins: {{ title: {{ display: true, text: 'NQI Health Distribution' }}, legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true }} }} }}
        }});

        new Chart(document.getElementById('resSizeChart'), {{
            type: 'doughnut',
            data: {{
                labels: {json.dumps(res_labels)},
                datasets: [{{
                    data: {json.dumps(res_size_data)},
                    backgroundColor: palette,
                    borderWidth: 0
                }}]
            }},
            options: {{ plugins: {{ title: {{ display: true, text: 'Storage Footprint by Res (GB)' }} }}, cutout: '65%' }}
        }});

        new Chart(document.getElementById('codecChart'), {{
            type: 'doughnut',
            data: {{
                labels: {json.dumps(video_labels)},
                datasets: [{{
                    data: {json.dumps(video_data)},
                    backgroundColor: palette,
                    borderWidth: 0
                }}]
            }},
            options: {{ plugins: {{ title: {{ display: true, text: 'Video Codecs' }} }}, cutout: '65%' }}
        }});

        new Chart(document.getElementById('audioChart'), {{
            type: 'doughnut',
            data: {{
                labels: {json.dumps(audio_labels)},
                datasets: [{{
                    data: {json.dumps(audio_data)},
                    backgroundColor: palette,
                    borderWidth: 0
                }}]
            }},
            options: {{ plugins: {{ title: {{ display: true, text: 'Audio Codecs' }} }}, cutout: '65%' }}
        }});

        new Chart(document.getElementById('hdrChart'), {{
            type: 'pie',
            data: {{
                labels: {json.dumps(hdr_labels)},
                datasets: [{{
                    data: {json.dumps(hdr_data)},
                    backgroundColor: palette,
                    borderWidth: 0
                }}]
            }},
            options: {{ plugins: {{ title: {{ display: true, text: 'Color Volume (HDR vs SDR)' }} }} }}
        }});
    </script>
</body>
</html>
"""

    output_file = Path.cwd() / 'nnuva_report.html'
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"\n\033[92m✓ Success! Report generated at:\033[0m {output_file}")
        print("Double-click the file to open it in your browser.")
    except Exception as e:
        print(f"Error saving report: {e}")

if __name__ == '__main__':
    generate_report()
