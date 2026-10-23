// ==============================================================================
// 1. STATE & CONSTANTS
// ==============================================================================
let NNUVA_PALETTE = ['#38bdf8', '#818cf8', '#2dd4bf', '#f472b6', '#64748b']; 
let actionHistory = [];
let historyLog = [];
let rawFiles = [];
let searchQuery = '';
let activeFilters = { RES: null, NQI: null, CAT: null, SHOW: null, VIDEO: null, AUDIO_BASE: null, HDR: null, DEPTH: null, EXT: null };
let currentFilteredData = [];
let activeTrendFilters = []; 

let tableLimits = { filtered: 5, transcode: 5, upgrade: 5, series: 5, largest: 5, fs: 5 };
let tableSort = {
    filtered:  { key: 'size_bytes', dir: 'desc' },
    transcode: { key: 'size_bytes', dir: 'desc' },
    upgrade:   { key: 'size_bytes', dir: 'desc' },
    series:    { key: 'bytes',      dir: 'desc' },
    largest:   { key: 'size_bytes', dir: 'desc' },
};

let bResChart, bNqiChart, bResSizeChart, bCodecChart, bAudioChart, bHdrChart;
let bCatSizeChart, bSeriesHogChart, bCatEfficiencyChart;
let bBitrateScatterChart, bBitrateByResChart, bBitrateHistChart;
let chartHist = null;
let trendHoveredElement = null;
window.modalChartInstance = null; 
let activeFullscreenElement = null;

// ==============================================================================
// 2. CORE UTILITIES
// ==============================================================================
async function decompressGzipBase64(base64Str) {
    if (!base64Str || base64Str.startsWith("__")) return [];
    try {
        const binaryString = atob(base64Str);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) { 
            bytes[i] = binaryString.charCodeAt(i); 
        }
        const stream = new Blob([bytes]).stream();
        const decompressedStream = stream.pipeThrough(new DecompressionStream('gzip'));
        const response = await new Response(decompressedStream);
        return await response.json();
    } catch(e) {
        throw new Error(`Decompression Failure: ${e.message}`);
    }
}

function hexToRgb(hex) {
    let c;
    if(/^#([A-Fa-f0-9]{3}){1,2}$/.test(hex)){
        c= hex.substring(1).split('');
        if(c.length== 3){ c= [c[0], c[0], c[1], c[1], c[2], c[2]]; }
        c= '0x'+c.join('');
        return [(c>>16)&255, (c>>8)&255, c&255].join(',');
    }
    return '56, 189, 248';
}

function stringToColor(str) {
    if (!str) return NNUVA_PALETTE[0];
    let hash = 0;
    for (let i = 0; i < str.length; i++) { hash = str.charCodeAt(i) + ((hash << 5) - hash); }
    hash = Math.abs(hash);
    return NNUVA_PALETTE[hash % NNUVA_PALETTE.length] || NNUVA_PALETTE[0];
}

function formatGb(bytes) {
    const gb = bytes / (1024**3);
    if (gb >= 1000) return (gb / 1024).toFixed(2) + " TB";
    return Math.floor(gb).toLocaleString() + " GB";
}

function getNqiColor(scoreStr) {
    const s = String(scoreStr).replace('NQI ', '').replace('Score ', '');
    if(s === '7') return '#cbd5e1'; 
    if(s === '6') return '#d946ef'; 
    if(s === '5') return '#22d3ee'; 
    if(s === '4') return '#34d399'; 
    if(s === '3') return '#fbbf24'; 
    if(s === '2') return '#fb923c'; 
    if(s === '1') return '#f87171'; 
    return '#64748b';
}

function getNqiTextColor(scoreStr) {
    const s = String(scoreStr).replace('NQI ', '').replace('Score ', '');
    if (['1', '6'].includes(s)) return 'white';
    return '#0f172a';
}

function parseMbps(val) {
    if (!val || val === 'N/A') return null;
    let str = String(val).toUpperCase().trim();
    let num = parseFloat(str.replace(/[^\d.]/g, ''));
    if (isNaN(num)) return null;
    if (str.includes('G')) return num * 1000;
    if (str.includes('K')) return num / 1000;
    if (str.includes('M')) return num;
    if (num > 10000) return num / 1000000;
    return num;
}

function aggData(data, key, fixedOrder = null, maxCats = 5) {
    let counts = {};
    let sizes = {};
    data.forEach(d => {
        let val = d[key];
        if (key === 'NQI') val = 'NQI ' + val;
        counts[val] = (counts[val] || 0) + 1;
        sizes[val] = (sizes[val] || 0) + d.size_bytes;
    });

    let labels = [], dataCounts = [], dataSizes = [], othersValues = [];
    if (fixedOrder) {
        labels = fixedOrder.filter(l => counts[l] !== undefined);
        Object.keys(counts).forEach(k => { if (!labels.includes(k)) labels.push(k); });
        dataCounts = labels.map(l => counts[l]);
        dataSizes = labels.map(l => (sizes[l] / (1024**3)).toFixed(2));
    } else {
        let sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
        if (sorted.length <= maxCats) {
            labels = sorted.map(s => s[0]);
            dataCounts = sorted.map(s => s[1]);
        } else {
            let top = sorted.slice(0, maxCats - 1);
            labels = top.map(s => s[0]);
            dataCounts = top.map(s => s[1]);
            const othersEntries = sorted.slice(maxCats - 1);
            const othersCount = othersEntries.reduce((sum, curr) => sum + curr[1], 0);
            othersValues = othersEntries.map(s => s[0]);
            labels.push('Others');
            dataCounts.push(othersCount);
        }
    }
    return { labels, dataCounts, dataSizes, othersValues };
}

const NNUVA_CAT_LABELS = {
    'tv-shows': 'TV Shows',
    'movies': 'Movies',
    'anime': 'Anime',
    'drama': 'Drama',
    'documentaries': 'Documentaries',
    'jtv': 'J-TV',
    'sweden-tv': 'Sweden TV',
    'temp': 'Temp'
};

const NNUVA_CAT_COLORS = {
    'TV Shows': '#38bdf8',
    'Movies': '#818cf8',
    'Anime': '#f472b6',
    'Drama': '#2dd4bf',
    'Documentaries': '#34d399',
    'J-TV': '#fbbf24',
    'Sweden TV': '#a855f7',
    'Temp': '#64748b'
};

function getCatColor(cat) {
    return NNUVA_CAT_COLORS[cat] || stringToColor(cat);
}

function parseDurSec(dur) {
    if (!dur || dur === 'N/A') return 0;
    const parts = String(dur).split(':').map(x => parseInt(x, 10));
    if (parts.some(isNaN)) return 0;
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    return 0;
}

function formatRuntimeHours(sec) {
    const hrs = (sec || 0) / 3600;
    if (hrs >= 100) return Math.round(hrs).toLocaleString() + 'h';
    if (hrs >= 10) return hrs.toFixed(1) + 'h';
    if (hrs >= 1) return hrs.toFixed(1) + 'h';
    return Math.round((sec || 0) / 60) + 'm';
}

function enrichFileMetadata(f) {
    const d = String(f.dir || '');
    let rel = d.replace(/^\/(?:mnt|media|volumes|volume\d+|share)\/[^/]+\/(?:video|media|movies|tv)\//i, '');
    if (rel === d) {
        rel = d.replace(/^\/(?:mnt|media)\/[^/]+\//i, '');
    }
    const parts = rel.split('/').filter(Boolean);
    const rawCat = (parts[0] || 'other').toLowerCase();
    f.CAT = NNUVA_CAT_LABELS[rawCat] || (rawCat.charAt(0).toUpperCase() + rawCat.slice(1));

    let show = null;
    if (['tv-shows', 'drama', 'documentaries', 'sweden-tv', 'jtv'].includes(rawCat) && parts.length >= 2) {
        show = parts[1].replace(/[._]/g, ' ');
    } else if (rawCat === 'anime') {
        if (parts.length >= 3) {
            show = parts[2].replace(/[._]/g, ' ');
        } else if (parts.length === 2 && !['anime-movies', 'anime-shows'].includes(parts[1])) {
            show = parts[1].replace(/[._]/g, ' ');
        }
    }
    f.SHOW = show;

    const fn = String(f.file || '');
    const dotIdx = fn.lastIndexOf('.');
    f.EXT = dotIdx > -1 ? fn.slice(dotIdx).toLowerCase() : 'unknown';
    f.DUR_SEC = parseDurSec(f.DUR);
}

function aggregateSeriesData(files) {
    const map = new Map();
    for (const f of files) {
        if (!f.SHOW) continue;
        let st = map.get(f.SHOW);
        if (!st) {
            st = { show: f.SHOW, cat: f.CAT || 'Other', count: 0, bytes: 0, dur_sec: 0, reclaim_bytes: 0, nqi_sum: 0, nqi_cnt: 0 };
            map.set(f.SHOW, st);
        }
        st.count += 1;
        st.bytes += (f.size_bytes || 0);
        st.dur_sec += (f.DUR_SEC || 0);
        if (['6', '7'].includes(String(f.NQI))) {
            st.reclaim_bytes += Math.round((f.size_bytes || 0) * 0.5);
        }
        const nqiNum = parseInt(f.NQI, 10);
        if (!isNaN(nqiNum)) {
            st.nqi_sum += nqiNum;
            st.nqi_cnt += 1;
        }
    }
    const out = [];
    for (const st of map.values()) {
        const gb = st.bytes / (1024 ** 3);
        const hrs = st.dur_sec / 3600;
        st.gb = gb;
        st.gb_hr = hrs > 0.1 ? (gb / hrs) : 0;
        st.avg_nqi = st.nqi_cnt > 0 ? (st.nqi_sum / st.nqi_cnt) : 0;
        out.push(st);
    }
    return out;
}

// ==============================================================================
// 3. UI HANDLERS & MODALS
// ==============================================================================

function handleModalOverlayClick(event, modalId) {
    if (event.target.id === modalId) {
        if (modalId === 'filterMenuModal') closeFilterModal();
        if (modalId === 'changelogModal') closeChangelog();
        if (modalId === 'guideModal') closeGuideModal();
        if (modalId === 'historyModal') closeHistoryModal();
        if (modalId === 'sysHealthModal') closeSysHealthModal();
    }
}

window.openSysHealthModal = function() {
    const m = document.getElementById('sysHealthModal');
    if (m) m.style.display = 'flex';
    document.getElementById('meatballMenu')?.classList.remove('show');
    document.getElementById('footerKebabBtn')?.classList.remove('active');
};

window.closeSysHealthModal = function() {
    const m = document.getElementById('sysHealthModal');
    if (m) m.style.display = 'none';
};

window.jumpToSystemHealth = window.openSysHealthModal;

function assertDOM() {
    const ids = ['nqiChart', 'resChart', 'resSizeChart', 'catSizeChart', 'seriesHogChart', 'catEfficiencyChart', 'codecChart', 'audioChart', 'hdrChart', 'bitrateScatterChart'];
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (!el) throw new Error(`DOM Assertion Failed: Canvas #${id} missing`);
    });
}

window.triggerFooterGlow = function() {
    const footer = document.querySelector('.glass-footer');
    if (footer) {
        footer.classList.remove('footer-pulse');
        void footer.offsetWidth;
        footer.classList.add('footer-pulse');
    }
};

window.showToast = function(message, kind) {
    const time = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
    actionHistory.unshift(`[${time}] ${message}`);
    if(actionHistory.length > 30) actionHistory.pop();

    const sessionPanel = document.getElementById('hist-panel-session');
    if(sessionPanel) {
        sessionPanel.innerHTML = actionHistory.map(item =>
            `<div style="padding: 8px 14px; border-bottom: 1px solid var(--border); color: var(--text-main); font-size: 0.82rem; font-family: monospace;">${item}</div>`
        ).join('');
    }

    if (typeof showNotifToast === 'function') {
        showNotifToast(message, kind || 'info', 2400);
    }
};

window.switchHistTab = function(tab) {
    document.getElementById('hist-tab-changes').classList.toggle('active', tab === 'changes');
    document.getElementById('hist-tab-session').classList.toggle('active', tab === 'session');
    document.getElementById('hist-panel-changes').style.display = tab === 'changes' ? 'block' : 'none';
    document.getElementById('hist-panel-session').style.display = tab === 'session' ? 'block' : 'none';
};

function renderLibraryChanges() {
    const panel = document.getElementById('hist-panel-changes');
    if (!panel) return;
    const entries = [...historyLog].reverse();
    if (entries.length === 0) {
        panel.innerHTML = `<div style="padding: 15px; color: var(--text-muted); font-size: 0.85rem; text-align: center; font-style: italic;">No history recorded yet.</div>`;
        return;
    }
    let html = '';
    entries.forEach(e => {
        const d = e.delta;
        const files = (e.total_files || 0).toLocaleString();
        const gb = (e.total_gb || 0).toLocaleString();
        let deltaHtml = '';
        if (d) {
            const addedSign  = d.added  > 0 ? `<span style="color:#34d399; font-weight:bold;">+${d.added} files (+${d.added_gb} GB)</span>`  : '';
            const removSign  = d.removed > 0 ? `<span style="color:#f87171; font-weight:bold;">−${d.removed} files (−${d.removed_gb} GB)</span>` : '';
            const parts = [addedSign, removSign].filter(Boolean);
            deltaHtml = parts.length
                ? `<div style="margin-top:4px; font-size:0.78rem;">${parts.join(' &nbsp;·&nbsp; ')}</div>`
                : `<div style="margin-top:4px; font-size:0.78rem; color:var(--text-muted);">No change</div>`;
            if (d.sample_added && d.sample_added.length) {
                deltaHtml += `<div style="margin-top:3px; font-size:0.75rem; color:var(--text-muted); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; word-break: break-all;">+ ${d.sample_added.slice(0,3).join(', ')}</div>`;
            }
        } else {
            deltaHtml = `<div style="margin-top:4px; font-size:0.78rem; color:var(--text-muted);">First scan — baseline established</div>`;
        }
        html += `
            <div style="padding: 12px 16px; border-bottom: 1px solid var(--border);">
                <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom: 4px;">
                    <span style="font-weight:bold; color:var(--text-main); font-size:0.85rem;">${e.date}</span>
                    <span style="font-size:0.78rem; color:var(--primary); font-weight: bold;">${files} files · ${gb} GB</span>
                </div>
                ${deltaHtml}
            </div>`;
    });
    panel.innerHTML = html;
}

window.copyTextSafe = function(text, anchorBtn, toastMsg) {
    const fallbackCopy = () => {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.top = '-9999px';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        let ok = false;
        try { ok = document.execCommand('copy'); } catch (_) {}
        document.body.removeChild(ta);
        return ok;
    };
    const done = (ok) => {
        if (ok && anchorBtn && typeof _showCopyPopover === 'function') {
            _showCopyPopover(anchorBtn, toastMsg || 'Copied!');
        }
        showToast(ok ? (toastMsg || 'Copied!') : 'Copy failed');
    };
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
        navigator.clipboard.writeText(text).then(() => done(true)).catch(() => done(fallbackCopy()));
    } else {
        done(fallbackCopy());
    }
};

window.copyCommandCard = function(btn, label) {
    const cmdEl = btn && btn.closest('.workflow-card') ? btn.closest('.workflow-card').querySelector('.cmd-block') : null;
    const text = cmdEl ? cmdEl.innerText : '';
    if (!text) return;
    window.copyTextSafe(text, btn, `${label || 'Command'} copied!`);
};

function buildCommandCard(title, desc, cmd, color, btnText = 'Copy') {
    const safeBtn = String(btnText).replace(/'/g, "\\'");
    return `
        <div class="workflow-card" style="border-left: 4px solid ${color}; background: var(--bg-body); margin-bottom: 12px; border-radius: 4px; overflow: hidden; border-top: 1px solid var(--border); border-right: 1px solid var(--border); border-bottom: 1px solid var(--border);">
            <div style="padding: 12px 15px;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                    <div style="color: ${color}; font-weight: bold; font-size: 0.95rem; margin-right: 15px;">${title}</div>
                    <button type="button" onclick="copyCommandCard(this, '${safeBtn}')" style="background: ${color}; color: #0f172a; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 0.75rem; font-weight: bold; transition: opacity 0.2s; flex-shrink: 0;" onmouseover="this.style.opacity=0.8" onmouseout="this.style.opacity=1">${btnText}</button>
                </div>
                <div style="color: var(--text-muted); font-size: 0.8rem; margin-bottom: 10px; line-height: 1.4;">${desc}</div>
                <div class="cmd-block" style="background: #0f172a; color: #34d399; border: 1px solid #334155; border-radius: 4px; padding: 10px 12px; font-family: monospace; font-size: 0.8rem; word-break: break-all; white-space: normal; line-height: 1.5;">${cmd}</div>
            </div>
        </div>
    `;
}

window.copyModalField = function(kind, ev) {
    const f = window._currentModalFile;
    if (!f) return;
    const text = kind === 'path' ? (f.dir || '') : (f.file || '');
    const label = kind === 'path' ? 'Directory copied' : 'Filename copied';

    // Anchor to the actual button that was clicked
    const btn = (ev && ev.currentTarget) ? ev.currentTarget : null;

    const flashAndPop = (ok) => {
        if (!btn) return;
        if (ok) {
            btn.classList.add('copied');
            _showCopyPopover(btn, label);
            setTimeout(() => btn.classList.remove('copied'), 1100);
        }
    };

    const fallbackCopy = () => {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        let ok = false;
        try { ok = document.execCommand('copy'); } catch (_) {}
        document.body.removeChild(ta);
        return ok;
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            flashAndPop(true);
            showToast(label);
        }).catch(() => {
            const ok = fallbackCopy();
            flashAndPop(ok);
            showToast(ok ? label : 'Copy failed');
        });
    } else {
        const ok = fallbackCopy();
        flashAndPop(ok);
        showToast(ok ? label : 'Copy failed');
    }
};

// Tiny floating "Copied!" popover anchored to a trigger element.
// Self-cleans after the animation.
function _showCopyPopover(anchorEl, message) {
    if (!anchorEl) return;
    const rect = anchorEl.getBoundingClientRect();
    const pop = document.createElement('div');
    pop.className = 'copy-popover';
    pop.textContent = message;
    pop.style.position = 'fixed';
    pop.style.left = `${Math.round(rect.left + rect.width / 2)}px`;
    pop.style.top = `${Math.round(rect.top - 6)}px`;
    document.body.appendChild(pop);
    // Force animation start
    requestAnimationFrame(() => pop.classList.add('show'));
    setTimeout(() => {
        pop.classList.remove('show');
        setTimeout(() => pop.remove(), 200);
    }, 900);
}

window.openFileModal = function(fileId) {
    const f = rawFiles.find(x => String(x.id) === String(fileId));
    if(!f) return;

    window._currentModalFile = f;

    if (window.modalChartInstance) {
        window.modalChartInstance.destroy();
    }
    
    const m = document.getElementById('fileModal');
    const backdrop = document.getElementById('fileModalBackdrop');
    
    const nameEl = document.getElementById('modalFileName');
    if (nameEl) {
        nameEl.innerText = f.file;
        nameEl.setAttribute('title', f.file || '');
    }
    
    const nqiColor = getNqiColor(f.NQI);
    const nqiText = getNqiTextColor(f.NQI);
    let nqiNum = parseInt(String(f.NQI).replace(/\D/g, ''));
    if(isNaN(nqiNum)) nqiNum = 3;
    
    const nqiScale = { 1: 20, 2: 40, 3: 60, 4: 85, 5: 100, 6: 125, 7: 150 };
    const nqiPercent = nqiScale[nqiNum] || 100;
    const visualWidth = Math.min((nqiPercent / 150) * 100, 100);
    
    let actionHtml = '';
    const inPath = `${f.dir}/${f.file}`;
    const baseNoExt = String(f.file || 'output').replace(/\.[^/.]+$/, '');
    const outPath = `${f.dir}/${baseNoExt}.hevc.mkv`;
    const tmpPath = `${f.dir}/${baseNoExt}.hevc.tmp.mkv`;
    const finalMkvPath = `${f.dir}/${baseNoExt}.mkv`;
    const is4k = String(f.RES) === '4K';
    const cqVal = is4k ? 24 : 23;
    const rateCap = is4k ? '-maxrate 18M -bufsize 36M' : '-maxrate 8M -bufsize 16M';
    const vCodecUpper = String(f.VIDEO || '').toUpperCase();
    const canZeroCopyCuda = vCodecUpper.includes('HEVC') || vCodecUpper.includes('H265') || vCodecUpper.includes('H264') || vCodecUpper.includes('AVC') || vCodecUpper.includes('VC1') || vCodecUpper.includes('MPEG2') || vCodecUpper.includes('VP9');
    const hwDecFlags = canZeroCopyCuda ? '-hwaccel cuda -hwaccel_output_format cuda' : '-hwaccel auto';
    const nvencPixFmt = canZeroCopyCuda ? '' : ' -pix_fmt p010le';

    if (nqiNum >= 6) {
        const nvencCmd = `ffmpeg -hide_banner -hwaccel_device 0 ${hwDecFlags} -i "${inPath}" -map 0:v:0 -map 0:a -map 0:s? -c:v hevc_nvenc -preset p5 -rc vbr -cq ${cqVal} ${rateCap}${nvencPixFmt} -c:a eac3 -b:a 640k -c:s copy "${outPath}"`;
        const replaceTail = inPath === finalMkvPath
            ? `mv -f "${tmpPath}" "${finalMkvPath}"`
            : `mv -f "${tmpPath}" "${finalMkvPath}" && rm -f "${inPath}"`;
        const nvencReplaceCmd = `ffmpeg -hide_banner -hwaccel_device 0 ${hwDecFlags} -i "${inPath}" -map 0:v:0 -map 0:a -map 0:s? -c:v hevc_nvenc -preset p5 -rc vbr -cq ${cqVal} ${rateCap}${nvencPixFmt} -c:a eac3 -b:a 640k -c:s copy "${tmpPath}" && ${replaceTail}`;
        const cpuCmd = `ffmpeg -hide_banner -i "${inPath}" -map 0:v:0 -map 0:a -map 0:s? -c:v libx265 -preset medium -crf ${is4k ? 20 : 21} -pix_fmt yuv420p10le -c:a eac3 -b:a 640k -c:s copy "${outPath}"`;

        actionHtml += buildCommandCard('GPU Fast Transcode (NVIDIA NVENC · Side-by-Side)', `Zero-copy CUDA hardware decode + 10-bit HEVC NVENC encode (${is4k ? '4K ~50 fps' : '1080p ~160 fps'} on Quadro P400). Converts lossless audio to 640k E-AC3, preserves all subtitles, and writes beside the original file.`, nvencCmd, '#d946ef', 'Copy GPU Cmd');
        actionHtml += buildCommandCard('GPU Transcode & Replace Original (Atomic Swap)', 'Transcodes on GPU to a temporary .tmp.mkv file in the same folder and atomically replaces the original file only if FFmpeg completes with zero errors.', nvencReplaceCmd, '#38bdf8', 'Copy Swap Cmd');
        actionHtml += buildCommandCard('CPU x265 Archival Fallback (Software)', 'Software libx265 10-bit encode. Higher compression efficiency per bit, but significantly slower on CPU.', cpuCmd, '#64748b', 'Copy CPU Cmd');
    } else if (nqiNum <= 2) {
        let query = `${baseNoExt.replace(/[._]/g, ' ')} 1080p WEB-DL`;
        actionHtml += buildCommandCard('Quality Warning: Sub-Optimal Encode', 'This file is heavily artifacted or uses legacy resolution. Transcoding will not help. Search for a higher quality replacement.', query, '#f87171', 'Copy Query');
    } else {
        let hasHeavyAudio = f.AUDIO && (f.AUDIO.includes('TRUEHD') || f.AUDIO.includes('DTS-HD') || f.AUDIO.includes('FLAC') || f.AUDIO.includes('PCM'));
        let isH264 = f.VIDEO && f.VIDEO.includes('H264');
        let isLarge = (f.size_bytes / (1024**3)) > 4.0; 
        
        if (hasHeavyAudio && isLarge) {
            let cmd = `ffmpeg -hide_banner -i "${inPath}" -map 0:v:0 -map 0:a -map 0:s? -c:v copy -c:a eac3 -b:a 640k -c:s copy "${f.dir}/${baseNoExt}.eac3.mkv"`;
            actionHtml += buildCommandCard('Audio Bloat Detected (Lossless Track Remux)', '<strong style="color: #f87171;">NOTE:</strong> Video is already optimal (copied untouched at disk speed), while lossless TrueHD/DTS-HD audio is converted to 640k E-AC3 and all subtitles are preserved.', cmd, '#34d399', 'Copy Remux Cmd');
        } else if (isH264 && isLarge) {
            let nvencH264Cmd = `ffmpeg -hide_banner -hwaccel_device 0 ${hwDecFlags} -i "${inPath}" -map 0:v:0 -map 0:a -map 0:s? -c:v hevc_nvenc -preset p5 -rc vbr -cq ${cqVal} ${rateCap}${nvencPixFmt} -c:a copy -c:s copy "${outPath}"`;
            actionHtml += buildCommandCard('Legacy H.264 Codec (GPU HEVC Upgrade)', 'Converts inefficient H.264 video to 10-bit HEVC on the NVIDIA GPU while copying all audio and subtitle tracks losslessly.', nvencH264Cmd, '#22d3ee', 'Copy GPU Cmd');
        } else {
            actionHtml += `<div style="padding: 15px; text-align: center; color: var(--text-muted); font-size: 0.9rem; font-style: italic; border: 1px dashed var(--border); border-radius: 6px;">File is fully optimized. No automated workflows recommended.</div>`;
        }
    }

    let vBitrate = parseMbps(f.BITRATE) || 0;
    let aBitrate = vBitrate / 10; 

    document.getElementById('modalBody').innerHTML = `
        <div class="modal-top-grid">
        <div style="min-width: 0;">
            <div style="margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px dashed var(--border);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 35px;">
                    <span style="font-weight: bold; color: var(--text-main); font-size: 1.1rem; display: flex; align-items: center; gap: 8px;">NQI Target Ratio <button class="docs-icon-btn" onclick="openGuideModal('nqi')" title="What is NQI?" aria-label="What is NQI?" style="margin-left: 0;"><svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2.4" stroke-linecap="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="11"></line><circle cx="12" cy="8" r="0.5" fill="currentColor" stroke="none"></circle></svg></button></span>
                    <span style="background: ${nqiColor}; color: ${nqiText}; padding: 6px 16px; border-radius: 999px; font-size: 0.85rem; font-weight: bold;">NQI ${nqiNum}</span>
                </div>
                
                <div style="padding: 0 30px;">
                    <div style="position: relative; margin-bottom: 5px;">
                        <!-- Tiered background: red (sub) | yellow (acceptable) | green (optimal) | purple (bloat) -->
                        <div style="width: 100%; background:
                            linear-gradient(to right,
                                rgba(239,68,68,0.18) 0%,
                                rgba(239,68,68,0.18) 33.33%,
                                rgba(251,191,36,0.20) 33.33%,
                                rgba(251,191,36,0.20) 53.33%,
                                rgba(52,211,153,0.22) 53.33%,
                                rgba(52,211,153,0.22) 73.33%,
                                rgba(168,85,247,0.20) 73.33%,
                                rgba(168,85,247,0.20) 100%);
                            border-radius: 10px; height: 16px; position: relative; border: 1px solid var(--border); overflow: hidden;">
                            <!-- Filled bar showing this file's actual ratio -->
                            <div style="width: ${visualWidth}%; background: ${nqiColor}; height: 100%; border-radius: 10px 0 0 10px; transition: width 0.5s ease-out; box-shadow: 0 0 0 1px ${nqiColor}88 inset;"></div>
                        </div>
                        <!-- Hexagon marker at the file's exact ratio (outside the bar so it can overflow) -->
                        <div style="position: absolute; left: ${visualWidth}%; top: 50%; transform: translate(-50%, -50%); z-index: 5; pointer-events: none; line-height: 0;">
                            <svg viewBox="0 0 24 24" width="22" height="22" style="display:block; filter: drop-shadow(0 1px 3px rgba(0,0,0,0.3));">
                                <polygon points="12,2 21,7 21,17 12,22 3,17 3,7" fill="${nqiColor}" stroke="var(--bg-card)" stroke-width="2"/>
                            </svg>
                        </div>
                        <!-- Score badge floating above the hex marker -->
                        <div style="position: absolute; left: ${visualWidth}%; top: -22px; transform: translateX(-50%); background: ${nqiColor}; color: ${nqiText}; font-size: 0.65rem; font-weight: 700; padding: 2px 7px; border-radius: 4px; white-space: nowrap; z-index: 6; box-shadow: 0 1px 4px rgba(0,0,0,0.15);">${nqiPercent}%</div>
                    </div>

                    <!-- Tier labels — color each label by its zone, no fixed "Optimal" marker -->
                    <div style="display: flex; color: var(--text-muted); font-size: 0.7rem; margin-top: 8px; font-family: monospace; position: relative; height: 15px;">
                        <span style="position: absolute; left: 16.66%; transform: translateX(-50%); color: #ef4444;">Sub</span>
                        <span style="position: absolute; left: 43.33%; transform: translateX(-50%); color: #eab308;">Accept</span>
                        <span style="position: absolute; left: 63.33%; transform: translateX(-50%); color: #34d399; font-weight: bold;">Optimal</span>
                        <span style="position: absolute; left: 86.66%; transform: translateX(-50%); color: #a855f7;">Bloat</span>
                    </div>
                </div>
            </div>

            <h4 style="color: var(--text-main); margin-bottom: 12px; margin-top: 0;">Quantifiable Media Specs</h4>
            
            <div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-bottom: 20px;">
                <div style="background: var(--bg-body); border: 1px solid var(--border); padding: 10px 8px; border-radius: 6px; text-align: center;">
                    <div style="color: var(--text-muted); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px;">Resolution</div>
                    <div style="color: var(--text-main); font-weight: bold; font-size: 0.95rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${f.RES || '—'}</div>
                </div>
                <div style="background: var(--bg-body); border: 1px solid var(--border); padding: 10px 8px; border-radius: 6px; text-align: center;">
                    <div style="color: var(--text-muted); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px;">Duration</div>
                    <div style="color: var(--text-main); font-weight: bold; font-size: 0.95rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${f.DUR || '—'}</div>
                </div>
                <div style="background: var(--bg-body); border: 1px solid var(--border); padding: 10px 8px; border-radius: 6px; text-align: center;">
                    <div style="color: var(--text-muted); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px;">Size</div>
                    <div style="color: var(--text-main); font-weight: bold; font-size: 0.95rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${f.SIZE || '—'}</div>
                </div>
                <div style="background: var(--bg-body); border: 1px solid var(--border); padding: 10px 8px; border-radius: 6px; text-align: center;">
                    <div style="color: var(--text-muted); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px;">Bit Depth</div>
                    <div style="color: var(--text-main); font-weight: bold; font-size: 0.95rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${f.DEPTH || '—'}</div>
                </div>
                <div style="background: var(--bg-body); border: 1px solid var(--border); padding: 10px 8px; border-radius: 6px; text-align: center;">
                    <div style="color: var(--text-muted); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px;">Video</div>
                    <div style="color: var(--text-main); font-weight: bold; font-size: 0.95rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${f.VIDEO || '—'}</div>
                </div>
                <div style="background: var(--bg-body); border: 1px solid var(--border); padding: 10px 8px; border-radius: 6px; text-align: center;">
                    <div style="color: var(--text-muted); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px;">HDR</div>
                    <div style="color: var(--text-main); font-weight: bold; font-size: 0.95rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${f.HDR || '—'}</div>
                </div>
                <div style="background: var(--bg-body); border: 1px solid var(--border); padding: 10px 8px; border-radius: 6px; text-align: center;">
                    <div style="color: var(--text-muted); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px;">Video Bitrate</div>
                    <div style="color: var(--text-main); font-weight: bold; font-size: 0.95rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${f.BITRATE || '—'}</div>
                </div>
                <div style="background: var(--bg-body); border: 1px solid var(--border); padding: 10px 8px; border-radius: 6px; text-align: center;">
                    <div style="color: var(--text-muted); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px;">Audio Bitrate</div>
                    <div style="color: var(--text-main); font-weight: bold; font-size: 0.95rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${aBitrate.toFixed(1)}M <span style="font-size:0.65rem;font-weight:normal;color:var(--text-muted)">est.</span></div>
                </div>
            </div>

            <!-- File Identity card (left column, below Specs) -->
            <div style="background: var(--bg-body); border-radius: 6px; padding: 14px 18px; border: 1px solid var(--border);">
                <h4 style="color: var(--text-main); margin: 0 0 10px 0; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em;">File Identity</h4>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0 18px;">
                    <div class="modal-id-row modal-id-row-flat">
                        <div class="modal-id-row-content">
                            <div class="modal-id-row-label">Filename</div>
                            <div class="modal-id-row-value modal-id-row-mono" title="${(f.file || '').replace(/"/g, '&quot;')}">${f.file || '—'}</div>
                        </div>
                        <button class="modal-copy-btn" onclick="copyModalField('name', event)" title="Copy filename (for web search)" aria-label="Copy filename">
                            <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" fill="none" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                        </button>
                    </div>
                    <div class="modal-id-row modal-id-row-flat">
                        <div class="modal-id-row-content">
                            <div class="modal-id-row-label">Directory</div>
                            <div class="modal-id-row-value modal-id-row-mono" title="${(f.dir || '').replace(/"/g, '&quot;')}">${f.dir || '—'}</div>
                        </div>
                        <button class="modal-copy-btn" onclick="copyModalField('path', event)" title="Copy directory path (for cd / file manager)" aria-label="Copy directory">
                            <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" fill="none" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                        </button>
                    </div>
                </div>
            </div>

        </div>

        <div style="min-width: 0; display: flex; flex-direction: column; gap: 16px;">
            <!-- Media Footprint (fills full column height to match left) -->
            <div style="display: flex; flex-direction: column; background: var(--bg-body); border-radius: 6px; padding: 18px; border: 1px solid var(--border); flex: 1 1 auto; min-height: 0;">
                <h4 style="color: var(--text-main); margin: 0 0 4px 0; font-size: 0.95rem;">Media Footprint</h4>
                <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 14px;">Relative distribution vs. library maximums</div>
                <div style="width: 100%; flex: 1 1 auto; min-height: 220px; position: relative;">
                    <canvas id="modalRadarChart"></canvas>
                </div>
                <div style="margin-top: 14px; width: 100%; font-size: 0.78rem; color: var(--text-muted); border-top: 1px dashed var(--border); padding-top: 10px; line-height: 1.45;">
                    <strong style="color: var(--text-main);">Footprint Scale:</strong> Six dimensions of file cost &mdash; size, bitrates, resolution, duration and bit depth &mdash; each as a percent of the library's maximum. A larger hexagon means a heavier file.
                </div>
            </div>
        </div>

        </div><!-- /modal-top-grid -->

        <!-- Full-width Transcode & Downscale Actions row -->
        <div class="modal-transcode-row">
            <h4 style="color: var(--primary); margin-bottom: 12px; margin-top: 0;">
                Transcode &amp; Downscale Actions
            </h4>
            ${actionHtml}
        </div>
    `;
    
    backdrop.style.display = 'block';
    m.style.display = 'flex';
    
    void m.offsetWidth;
    
    backdrop.style.opacity = '1';
    m.classList.add('show');
    
    setTimeout(() => {
        try {
            if (typeof Chart !== 'undefined') {
                const ctx = document.getElementById('modalRadarChart');

                // Compute (or fetch cached) library-wide maximums so each axis is
                // genuinely "% of library max" — not a hard-coded guess.
                if (!window._libMaxes) {
                    const maxes = { size: 1, vBit: 1, aBit: 1, pixels: 1, dur: 1, depth: 1 };
                    const allDurs = []; // collected for percentile-based normalization
                    const parseDepth = (d) => {
                        // "8b" → 8, "10b" → 10, "N/A" → 8 (sensible default)
                        if (!d) return 8;
                        const m = String(d).match(/(\d+)/);
                        return m ? parseInt(m[1], 10) : 8;
                    };
                    const parseDur = (s) => {
                        // "HH:MM:SS" → seconds, "MM:SS" → seconds, missing → 0
                        if (!s || s === 'N/A') return 0;
                        const parts = String(s).split(':').map(p => parseInt(p, 10) || 0);
                        if (parts.length === 3) return parts[0]*3600 + parts[1]*60 + parts[2];
                        if (parts.length === 2) return parts[0]*60 + parts[1];
                        return 0;
                    };
                    const parseRes = (r) => {
                        if (!r) return 0;
                        if (/4K|2160/i.test(r)) return 3840 * 2160;
                        if (/1080/.test(r))     return 1920 * 1080;
                        if (/720/.test(r))      return 1280 * 720;
                        if (/480/.test(r))      return 854 * 480;
                        return 0;
                    };
                    for (const x of (rawFiles || [])) {
                        if (x.size_bytes > maxes.size) maxes.size = x.size_bytes;
                        const vb = parseMbps(x.BITRATE) || 0;
                        if (vb > maxes.vBit) maxes.vBit = vb;
                        const ab = vb / 10;
                        if (ab > maxes.aBit) maxes.aBit = ab;
                        const px = parseRes(x.RES);
                        if (px > maxes.pixels) maxes.pixels = px;
                        const du = parseDur(x.DUR);
                        if (du > 0) allDurs.push(du);
                        const de = parseDepth(x.DEPTH);
                        if (de > maxes.depth) maxes.depth = de;
                    }
                    // Duration uses the 75th percentile rather than the absolute max,
                    // so outlier multi-hour recordings (concerts, batched TV episodes)
                    // don't crush typical movie scores. Anything above caps at 100%.
                    if (allDurs.length > 0) {
                        allDurs.sort((a, b) => a - b);
                        maxes.dur = allDurs[Math.floor(allDurs.length * 0.75)] || 1;
                    }
                    window._libMaxes = maxes;
                    window._parseDepth = parseDepth;
                    window._parseDur = parseDur;
                    window._parseRes = parseRes;
                }
                const lm = window._libMaxes;

                // Per-file values for this modal
                const fileDur    = window._parseDur(f.DUR);
                const fileDepth  = window._parseDepth(f.DEPTH);
                const filePixels = window._parseRes(f.RES);

                // Normalized 0–100 scores against actual library maxes
                const pct = (v, m) => Math.min((v / (m || 1)) * 100, 100);
                const sizeScore  = pct(f.size_bytes, lm.size);
                const vBitScore  = pct(vBitrate,    lm.vBit);
                const resScore   = pct(filePixels,  lm.pixels);
                const durScore   = pct(fileDur,     lm.dur);
                const depthScore = pct(fileDepth,   lm.depth);
                const aBitScore  = pct(aBitrate,    lm.aBit);

                // Hexagonal layout — pointy-top orientation:
                //   Top:          Total size
                //   Upper-right:  Audio bitrate
                //   Lower-right:  Bit depth
                //   Bottom:       Duration
                //   Lower-left:   Resolution (pixel count)
                //   Upper-left:   Video bitrate
                const radarLabels = [
                    ['Size',       `(${f.SIZE})`],
                    ['Audio',      'Bitrate', `(${aBitrate.toFixed(1)}M)`],
                    ['Bit Depth',  `(${f.DEPTH || '—'})`],
                    ['Duration',   `(${f.DUR || '—'})`],
                    ['Resolution', `(${f.RES})`],
                    ['Video',      'Bitrate', `(${vBitrate.toFixed(1)}M)`]
                ];

                const rootStyle = getComputedStyle(document.documentElement);
                const radarTextColor = rootStyle.getPropertyValue('--text-main').trim() || '#f8fafc';
                const radarGridColor = rootStyle.getPropertyValue('--grid-line').trim() || 'rgba(148, 163, 184, 0.2)';
                const radarBgCard = rootStyle.getPropertyValue('--bg-card').trim() || '#080b11';

                window.modalChartInstance = new Chart(ctx, {
                    type: 'radar',
                    data: {
                        labels: radarLabels,
                        datasets: [{
                            label: 'File Profile',
                            data: [sizeScore, aBitScore, depthScore, durScore, resScore, vBitScore],
                            backgroundColor: nqiColor + '66',
                            borderColor: nqiColor,
                            pointBackgroundColor: nqiColor,
                            pointBorderColor: radarBgCard,
                            pointHoverBackgroundColor: radarTextColor,
                            pointHoverBorderColor: nqiColor
                        }]
                    },
                    options: {
                        maintainAspectRatio: false,
                        scales: {
                            r: {
                                angleLines: { display: true, color: radarGridColor },
                                grid: { display: true, color: radarGridColor },
                                pointLabels: { color: radarTextColor, font: { size: 11, weight: 'bold', family: 'monospace' } },
                                ticks: { display: false, max: 100, min: 0, stepSize: 25 }
                            }
                        },
                        plugins: { 
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: function(context) { return ` Percent of Library Max: ${Math.round(context.raw)}%`; }
                                }
                            }
                        }
                    }
                });
            }
        } catch(e) { console.error("Modal chart error", e); }
    }, 10);
};

window.closeFileModal = function() {
    const m = document.getElementById('fileModal');
    const backdrop = document.getElementById('fileModalBackdrop');
    if(m) {
        m.classList.remove('show');
    }
    if(backdrop) {
        backdrop.style.opacity = '0';
    }
    setTimeout(() => {
        if(m) m.style.display = 'none';
        if(backdrop) backdrop.style.display = 'none';
        if (window.modalChartInstance) {
            window.modalChartInstance.destroy();
            window.modalChartInstance = null;
        }
    }, 250);
};

function buildRows(items, emptyMsg, batchSize = 5) {
    if (!items.length) return `<tr><td colspan='7'>${emptyMsg}</td></tr>`;
    let html = '';
    items.forEach((f, i) => {
        if (i > 0 && i % batchSize === 0 && i !== items.length) {
            html += `<tr class="row-separator"><td colspan="7"></td></tr>`;
        }
        // Universal pill design in table logic
        html += `<tr class="clickable-row" onclick="openFileModal('${f.id}')">
            <td>${f.file}</td><td>${f.RES}</td><td>${f.VIDEO}</td><td>${f.HDR}</td><td>${f.AUDIO}</td>
            <td><span class="badge" style="background-color: ${getNqiColor(f.NQI)}; color: ${getNqiTextColor(f.NQI)}; border-radius: 999px; padding: 4px 12px; font-weight: bold; font-size: 0.75rem;">${f.NQI}</span></td>
            <td class="text-right">${f.SIZE}</td>
        </tr>`;
    });
    return html;
}

function populateTable(tableId, data, limit, emptyMsg) {
    const slice = data.slice(0, limit);
    const tbody = document.getElementById(`table-${tableId}`);
    if(tbody) tbody.innerHTML = buildRows(slice, emptyMsg);
    const fText = document.getElementById(`footer-text-${tableId}`);
    if(fText) fText.innerText = `Showing ${slice.length} of ${data.length} files`;
    
    const moreBtn = document.getElementById(`more-btn-${tableId}`);
    const lessBtn = document.getElementById(`less-btn-${tableId}`);
    
    if(moreBtn) moreBtn.style.display = slice.length < data.length ? 'inline-block' : 'none';
    if(lessBtn) lessBtn.style.display = limit > 5 ? 'inline-block' : 'none';
}

window.populateFullscreenTable = function(container) {
    const tbody = container.querySelector('.fs-tbody');
    const fText = container.querySelector('#footer-text-fs');
    const moreBtn = container.querySelector('#more-btn-fs');
    const lessBtn = container.querySelector('#less-btn-fs');
    if(!tbody) return;

    const sorted = currentFilteredData.sort((a,b) => b.size_bytes - a.size_bytes);
    const slice = sorted.slice(0, tableLimits.fs);
    
    tbody.innerHTML = buildRows(slice, "No files found matching current filters.");
    if(fText) fText.innerText = `Showing ${slice.length} of ${sorted.length} files`;
    
    if(moreBtn) moreBtn.style.display = slice.length < sorted.length ? 'inline-block' : 'none';
    if(lessBtn) lessBtn.style.display = tableLimits.fs > 5 ? 'inline-block' : 'none';
};

window.updateKPI = function(id, val, meta) {
    const valEl = document.getElementById(`kpi-${id}`);
    if(valEl) valEl.innerText = val;
    const metaEl = document.getElementById(`kpi-meta-${id}`);
    if(metaEl) metaEl.innerHTML = meta;
};

window.closeExpandedChart = function() {
    if (activeFullscreenElement) {
        toggleFullscreen(activeFullscreenElement, activeFullscreenElement.querySelector('.expand-btn'));
    }
}

window.toggleFullscreen = function(element, btn) {
    const isFullscreen = element.classList.toggle('chart-fullscreen');
    
    let backdrop = document.getElementById('fsBackdrop');
    if (!backdrop) {
        backdrop = document.createElement('div');
        backdrop.id = 'fsBackdrop';
        backdrop.onclick = closeExpandedChart;
        document.body.appendChild(backdrop);
    }
    
    backdrop.style.display = isFullscreen ? 'block' : 'none';

    btn.innerHTML = isFullscreen ? '✕' : '⛶';

    // Move the close button INTO the card-header so it sits in the sticky bar
    // (rather than floating in the card body where it scrolls away).
    const header = element.querySelector('.card-header');
    if (isFullscreen) {
        activeFullscreenElement = element;
        if (header && btn.parentElement !== header) {
            btn.__originalParent = btn.parentElement;
            btn.__originalNextSibling = btn.nextSibling;
            header.appendChild(btn);
        }

        // Wrap all non-header children into a .chart-fullscreen-body div so the
        // scrollable area lives below the header — mirrors .modal-body-scrollable
        // in the file modal, prevents scrollbar from bleeding into the header.
        let body = element.querySelector(':scope > .chart-fullscreen-body');
        if (!body) {
            body = document.createElement('div');
            body.className = 'chart-fullscreen-body';
            const toMove = [];
            for (const child of element.children) {
                if (child !== header && child !== body) toMove.push(child);
            }
            toMove.forEach(c => body.appendChild(c));
            element.appendChild(body);
        }
    } else {
        activeFullscreenElement = null;

        // Unwrap .chart-fullscreen-body — restore children to the chart-container
        // so the card returns to its in-flow layout cleanly.
        const body = element.querySelector(':scope > .chart-fullscreen-body');
        if (body) {
            while (body.firstChild) element.appendChild(body.firstChild);
            body.remove();
        }

        // Restore button to its original DOM position
        if (btn.__originalParent) {
            btn.__originalParent.insertBefore(btn, btn.__originalNextSibling || null);
            delete btn.__originalParent;
            delete btn.__originalNextSibling;
        }
    }
    
    let tableContainer = element.querySelector('.fullscreen-table-container');
    if (isFullscreen) {
        if (!tableContainer) {
            tableContainer = document.createElement('div');
            tableContainer.className = 'fullscreen-table-container';
            tableContainer.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin: 20px 40px 15px 40px;">
                    <h3 style="color: var(--primary); margin: 0;">Relevant Files</h3>
                </div>
                <div style="padding: 0 40px 40px 40px;">
                    <div class="table-wrapper" style="margin-bottom: 0;">
                        <table>
                            <thead><tr><th>Filename</th><th>Resolution</th><th>Video</th><th>HDR/SDR</th><th>Audio</th><th>NQI</th><th class="text-right">Size</th></tr></thead>
                            <tbody class="fs-tbody" id="table-fs"></tbody>
                        </table>
                        <div class="table-footer">
                            <span class="table-footer-text" id="footer-text-fs">Showing 5</span>
                            <div style="display: flex; gap: 8px;">
                                <button class="table-more-btn" id="less-btn-fs" onclick="loadLess('fs')" style="display: none;">Less</button>
                                <button class="table-more-btn" id="more-btn-fs" onclick="loadMore('fs')">More</button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            element.querySelector(':scope > .chart-fullscreen-body')?.appendChild(tableContainer)
                || element.appendChild(tableContainer);
            tableLimits.fs = 5; 
        }
        tableContainer.style.display = 'block';
        window.populateFullscreenTable(tableContainer);
    } else {
        if (tableContainer) tableContainer.style.display = 'none';
    }
    
    const canvas = element.querySelector('canvas');
    if (canvas && typeof Chart !== 'undefined') {
        setTimeout(() => {
            const chartInstance = Chart.getChart(canvas);
            if (chartInstance) chartInstance.resize();
        }, 50);

        // Live-resize the chart when the user drags the chart-wrapper's resize handle.
        // Wrap in rAF + try/catch — Chrome fires "ResizeObserver loop completed with
        // undelivered notifications" when the callback synchronously triggers another
        // layout, which Chart.js's resize() does. rAF defers it to the next frame.
        const wrapper = canvas.parentElement;
        if (isFullscreen && wrapper && !wrapper.__resizeObs) {
            let pending = false;
            const obs = new ResizeObserver(() => {
                if (pending) return;
                pending = true;
                requestAnimationFrame(() => {
                    pending = false;
                    try {
                        const c = Chart.getChart(canvas);
                        if (c) c.resize();
                    } catch (_) {}
                });
            });
            obs.observe(wrapper);
            wrapper.__resizeObs = obs;
        } else if (!isFullscreen && wrapper && wrapper.__resizeObs) {
            wrapper.__resizeObs.disconnect();
            delete wrapper.__resizeObs;
            wrapper.style.height = ''; // clear any drag-set height when leaving fullscreen
        }
    }
};

window.toggleHexMenu = function(e) {
    if(e) e.stopPropagation();
    document.getElementById('historyMenu')?.classList.remove('show');
    document.getElementById('meatballMenu')?.classList.remove('show');
    const menu = document.getElementById('hexMenu');
    if (!menu) return;
    if (menu.classList.contains('show')) {
        menu.classList.remove('show');
        return;
    }
    // Anchor to whichever trigger is visible right now
    _anchorMenuToTrigger(menu, ['hexBtn', 'heroTitle'], 'left');
    menu.classList.add('show');
};

// Close hex menu on outside click (history is a modal now, not a popover)
document.addEventListener('click', (e) => {
    const hex = document.getElementById('hexMenu');
    const hexBtn = document.getElementById('hexBtn');
    const heroTitle = document.getElementById('heroTitle');
    if (hex?.classList.contains('show') && !hex.contains(e.target) && !hexBtn?.contains(e.target) && !heroTitle?.contains(e.target)) {
        hex.classList.remove('show');
    }
});

window.toggleHistory = function(e) {
    // Legacy stub — history is now a modal launched from the hex menu
    if(e) e.stopPropagation();
    window.openHistoryModal();
};

window.openHistoryModal = function() {
    const m = document.getElementById('historyModal');
    if (m) m.style.display = 'flex';
    document.getElementById('hexMenu')?.classList.remove('show');
};
window.closeHistoryModal = function() {
    const m = document.getElementById('historyModal');
    if (m) m.style.display = 'none';
};

window.openChangelog = function() {
    const m = document.getElementById('changelogModal');
    if(m) m.style.display = 'flex';
    document.getElementById('hexMenu')?.classList.remove('show');
};
window.closeChangelog = function() {
    const m = document.getElementById('changelogModal');
    if(m) m.style.display = 'none';
};

window.openGuideModal = function(targetTab = 'intro') {
    const m = document.getElementById('guideModal');
    if(m) m.style.display = 'flex';
    document.getElementById('hexMenu')?.classList.remove('show');
    window.switchGuideTab(targetTab);
};

window.closeGuideModal = function() {
    const m = document.getElementById('guideModal');
    if(m) m.style.display = 'none';
};

window.switchGuideTab = function(tabId) {
    document.querySelectorAll('.guide-tab').forEach(btn => {
        btn.classList.remove('active');
        if (btn.getAttribute('onclick').includes(tabId)) btn.classList.add('active');
    });
    document.querySelectorAll('.guide-content').forEach(content => {
        content.style.display = 'none';
        content.classList.remove('active');
    });
    const activeContent = document.getElementById(`guide-${tabId}`);
    if (activeContent) {
        activeContent.style.display = 'block';
        activeContent.classList.add('active');
    }
};

function renderFilterBar() {
    const gfb = document.getElementById('globalFilterBar');
    const gfbPills = document.getElementById('gfbPills');
    const gfbClear = document.getElementById('gfbClearBtn');
    const dynamicBtn = document.getElementById('dynamicIconBtn');
    const dynamicInfo = document.getElementById('dynamicIconInfo');
    const dynamicClear = document.getElementById('dynamicIconClear');
    const topGavel = document.getElementById('topGavel');

    let hasFilters = false;
    let html = '';

    const displayKeyMap = {
        AUDIO_BASE: 'Audio', BITRATE_RANGE: 'Bitrate', SIZE_RANGE_GB: 'Size',
        VIDEO: 'Video', AUDIO: 'Audio', RES: 'Res', NQI: 'NQI', HDR: 'HDR',
        CAT: 'Category', SHOW: 'Series', DEPTH: 'Depth', EXT: 'Container'
    };
    Object.keys(activeFilters).forEach(key => {
        if (key.startsWith('_')) return;
        if (!activeFilters[key]) return;
        hasFilters = true;
        const displayKey = displayKeyMap[key] || (key.charAt(0) + key.slice(1).toLowerCase());
        const displayVal = activeFilters[`_${key}_label`] ||
            (Array.isArray(activeFilters[key]) ? activeFilters[key].join(', ') : activeFilters[key]);
        html += `<span class="gfb-pill"><span class="gfb-key">${displayKey}</span><span>${displayVal}</span><button class="gfb-x" onclick="toggleFilter('${key}')" aria-label="Remove">×</button></span>`;
    });

    if (gfb && gfbPills) {
        if (hasFilters) {
            gfbPills.innerHTML = html;
            gfb.classList.remove('empty');
            // Old text Reset button stays hidden — the red ✕ on the bar handles it
            if (gfbClear) gfbClear.style.display = 'none';
        } else {
            gfbPills.innerHTML = '';
            gfb.classList.add('empty');
            if (gfbClear) gfbClear.style.display = 'none';
        }
    }

    // Filter gavel: shows + turns red when filter pills are active (search does NOT trigger this)
    const filterGavel = document.getElementById('filterGavel');
    const topAddBtn   = document.getElementById('topAddFilterBtn');
    if (filterGavel) filterGavel.classList.toggle('active', hasFilters);
    document.body.classList.toggle('has-filter-bar', hasFilters);
    if (topAddBtn) topAddBtn.classList.toggle('has-filters', hasFilters);

    // Dynamic icon: (i) info default → (×) clear-all when filters exist
    if (dynamicBtn && dynamicInfo && dynamicClear) {
        if (hasFilters) {
            dynamicBtn.classList.add('has-filters');
            dynamicBtn.title = 'Clear all filters';
            dynamicBtn.setAttribute('aria-label', 'Clear all filters');
            dynamicInfo.style.display = 'none';
            dynamicClear.style.display = 'block';
        } else {
            dynamicBtn.classList.remove('has-filters');
            dynamicBtn.title = 'Documentation & Guides';
            dynamicBtn.setAttribute('aria-label', 'Documentation & Guides');
            dynamicInfo.style.display = 'block';
            dynamicClear.style.display = 'none';
        }
    }
}

window.handleDynamicIconClick = function(e) {
    const hasFilters = Object.keys(activeFilters).some(k => !k.startsWith('_') && activeFilters[k] !== null);
    if (hasFilters) {
        clearAllFilters(e);
    } else {
        openGuideModal('intro');
    }
};

window.openFilterModal = function() {
    const m = document.getElementById('filterMenuModal');
    if(m) m.style.display = 'flex';
    switchFilterTab('RES');
};

window.closeFilterModal = function() {
    const m = document.getElementById('filterMenuModal');
    if(m) m.style.display = 'none';
};

window.switchFilterTab = function(cat) {
    document.querySelectorAll('.filter-tab').forEach(btn => {
        btn.classList.remove('active');
        if (btn.getAttribute('onclick').includes(cat)) btn.classList.add('active');
    });
    const container = document.getElementById('filterChipContainer');
    if (!container) return;
    
    const uniqueVals = [...new Set(rawFiles.map(f => f[cat]))].filter(v => v !== undefined && v !== null && v !== '');
    
    if(cat === 'NQI') {
        uniqueVals.sort((a,b) => parseInt(b) - parseInt(a));
    } else if (cat === 'RES') {
        const resOrder = ['4K', '1080p', '720p', '480p'];
        uniqueVals.sort((a,b) => resOrder.indexOf(a) - resOrder.indexOf(b));
    } else if (cat === 'CAT') {
        const catOrder = ['TV Shows', 'Movies', 'Anime', 'Drama', 'Documentaries', 'J-TV', 'Sweden TV', 'Temp'];
        uniqueVals.sort((a,b) => {
            const ia = catOrder.indexOf(a), ib = catOrder.indexOf(b);
            return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
        });
    } else {
        uniqueVals.sort();
    }
    
    if(uniqueVals.length === 0) {
        container.innerHTML = `<span style="color: var(--text-muted); font-style: italic;">No data available.</span>`;
        return;
    }
    
    const catMap = {
        'RES': 'Resolution', 'NQI': 'Quality Score', 'CAT': 'Library Category',
        'VIDEO': 'Video Codec', 'AUDIO_BASE': 'Audio Format', 'HDR': 'Color / HDR',
        'DEPTH': 'Bit Depth', 'EXT': 'Container Format'
    };
    const headerText = catMap[cat] || cat;
    
    let chipsHtml = uniqueVals.map(v => {
        let displayVal = v;
        if (cat === 'NQI' && !v.includes('NQI')) displayVal = 'NQI ' + v;
        
        let isActive = false;
        if (activeFilters[cat]) {
            let compareVal = activeFilters[cat];
            if (cat === 'NQI') compareVal = String(compareVal).replace('NQI ', '').replace('Score ', '');
            
            if (Array.isArray(compareVal)) {
                if (compareVal.includes(String(v))) isActive = true;
            } else if (String(compareVal) === String(v)) {
                isActive = true;
            }
        }
        
        const style = isActive ? `background: var(--primary); color: var(--bg-card); border-color: var(--primary);` : '';
        return `<button class="filter-chip-btn" style="${style}" onclick="applyManualFilter('${cat}', '${v}', '${displayVal}')">${displayVal}</button>`;
    }).join('');
    
    container.innerHTML = `
        <div style="width: 100%;">
            <h4 style="margin-top: 0; color: var(--text-main); margin-bottom: 5px;">${headerText} Settings</h4>
            <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0; margin-bottom: 20px;">Select a specific data point to isolate it across the dashboard.</p>
            <div style="display: flex; flex-wrap: wrap; gap: 10px;">
                ${chipsHtml}
            </div>
        </div>
    `;
};

// ==============================================================================
// 4. FILTER PIPELINE LOGIC
// ==============================================================================
window.applyManualFilter = function(cat, val, label) {
    if (!Array.isArray(activeFilters[cat])) {
        activeFilters[cat] = activeFilters[cat] ? [activeFilters[cat]] : [];
    }

    const valIndex = activeFilters[cat].indexOf(String(val));
    if (valIndex > -1) {
        activeFilters[cat].splice(valIndex, 1);
        showToast(`Removed filter: ${label}`);
    } else {
        activeFilters[cat].push(String(val));
        showToast(`Added filter: ${label}`);
    }
    
    if (activeFilters[cat].length === 0) {
        activeFilters[cat] = null;
        activeFilters[`_${cat}_label`] = null;
    } else {
        activeFilters[`_${cat}_label`] = activeFilters[cat].join(', ');
    }
    
    runFilterPipeline();
    closeFilterModal();
    const exp = document.getElementById('libraryExplorer');
    if(exp) exp.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

window.clearAllFilters = function(e) {
    if(e && typeof e.preventDefault === 'function') e.preventDefault();
    Object.keys(activeFilters).forEach(k => activeFilters[k] = null);
    document.getElementById('hexMenu')?.classList.remove('show');
    showToast('Filters Cleared');
    runFilterPipeline();
    syncTopChartVisibility();
};

window.resetToBaseline = function(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (typeof clearAllFilters === 'function') clearAllFilters();
    window.scrollTo({ top: 0, behavior: 'smooth' });
};

window.clearSearch = function() {
    searchQuery = '';
    ['globalSearch', 'librarySearch', 'heroSearch'].forEach(id => {
        const inp = document.getElementById(id);
        if (inp) { inp.value = ''; inp.classList.remove('has-value'); }
    });
    ['searchClearBtn', 'librarySearchClearBtn', 'heroSearchClearBtn'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.style.display = 'none';
    });
    runFilterPipeline();
};

function syncSearchInputs(sourceId) {
    const ids = [
        { inp: 'globalSearch',   clear: 'searchClearBtn'        },
        { inp: 'librarySearch',  clear: 'librarySearchClearBtn' },
        { inp: 'heroSearch',     clear: 'heroSearchClearBtn'    },
    ];
    ids.forEach(({ inp, clear }) => {
        const el = document.getElementById(inp);
        const btn = document.getElementById(clear);
        if (!el) return;
        if (el.id !== sourceId) el.value = searchQuery;
        el.classList.toggle('has-value', searchQuery.length > 0);
        if (btn) btn.style.display = searchQuery ? 'flex' : 'none';
    });
}

window.jumpToLibrary = function() {
    const target = document.getElementById('libraryExplorer');
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

window.jumpToSystemHealth = function() {
    window.openSysHealthModal();
};

window.toggleSysHealth = function() {
    const header = document.getElementById('system-health');
    const body = document.getElementById('sysHealthBody');
    if (!header || !body) return;
    const isOpen = header.getAttribute('aria-expanded') === 'true';
    header.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
    body.classList.toggle('expanded', !isOpen);
    // When opening, scroll the header into view so the user sees the body unfold below
    if (!isOpen) {
        requestAnimationFrame(() => header.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    }
};

window.toggleKebabMenu = function(e) {
    if (e) e.stopPropagation();
    const menu = document.getElementById('meatballMenu');
    const btn = document.getElementById('footerKebabBtn') || document.getElementById('floatingHexBtn');
    if (!menu) return;
    if (menu.classList.contains('show')) {
        menu.classList.remove('show');
        btn?.classList.remove('active');
        return;
    }
    if (btn) {
        const rect = btn.getBoundingClientRect();
        menu.style.position = 'fixed';
        menu.style.bottom = `${Math.round(window.innerHeight - rect.top + 8)}px`;
        menu.style.right = `${Math.max(16, Math.round(window.innerWidth - rect.right))}px`;
        menu.style.top = 'auto';
        menu.style.left = 'auto';
    }
    menu.classList.add('show');
    btn?.classList.add('active');
};
window.toggleHexMenu = window.toggleKebabMenu;
window.toggleMeatballMenu = window.toggleKebabMenu;

// Click-outside handler for kebab menu
document.addEventListener('click', function(e) {
    const menu = document.getElementById('meatballMenu');
    const btn = document.getElementById('footerKebabBtn') || document.getElementById('floatingHexBtn');
    if (menu?.classList.contains('show') && !menu.contains(e.target) && !btn?.contains(e.target)) {
        menu.classList.remove('show');
        btn?.classList.remove('active');
    }
});

// Escape key to close any active menu or modal
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        if (typeof closeSysHealthModal === 'function') closeSysHealthModal();
        if (typeof closeGuideModal === 'function') closeGuideModal();
        if (typeof closeChangelog === 'function') closeChangelog();
        if (typeof closeHistoryModal === 'function') closeHistoryModal();
        if (typeof closeFilterModal === 'function') closeFilterModal();
        document.getElementById('meatballMenu')?.classList.remove('show');
        document.getElementById('footerKebabBtn')?.classList.remove('active');
    }
});

window.toggleFilter = function(key) {
    showToast(`Removed filter`);
    activeFilters[key] = null; 
    activeFilters[`_${key}_label`] = null;
    runFilterPipeline();
    syncTopChartVisibility();
};

// ==============================================================================
// KPI DETAIL MODAL — clicking a top KPI card opens a rich popup
// ==============================================================================
window.kpiSparklineChart = null;

window.openKpiModal = function(kind) {
    const modal = document.getElementById('kpiModal');
    const backdrop = document.getElementById('kpiModalBackdrop');
    const titleEl = document.getElementById('kpiModalTitle');
    const bodyEl = document.getElementById('kpiModalBody');
    if (!modal || !bodyEl) return;

    const cfg = _kpiConfig(kind);
    titleEl.innerHTML = `<span style="color:${cfg.color}; margin-right:6px;">⬢</span>${cfg.title}`;
    bodyEl.innerHTML = cfg.html;

    backdrop.style.display = 'block';
    modal.style.display = 'flex';
    void modal.offsetWidth;
    backdrop.style.opacity = '1';
    modal.classList.add('show');

    // Render sparkline once visible
    setTimeout(() => _renderKpiSparkline(kind, cfg.color), 50);
};

window.closeKpiModal = function() {
    const modal = document.getElementById('kpiModal');
    const backdrop = document.getElementById('kpiModalBackdrop');
    if (window.kpiSparklineChart) {
        try { window.kpiSparklineChart.destroy(); } catch(_) {}
        window.kpiSparklineChart = null;
    }
    if (modal) {
        modal.classList.remove('show');
        modal.style.display = 'none';
    }
    if (backdrop) {
        backdrop.style.opacity = '0';
        backdrop.style.display = 'none';
    }
};

window.kpiApplyFilterAndJump = function(kind) {
    closeKpiModal();
    const map = {
        files:        ['reset', null, null],
        storage:      ['reset', null, null],
        reclaimable:  ['NQI', ['6','7'], 'Bloat (Reclaimable)'],
        optimal:      ['NQI', ['4','5'], 'Optimal Encodes'],
        transcode:    ['NQI', ['6','7'], 'Transcode Targets'],
        upgrade:      ['NQI', ['1','2'], 'Upgrade Targets'],
    };
    const [type, values, label] = map[kind] || ['reset', null, null];
    triggerKpiFilter(type, values, label);
};

function _kpiConfig(kind) {
    const totalFiles = rawFiles.length || 0;
    const totalGB = rawFiles.reduce((s, f) => s + (f.size_bytes || 0), 0) / (1024 ** 3);

    const countByNqi = {};
    const sizeByNqi = {};
    rawFiles.forEach(f => {
        const k = String(f.NQI || 'N/A');
        countByNqi[k] = (countByNqi[k] || 0) + 1;
        sizeByNqi[k]  = (sizeByNqi[k]  || 0) + (f.size_bytes || 0);
    });

    const sumNqi = (keys) => keys.reduce((s, k) => s + (countByNqi[k] || 0), 0);
    const sumNqiSize = (keys) => keys.reduce((s, k) => s + (sizeByNqi[k] || 0), 0) / (1024 ** 3);

    if (kind === 'files') {
        return {
            title: 'Total Files',
            color: '#38bdf8',
            html: _kpiSummaryHtml({
                kind: 'files',
                bigStat: totalFiles.toLocaleString(),
                bigStatLabel: 'media files indexed',
                description: 'The complete count of every media file currently tracked in your library cache. This includes every NQI tier and every codec.',
                table: _kpiBreakdownByRes(rawFiles),
                tableTitle: 'Breakdown by Resolution',
                ctaLabel: 'View all files',
            })
        };
    }
    if (kind === 'storage') {
        return {
            title: 'Total Storage',
            color: '#38bdf8',
            html: _kpiSummaryHtml({
                kind: 'storage',
                bigStat: totalGB.toLocaleString(undefined, { maximumFractionDigits: 0 }) + ' GB',
                bigStatLabel: `≈ ${(totalGB / 1024).toFixed(2)} TB on disk`,
                description: 'Total bytes consumed by all indexed media. Compare the per-tier breakdown to find where your storage budget is going.',
                table: _kpiBreakdownByNqiSize(sizeByNqi),
                tableTitle: 'Storage by NQI Tier',
                ctaLabel: 'View all files',
            })
        };
    }
    if (kind === 'optimal') {
        const c = sumNqi(['4', '5']);
        const sz = sumNqiSize(['4', '5']);
        return {
            title: 'Optimal Encodes',
            color: '#34d399',
            html: _kpiSummaryHtml({
                kind: 'optimal',
                bigStat: c.toLocaleString(),
                bigStatLabel: `files (${sz.toFixed(1)} GB) — NQI 4 & 5`,
                description: 'Files in the sweet spot — quality is high enough to look great on modern displays, and file size is reasonable for the resolution. Leave these alone.',
                table: _kpiBreakdownByCodec(rawFiles, ['4', '5']),
                tableTitle: 'Codec mix in this tier',
                ctaLabel: 'Filter library to NQI 4–5',
            })
        };
    }
    if (kind === 'reclaimable') {
        const bloatBytes = rawFiles.filter(f => ['6','7'].includes(String(f.NQI)))
                                    .reduce((s, f) => s + (f.size_bytes || 0), 0);
        const totalGB = rawFiles.reduce((s, f) => s + (f.size_bytes || 0), 0) / (1024 ** 3);
        const reclaimGB = (bloatBytes * 0.5) / (1024 ** 3);
        const bloatGB = bloatBytes / (1024 ** 3);
        const cBloat = sumNqi(['6', '7']);
        const reclaimPct = totalGB > 0 ? ((reclaimGB / totalGB) * 100) : 0;
        return {
            title: 'Reclaimable Storage',
            color: '#d946ef',
            html: _kpiSummaryHtml({
                kind: 'reclaimable',
                bigStat: reclaimGB.toLocaleString(undefined, { maximumFractionDigits: 0 }) + ' GB',
                bigStatLabel: `≈ ${reclaimPct.toFixed(1)}% of your library — projected savings`,
                description: `If you transcode all <strong>${cBloat.toLocaleString()} files</strong> in the bloat tier (NQI 6–7, totalling ${bloatGB.toFixed(1)} GB) to HEVC at sane bitrate targets, you can expect roughly half the original size back. That's around <strong>${reclaimGB.toFixed(1)} GB freed</strong> with negligible visible quality loss. Click any file in the Library Explorer to get a ready-to-run ffmpeg/HandBrake command for it.`,
                table: _kpiBreakdownByCodec(rawFiles, ['6', '7']),
                tableTitle: 'Bloat-tier codec mix (best HEVC candidates first)',
                ctaLabel: 'Filter library to NQI 6–7',
            })
        };
    }
    if (kind === 'transcode') {
        const c = sumNqi(['6', '7']);
        const sz = sumNqiSize(['6', '7']);
        return {
            title: 'Transcode Targets',
            color: '#d946ef',
            html: _kpiSummaryHtml({
                kind: 'transcode',
                bigStat: c.toLocaleString(),
                bigStatLabel: `files (${sz.toFixed(1)} GB) — NQI 6 & 7`,
                description: 'Files where bitrate is well above what the resolution needs. Strong candidates for HEVC transcoding — you can cut storage substantially with negligible visual loss.',
                table: _kpiBreakdownByCodec(rawFiles, ['6', '7']),
                tableTitle: 'Codec mix among bloat candidates',
                ctaLabel: 'Filter library to NQI 6–7',
            })
        };
    }
    if (kind === 'upgrade') {
        const c = sumNqi(['1', '2']);
        const sz = sumNqiSize(['1', '2']);
        return {
            title: 'Upgrade Targets',
            color: '#f97316',
            html: _kpiSummaryHtml({
                kind: 'upgrade',
                bigStat: c.toLocaleString(),
                bigStatLabel: `files (${sz.toFixed(1)} GB) — NQI 1 & 2`,
                description: 'Files with bitrate too low for their resolution — likely artifacted, blocky, or sub-optimal source quality. Transcoding will not help. Look for higher-quality replacements.',
                table: _kpiBreakdownByRes(rawFiles.filter(f => ['1', '2'].includes(String(f.NQI)))),
                tableTitle: 'Resolution distribution of upgrade candidates',
                ctaLabel: 'Filter library to NQI 1–2',
            })
        };
    }
    return { title: kind, color: '#38bdf8', html: '<div style="padding:20px;color:var(--text-muted);">No data.</div>' };
}

function _kpiSummaryHtml(opts) {
    return `
        <div style="padding: 24px;">
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px;">
                <div>
                    <div style="font-size: 2.4rem; font-weight: 700; color: var(--text-main); line-height: 1.1;">${opts.bigStat}</div>
                    <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 4px;">${opts.bigStatLabel}</div>
                </div>
                <div style="background: var(--bg-body); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px;">
                    <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px;">90-day trend</div>
                    <div style="height: 56px; position: relative;"><canvas id="kpiModalSparkline"></canvas></div>
                </div>
            </div>

            <div style="background: var(--bg-body); border: 1px solid var(--border); border-radius: 8px; padding: 16px 18px; margin-bottom: 20px;">
                <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px;">What this means</div>
                <div style="font-size: 0.88rem; color: var(--text-main); line-height: 1.5;">${opts.description}</div>
            </div>

            <h4 style="margin: 0 0 10px 0; color: var(--text-main); font-size: 0.92rem;">${opts.tableTitle}</h4>
            ${opts.table}

            <div style="display:flex; justify-content:flex-end; margin-top: 22px; gap: 10px;">
                <button onclick="closeKpiModal()" style="padding: 8px 18px; background: transparent; color: var(--text-muted); border: 1px solid var(--border); border-radius: 6px; cursor: pointer; font-size: 0.85rem;">Close</button>
                <button onclick="kpiApplyFilterAndJump('${opts.kind}')" style="padding: 8px 18px; background: var(--primary); color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 600;">${opts.ctaLabel} →</button>
            </div>
        </div>
    `;
}

function _kpiTableRow(label, count, valueExtra, color, clickAttr) {
    const total = rawFiles.length || 1;
    const pct = (count / total) * 100;
    const cursor = clickAttr ? 'pointer' : 'default';
    const hoverHook = clickAttr ? 'class="kpi-row-clickable"' : '';
    return `
        <div ${hoverHook} ${clickAttr || ''} style="display:grid; grid-template-columns: 1fr auto auto; gap: 14px; align-items: center; padding: 8px 10px; margin: 0 -10px; border-bottom: 1px dashed var(--border); cursor: ${cursor}; border-radius: 6px; transition: background 0.12s ease;">
            <div style="display:flex; align-items:center; gap:10px; min-width:0;">
                <div style="width: 8px; height: 8px; border-radius: 999px; background: ${color || 'var(--primary)'}; flex-shrink: 0;"></div>
                <div style="font-size: 0.85rem; color: var(--text-main); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${label}</div>
            </div>
            <div style="font-size: 0.82rem; color: var(--text-muted); font-variant-numeric: tabular-nums;">${valueExtra || ''}</div>
            <div style="font-size: 0.85rem; color: var(--text-main); font-weight: 600; font-variant-numeric: tabular-nums; min-width: 90px; text-align: right;">${count.toLocaleString()} <span style="color: var(--text-muted); font-weight: 400; font-size: 0.75rem;">(${pct.toFixed(1)}%)</span></div>
        </div>
    `;
}

function _kpiBreakdownByRes(files) {
    const groups = {};
    files.forEach(f => {
        const r = f.RES || 'Unknown';
        groups[r] = (groups[r] || 0) + 1;
    });
    const palette = ['#38bdf8', '#818cf8', '#2dd4bf', '#f472b6', '#fbbf24', '#64748b', '#94a3b8'];
    const rows = Object.entries(groups).sort((a, b) => b[1] - a[1]).slice(0, 8);
    return rows.map(([r, c], i) => {
        const click = r !== 'Unknown' ? `onclick="kpiApplyFromRow('RES', '${_kpiEscape(r)}', '${_kpiEscape(r)}')"` : '';
        return _kpiTableRow(r, c, '', palette[i % palette.length], click);
    }).join('');
}

function _kpiBreakdownByNqiSize(sizeByNqi) {
    const colorMap = { '1': '#dc2626', '2': '#f97316', '3': '#fbbf24', '4': '#84cc16', '5': '#34d399', '6': '#a855f7', '7': '#d946ef' };
    const labelMap = { '1': 'NQI 1 — Critical', '2': 'NQI 2 — Upgrade', '3': 'NQI 3 — Acceptable', '4': 'NQI 4 — Optimal', '5': 'NQI 5 — Optimal', '6': 'NQI 6 — Bloat', '7': 'NQI 7 — Bloat', 'N/A': 'Unknown' };
    const totalGB = Object.values(sizeByNqi).reduce((s, b) => s + b, 0) / (1024 ** 3);
    const rows = Object.entries(sizeByNqi)
        .map(([k, v]) => ({ k, gb: v / (1024 ** 3) }))
        .sort((a, b) => b.gb - a.gb);
    return rows.map(({ k, gb }) => {
        const pct = totalGB > 0 ? (gb / totalGB) * 100 : 0;
        const clickable = k !== 'N/A';
        const click = clickable ? `onclick="kpiApplyFromRow('NQI', ['${k}'], '${_kpiEscape(labelMap[k] || k)}')"` : '';
        const cursor = clickable ? 'pointer' : 'default';
        const hoverHook = clickable ? 'class="kpi-row-clickable"' : '';
        return `
            <div ${hoverHook} ${click} style="display:grid; grid-template-columns: 1fr auto; gap: 14px; align-items: center; padding: 8px 10px; margin: 0 -10px; border-bottom: 1px dashed var(--border); cursor: ${cursor}; border-radius: 6px; transition: background 0.12s ease;">
                <div style="display:flex; align-items:center; gap:10px; min-width:0;">
                    <div style="width: 8px; height: 8px; border-radius: 999px; background: ${colorMap[k] || '#94a3b8'}; flex-shrink: 0;"></div>
                    <div style="font-size: 0.85rem; color: var(--text-main);">${labelMap[k] || k}</div>
                </div>
                <div style="font-size: 0.85rem; color: var(--text-main); font-weight: 600; font-variant-numeric: tabular-nums; text-align: right;">${gb.toFixed(1)} GB <span style="color: var(--text-muted); font-weight: 400; font-size: 0.75rem;">(${pct.toFixed(1)}%)</span></div>
            </div>
        `;
    }).join('');
}

function _kpiBreakdownByCodec(allFiles, nqiKeys) {
    const filtered = allFiles.filter(f => nqiKeys.includes(String(f.NQI)));
    const groups = {};
    filtered.forEach(f => {
        const c = f.VIDEO || 'Unknown';
        groups[c] = (groups[c] || 0) + 1;
    });
    const palette = ['#38bdf8', '#a855f7', '#34d399', '#f472b6', '#fbbf24', '#64748b'];
    const rows = Object.entries(groups).sort((a, b) => b[1] - a[1]).slice(0, 6);
    if (rows.length === 0) {
        return `<div style="padding: 14px 0; color: var(--text-muted); font-size: 0.85rem; font-style: italic;">No files in this tier.</div>`;
    }
    const total = filtered.length || 1;
    return rows.map(([codec, count], i) => {
        const pct = (count / total) * 100;
        const clickable = codec !== 'Unknown';
        // Build inline onclick safely — JSON.stringify produces double-quotes which
        // would break the onclick="..." attribute. Use single-quoted JS array literal instead.
        const nqiArrJs = '[' + nqiKeys.map(k => `'${_kpiEscape(k)}'`).join(',') + ']';
        const click = clickable
            ? `onclick="kpiApplyMulti({VIDEO: '${_kpiEscape(codec)}', NQI: ${nqiArrJs}}, '${_kpiEscape(codec)} · NQI ${nqiKeys.join('–')}')"`
            : '';
        const cursor = clickable ? 'pointer' : 'default';
        const hoverHook = clickable ? 'class="kpi-row-clickable"' : '';
        return `
            <div ${hoverHook} ${click} style="display:grid; grid-template-columns: 1fr auto; gap: 14px; align-items: center; padding: 8px 10px; margin: 0 -10px; border-bottom: 1px dashed var(--border); cursor: ${cursor}; border-radius: 6px; transition: background 0.12s ease;">
                <div style="display:flex; align-items:center; gap:10px; min-width:0;">
                    <div style="width: 8px; height: 8px; border-radius: 999px; background: ${palette[i % palette.length]}; flex-shrink: 0;"></div>
                    <div style="font-size: 0.85rem; color: var(--text-main); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${codec}</div>
                </div>
                <div style="font-size: 0.85rem; color: var(--text-main); font-weight: 600; font-variant-numeric: tabular-nums; text-align: right;">${count.toLocaleString()} <span style="color: var(--text-muted); font-weight: 400; font-size: 0.75rem;">(${pct.toFixed(1)}%)</span></div>
            </div>
        `;
    }).join('');
}

function _kpiEscape(s) {
    return String(s).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// Single-filter row click — close modal, apply filter, scroll to library
window.kpiApplyFromRow = function(type, values, label) {
    closeKpiModal();
    const vals = Array.isArray(values) ? values : [values];
    triggerKpiFilter(type, vals, label);
};

// Multi-filter row click (e.g. codec + NQI tier together)
window.kpiApplyMulti = function(filterMap, label) {
    closeKpiModal();
    Object.keys(activeFilters).forEach(k => activeFilters[k] = null);
    Object.entries(filterMap).forEach(([k, v]) => {
        activeFilters[k] = Array.isArray(v) ? v : [v];
        activeFilters[`_${k}_label`] = Array.isArray(v) ? v.join(', ') : v;
    });
    showToast(`Applied filter: ${label}`);
    runFilterPipeline();
    syncTopChartVisibility();
    const exp = document.getElementById('libraryExplorer');
    if (exp) exp.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

function _renderKpiSparkline(kind, color) {
    if (typeof Chart === 'undefined' || !historyLog || historyLog.length < 2) return;
    const ctx = document.getElementById('kpiModalSparkline');
    if (!ctx) return;
    const series = historyLog.map(h => {
        if (kind === 'files')     return h.total_files || 0;
        if (kind === 'storage')   return h.total_gb || 0;
        if (kind === 'optimal')   return h.optimal || 0;
        if (kind === 'transcode') return h.transcode || 0;
        if (kind === 'upgrade')   return h.upgrade || 0;
        return 0;
    });
    if (window.kpiSparklineChart) {
        try { window.kpiSparklineChart.destroy(); } catch (_) {}
    }
    window.kpiSparklineChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: historyLog.map(h => h.date),
            datasets: [{
                data: series,
                borderColor: color,
                backgroundColor: color + '33',
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.3,
                fill: true,
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { enabled: true, mode: 'index', intersect: false } },
            scales: {
                x: { display: false },
                y: { display: false, beginAtZero: false }
            },
            elements: { line: { borderJoinStyle: 'round' } }
        }
    });
}

window.triggerKpiFilter = function(type, values, label) {
    if (type === 'reset') {
        Object.keys(activeFilters).forEach(k => activeFilters[k] = null);
        showToast('Reset all filters');
    } else {
        Object.keys(activeFilters).forEach(k => activeFilters[k] = null); 
        activeFilters[type] = values;
        activeFilters[`_${type}_label`] = label; 
        showToast(`Applied filter: ${label}`);
    }
    runFilterPipeline();
    syncTopChartVisibility();
    const exp = document.getElementById('libraryExplorer');
    if (exp) exp.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

window.loadMore = function(tableId) {
    if (tableLimits[tableId] !== undefined) {
        tableLimits[tableId] += 5; 
        if (tableId === 'fs') {
            const fsContainer = document.querySelector('.chart-fullscreen .fullscreen-table-container');
            if (fsContainer) window.populateFullscreenTable(fsContainer.parentElement);
        } else {
            updateTables(currentFilteredData);
        }
    }
};

window.loadLess = function(tableId) {
    if (tableLimits[tableId] !== undefined && tableLimits[tableId] > 5) {
        tableLimits[tableId] = Math.max(5, tableLimits[tableId] - 5);
        if (tableId === 'fs') {
            const fsContainer = document.querySelector('.chart-fullscreen .fullscreen-table-container');
            if (fsContainer) window.populateFullscreenTable(fsContainer.parentElement);
        } else {
            updateTables(currentFilteredData);
        }
    }
};

window.exportDataToCSV = function() {
    if (!currentFilteredData || currentFilteredData.length === 0) return;
    const headers = ['file', 'dir', 'RES', 'VIDEO', 'AUDIO', 'NQI', 'SIZE', 'size_bytes', 'DUR', 'BITRATE', 'FPS', 'HDR'];
    const csvRows = [];
    csvRows.push(headers.join(','));
    for (const row of currentFilteredData) {
        const values = headers.map(header => {
            const escaped = ('' + row[header]).replace(/"/g, '""');
            return `"${escaped}"`;
        });
        csvRows.push(values.join(','));
    }
    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.setAttribute('hidden', '');
    a.setAttribute('href', url);
    a.setAttribute('download', 'nnuva_library_export.csv');
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    document.getElementById('hexMenu')?.classList.remove('show');
    showToast("CSV Exported Successfully");
};

function _sortFiles(arr, key, dir) {
    const mult = dir === 'asc' ? 1 : -1;
    const isNumeric = (key === 'size_bytes' || key === 'NQI');
    return [...arr].sort((a, b) => {
        let av = a[key];
        let bv = b[key];
        if (isNumeric) {
            // NQI may be a string like "4" or "N/A"; treat non-numeric as -Infinity
            const an = parseFloat(av);
            const bn = parseFloat(bv);
            const aSafe = isNaN(an) ? -Infinity : an;
            const bSafe = isNaN(bn) ? -Infinity : bn;
            return (aSafe - bSafe) * mult;
        }
        // String compare, case-insensitive, with safe fallback
        av = (av == null ? '' : String(av)).toLowerCase();
        bv = (bv == null ? '' : String(bv)).toLowerCase();
        if (av < bv) return -1 * mult;
        if (av > bv) return  1 * mult;
        return 0;
    });
}

function _applyTableSort(data, tableKey) {
    const cfg = tableSort[tableKey] || { key: 'size_bytes', dir: 'desc' };
    return _sortFiles(data, cfg.key, cfg.dir);
}

window.toggleTableSort = function(tableKey, sortKey) {
    const cur = tableSort[tableKey] || { key: 'size_bytes', dir: 'desc' };
    if (cur.key === sortKey) {
        // Same column — toggle direction
        cur.dir = cur.dir === 'asc' ? 'desc' : 'asc';
    } else {
        cur.key = sortKey;
        // Sensible default for newly-clicked column: numeric → desc, string → asc
        cur.dir = (sortKey === 'size_bytes' || sortKey === 'NQI') ? 'desc' : 'asc';
    }
    tableSort[tableKey] = cur;
    _updateSortIndicators(tableKey);
    runFilterPipeline();
};

function _updateSortIndicators(tableKey) {
    const cfg = tableSort[tableKey];
    if (!cfg) return;
    document.querySelectorAll(`[data-indicator-table="${tableKey}"]`).forEach(el => {
        el.classList.remove('sort-asc', 'sort-desc');
        if (el.dataset.indicatorKey === cfg.key) {
            el.classList.add(cfg.dir === 'asc' ? 'sort-asc' : 'sort-desc');
        }
    });
}

window.toggleSeriesSort = function(sortKey) {
    const cur = tableSort.series || { key: 'bytes', dir: 'desc' };
    if (cur.key === sortKey) {
        cur.dir = cur.dir === 'asc' ? 'desc' : 'asc';
    } else {
        cur.key = sortKey;
        cur.dir = (sortKey === 'show' || sortKey === 'cat') ? 'asc' : 'desc';
    }
    tableSort.series = cur;
    _updateSortIndicators('series');
    runFilterPipeline();
};

function populateSeriesTable(data, limit) {
    const tbody = document.getElementById('table-series');
    if (!tbody) return;
    const seriesList = aggregateSeriesData(data);
    const cfg = tableSort.series || { key: 'bytes', dir: 'desc' };
    const mult = cfg.dir === 'asc' ? 1 : -1;
    const isStr = (cfg.key === 'show' || cfg.key === 'cat');

    seriesList.sort((a, b) => {
        if (isStr) {
            const av = String(a[cfg.key] || '').toLowerCase();
            const bv = String(b[cfg.key] || '').toLowerCase();
            return av < bv ? -1 * mult : (av > bv ? 1 * mult : 0);
        }
        return ((a[cfg.key] || 0) - (b[cfg.key] || 0)) * mult;
    });

    const slice = seriesList.slice(0, limit);
    if (!slice.length) {
        tbody.innerHTML = `<tr><td colspan="8">No multi-episode series found.</td></tr>`;
    } else {
        let html = '';
        slice.forEach((st, i) => {
            if (i > 0 && i % 5 === 0 && i !== slice.length) {
                html += `<tr class="row-separator"><td colspan="8"></td></tr>`;
            }
            const safeShow = String(st.show).replace(/'/g, "\\'").replace(/"/g, '&quot;');
            const nqiRound = st.avg_nqi > 0 ? Math.round(st.avg_nqi) : 'N/A';
            const nqiDisplay = st.avg_nqi > 0 ? st.avg_nqi.toFixed(1) : 'N/A';
            const reclaimStr = st.reclaim_bytes > 0
                ? `<span style="color:#d946ef;font-weight:600;">${formatGb(st.reclaim_bytes)}</span>`
                : `<span style="color:var(--text-muted);">—</span>`;
            const catColor = getCatColor(st.cat);
            html += `<tr class="clickable-row" onclick="applyManualFilter('SHOW', '${safeShow}', '${safeShow}')" title="Click to filter all ${st.count} files in ${safeShow}">
                <td style="font-weight:600;color:var(--text-main);">${st.show}</td>
                <td><span style="display:inline-flex;align-items:center;gap:6px;"><span style="width:8px;height:8px;border-radius:999px;background:${catColor};"></span>${st.cat}</span></td>
                <td>${st.count.toLocaleString()}</td>
                <td>${formatRuntimeHours(st.dur_sec)}</td>
                <td>${st.gb_hr.toFixed(2)} GB/h</td>
                <td><span class="badge" style="background-color: ${getNqiColor(nqiRound)}; color: ${getNqiTextColor(nqiRound)}; border-radius: 999px; padding: 4px 12px; font-weight: bold; font-size: 0.75rem;">${nqiDisplay}</span></td>
                <td>${reclaimStr}</td>
                <td class="text-right" style="font-weight:600;">${formatGb(st.bytes)}</td>
            </tr>`;
        });
        tbody.innerHTML = html;
    }

    const fText = document.getElementById('footer-text-series');
    if (fText) fText.innerText = `Showing ${slice.length} of ${seriesList.length} series`;
    const moreBtn = document.getElementById('more-btn-series');
    const lessBtn = document.getElementById('less-btn-series');
    if (moreBtn) moreBtn.style.display = slice.length < seriesList.length ? 'inline-block' : 'none';
    if (lessBtn) lessBtn.style.display = limit > 5 ? 'inline-block' : 'none';
}

function updateTables(data) {
    const hasFilters = searchQuery.trim() !== '' || Object.keys(activeFilters).some(k => !k.startsWith('_') && activeFilters[k] !== null);
    const filteredContainer = document.getElementById('filteredViewContainer');
    const defaultContainer = document.getElementById('defaultViewContainer');

    if (hasFilters) {
        if (filteredContainer) filteredContainer.style.display = 'block';
        if (defaultContainer) defaultContainer.style.display = 'none';
        const sorted = _applyTableSort(data, 'filtered');
        populateTable('filtered', sorted, tableLimits.filtered, "No files found matching your filters.");
        _updateSortIndicators('filtered');
    } else {
        if (filteredContainer) filteredContainer.style.display = 'none';
        if (defaultContainer) defaultContainer.style.display = 'block';

        // Each default table gets its own filter then its own sort
        const trnRaw = data.filter(f => ['6','7'].includes(String(f.NQI)));
        populateTable('transcode', _applyTableSort(trnRaw, 'transcode'), tableLimits.transcode, "No transcode targets found.");

        const upgRaw = data.filter(f => ['1','2'].includes(String(f.NQI)));
        populateTable('upgrade',   _applyTableSort(upgRaw, 'upgrade'),   tableLimits.upgrade,   "No upgrade targets found.");

        populateSeriesTable(data, tableLimits.series);

        populateTable('largest',   _applyTableSort(data, 'largest'),    tableLimits.largest,   "No files found.");

        _updateSortIndicators('transcode');
        _updateSortIndicators('upgrade');
        _updateSortIndicators('series');
        _updateSortIndicators('largest');
    }

    const fsContainer = document.querySelector('.chart-fullscreen .fullscreen-table-container');
    if (fsContainer && fsContainer.style.display !== 'none') {
        window.populateFullscreenTable(fsContainer.parentElement);
    }
}

function runFilterPipeline() {
    let currentData = rawFiles.filter(f => {
        if (activeFilters.RES && activeFilters.RES.length > 0) {
            if (Array.isArray(activeFilters.RES)) {
                if (!activeFilters.RES.includes(String(f.RES))) return false;
            } else {
                if (String(f.RES) !== String(activeFilters.RES)) return false;
            }
        }
        
        if (activeFilters.NQI && activeFilters.NQI.length > 0) {
            if (Array.isArray(activeFilters.NQI)) {
                if (!activeFilters.NQI.includes(String(f.NQI))) return false;
            } else {
                if (String(f.NQI) !== String(activeFilters.NQI)) return false;
            }
        }

        if (activeFilters.CAT && activeFilters.CAT.length > 0) {
            if (Array.isArray(activeFilters.CAT)) {
                if (!activeFilters.CAT.includes(String(f.CAT))) return false;
            } else {
                if (String(f.CAT) !== String(activeFilters.CAT)) return false;
            }
        }

        if (activeFilters.SHOW && activeFilters.SHOW.length > 0) {
            if (!f.SHOW) return false;
            if (Array.isArray(activeFilters.SHOW)) {
                if (!activeFilters.SHOW.includes(String(f.SHOW))) return false;
            } else {
                if (String(f.SHOW) !== String(activeFilters.SHOW)) return false;
            }
        }
        
        if (activeFilters.VIDEO && activeFilters.VIDEO.length > 0) {
            if (Array.isArray(activeFilters.VIDEO)) {
                if (!activeFilters.VIDEO.includes(f.VIDEO)) return false;
            } else {
                if (f.VIDEO !== activeFilters.VIDEO) return false;
            }
        }

        if (activeFilters.AUDIO_BASE && activeFilters.AUDIO_BASE.length > 0) {
            if (Array.isArray(activeFilters.AUDIO_BASE)) {
                if (!activeFilters.AUDIO_BASE.includes(f.AUDIO_BASE)) return false;
            } else {
                if (f.AUDIO_BASE !== activeFilters.AUDIO_BASE) return false;
            }
        }

        if (activeFilters.HDR && activeFilters.HDR.length > 0) {
            if (Array.isArray(activeFilters.HDR)) {
                if (!activeFilters.HDR.includes(f.HDR)) return false;
            } else {
                if (f.HDR !== activeFilters.HDR) return false;
            }
        }

        if (activeFilters.DEPTH && activeFilters.DEPTH.length > 0) {
            if (Array.isArray(activeFilters.DEPTH)) {
                if (!activeFilters.DEPTH.includes(String(f.DEPTH))) return false;
            } else {
                if (String(f.DEPTH) !== String(activeFilters.DEPTH)) return false;
            }
        }

        if (activeFilters.EXT && activeFilters.EXT.length > 0) {
            if (Array.isArray(activeFilters.EXT)) {
                if (!activeFilters.EXT.includes(String(f.EXT))) return false;
            } else {
                if (String(f.EXT) !== String(activeFilters.EXT)) return false;
            }
        }

        // Range filters from scatter cluster zoom-in
        if (Array.isArray(activeFilters.BITRATE_RANGE) && activeFilters.BITRATE_RANGE.length === 2) {
            const mbps = parseMbps(f.BITRATE);
            if (mbps === null) return false;
            const [lo, hi] = activeFilters.BITRATE_RANGE;
            if (mbps < lo || mbps > hi) return false;
        }
        if (Array.isArray(activeFilters.SIZE_RANGE_GB) && activeFilters.SIZE_RANGE_GB.length === 2) {
            const gb = f.size_bytes / (1024 ** 3);
            const [lo, hi] = activeFilters.SIZE_RANGE_GB;
            if (gb < lo || gb > hi) return false;
        }

        return true;
    });

    // Search filter: filename or directory match
    if (searchQuery.trim()) {
        const q = searchQuery.trim().toLowerCase();
        currentData = currentData.filter(f =>
            (f.file && f.file.toLowerCase().includes(q)) ||
            (f.dir  && f.dir.toLowerCase().includes(q))
        );
    }

    currentFilteredData = currentData; 
    
    tableLimits.filtered = 5;
    tableLimits.transcode = 5;
    tableLimits.upgrade = 5;
    tableLimits.series = 5;
    tableLimits.largest = 5;
    tableLimits.fs = 5;
    
    renderFilterBar();

    let tFiles = currentData.length;
    let tBytes = currentData.reduce((sum, f) => sum + f.size_bytes, 0);
    let tDurSec = currentData.reduce((sum, f) => sum + (f.DUR_SEC || 0), 0);
    let tHrsStr = formatRuntimeHours(tDurSec);
    let cOpt = currentData.filter(f => ['4','5'].includes(String(f.NQI))).length;
    let cTrn = currentData.filter(f => ['6','7'].includes(String(f.NQI))).length;
    let cUpg = currentData.filter(f => ['1','2'].includes(String(f.NQI))).length;
    
    let avgSizeStr = "0 MB avg";
    let largestName = "None";
    let sampleNames = "";

    if (tFiles > 0) {
        let avgBytes = tBytes / tFiles;
        if (avgBytes > 1024**3) avgSizeStr = (avgBytes / (1024**3)).toFixed(2) + ' GB';
        else avgSizeStr = (avgBytes / (1024**2)).toFixed(0) + ' MB';
        
        let sortedFiles = [...currentData].sort((a,b) => b.size_bytes - a.size_bytes);
        largestName = sortedFiles[0].file;
        if (largestName.length > 20) largestName = largestName.substring(0, 17) + '...';
        
        sampleNames = currentData.slice(0, 2).map(f => f.file).join(', ');
        if (sampleNames.length > 30) sampleNames = sampleNames.substring(0, 27) + '...';
    }
    
    let optPct = tFiles > 0 ? ((cOpt / tFiles) * 100).toFixed(1) + '%' : '0%';
    let trnPct = tFiles > 0 ? ((cTrn / tFiles) * 100).toFixed(1) + '%' : '0%';
    let upgPct = tFiles > 0 ? ((cUpg / tFiles) * 100).toFixed(1) + '%' : '0%';

    try {
        updateKPI('files', tFiles.toLocaleString(), '');

        const kpiMetaFiles = document.getElementById('kpi-meta-files');
        let latestDelta = null;
        if (historyLog && historyLog.length > 0) {
            latestDelta = historyLog.slice().reverse().find(e => e.delta);
        }

        // Compute trend across the historical window: how many files were added/removed net,
        // and the percent change from the oldest snapshot to today.
        let trendStr = '';
        const tDays = Math.round((tDurSec / 3600) / 24);
        const runtimeBadge = `<span style="color:var(--primary);font-weight:bold;">⏱ ${tHrsStr}${tDays >= 1 ? ` (${tDays}d)` : ''}</span>`;
        if (historyLog && historyLog.length >= 2) {
            const first = historyLog[0]?.total_files || 0;
            const last  = historyLog[historyLog.length - 1]?.total_files || 0;
            const diff = last - first;
            const pct = first > 0 ? ((diff / first) * 100) : 0;
            if (diff !== 0) {
                const arrow = diff > 0 ? '▲' : '▼';
                const color = diff > 0 ? '#34d399' : '#f87171';
                const sign = diff > 0 ? '+' : '−';
                trendStr = `${runtimeBadge} <span style="opacity:0.65;">·</span> <span style="color:${color};font-weight:bold;">${arrow} ${sign}${Math.abs(diff).toLocaleString()}</span> <span style="opacity:0.7;">(${sign}${Math.abs(pct).toFixed(1)}%)</span>`;
            } else {
                trendStr = `${runtimeBadge} <span style="opacity:0.7;">total runtime</span>`;
            }
        }

        if (latestDelta && latestDelta.delta) {
            const d = latestDelta.delta;
            if (d.added > 0 || d.removed > 0) {
                const addStr  = d.added   > 0 ? `<span style="color:#34d399;font-weight:bold;">+${d.added}</span>` : '';
                const remStr  = d.removed > 0 ? `<span style="color:#f87171;font-weight:bold;">−${d.removed}</span>` : '';
                const gbStr   = d.added_gb > 0 ? `<span style="color:#34d399;font-weight:bold;"> +${d.added_gb} GB</span>` : '';
                const rgbStr  = d.removed_gb > 0 ? `<span style="color:#f87171;font-weight:bold;"> −${d.removed_gb} GB</span>` : '';
                const since   = latestDelta.date;
                if(kpiMetaFiles) kpiMetaFiles.innerHTML = `${runtimeBadge} · since ${since}: ${[addStr, remStr].filter(Boolean).join(' / ')}`;
                const kpiMetaStorageDelta = document.getElementById('kpi-meta-storage');
                if(kpiMetaStorageDelta) kpiMetaStorageDelta.innerHTML = `<span style="opacity:0.7;">Avg: ${avgSizeStr}</span>${[gbStr, rgbStr].filter(Boolean).join('')}`;
            } else {
                if(kpiMetaFiles) kpiMetaFiles.innerHTML = trendStr || `${runtimeBadge} <span style="opacity:0.7;">runtime</span>`;
            }
        } else {
            if(kpiMetaFiles) kpiMetaFiles.innerHTML = trendStr || `${runtimeBadge} <span style="opacity:0.7;">runtime</span>`;
        }
        
        updateKPI('storage', formatGb(tBytes), '');
        
        if (!latestDelta || !latestDelta.delta || !(latestDelta.delta.added_gb > 0 || latestDelta.delta.removed_gb > 0)) {
            const kpiMetaStorage = document.getElementById('kpi-meta-storage');
            if(kpiMetaStorage) kpiMetaStorage.innerHTML = `<span style="opacity:0.7;">Avg: ${avgSizeStr} | Max: ${largestName}</span>`;
        }
        
        updateKPI('optimal', cOpt.toLocaleString(), `<span style="opacity:0.7;">${optPct} of selection</span>`);
        updateKPI('transcode', cTrn.toLocaleString(), `<span style="opacity:0.7;">${trnPct} of selection</span>`);
        updateKPI('upgrade', cUpg.toLocaleString(), `<span style="opacity:0.7;">${upgPct} of selection</span>`);

        // Reclaimable storage: ~50% size reduction is typical for bloat-tier files transcoded to HEVC at sane targets
        const bloatBytes = currentData.filter(f => ['6','7'].includes(String(f.NQI)))
                                       .reduce((s, f) => s + (f.size_bytes || 0), 0);
        const reclaimBytes = bloatBytes * 0.5;
        const reclaimMeta = cTrn > 0
            ? `<span style="opacity:0.7;">~50% saving on ${cTrn} bloat files</span>`
            : `<span style="opacity:0.7;">No bloat-tier files</span>`;
        updateKPI('reclaimable', reclaimBytes > 0 ? formatGb(reclaimBytes) : '0 GB', reclaimMeta);
    } catch(e) {
        console.error("KPI update error:", e);
    }

    if (typeof Chart !== 'undefined') {
        try { updateBottomCharts(currentData); } catch(e) { console.error(e); }
        try { updateStorageCharts(currentData); } catch(e) { console.error(e); }
        try { updateBitrateCharts(currentData); } catch(e) { console.error(e); }
    }
    updateTables(currentData);
    
    // Trigger footer glow when filters change
    if (Object.keys(activeFilters).some(k => !k.startsWith('_') && activeFilters[k] !== null)) {
        triggerFooterGlow();
    }
}

// Trapezoid area highlight on the trend chart.
// Non-stacked metrics: the polygon between the two adjacent x-points and the zero baseline.
// Stacked NQI tier: the polygon between this band's top edge and the band below it (or zero) — a true cumulative quad.
// Bars: the bar rectangle itself gets a glow + outline.
const trendAreaPlugin = {
    id: 'trendAreaPlugin',
    afterDraw(chart) {
        if (chart.canvas.id !== 'trendChartHist') return;
        if (!trendHoveredElement) return;

        const { datasetIndex, index } = trendHoveredElement;
        const ds = chart.data.datasets[datasetIndex];
        if (!ds) return;
        const meta = chart.getDatasetMeta(datasetIndex);
        if (!meta || !meta.data || !meta.data[index]) return;

        const ctx = chart.ctx;
        const ca = chart.chartArea;
        const color = ds.borderColor || '#38bdf8';

        // Bar metrics — draw the bar's rectangle with a glow + outline
        if (ds.type === 'bar' || meta.type === 'bar') {
            const bar = meta.data[index];
            const barX = bar.x - (bar.width / 2);
            const barY = Math.min(bar.y, bar.base);
            const barW = bar.width;
            const barH = Math.abs(bar.base - bar.y);

            ctx.save();
            ctx.beginPath();
            ctx.strokeStyle = 'rgba(128,128,128,0.28)';
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 4]);
            ctx.moveTo(bar.x, ca.top);
            ctx.lineTo(bar.x, ca.bottom);
            ctx.stroke();
            ctx.setLineDash([]);

            ctx.fillStyle = color;
            ctx.globalAlpha = 0.18;
            ctx.fillRect(barX, barY, barW, barH);
            ctx.globalAlpha = 1;
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.shadowColor = color;
            ctx.shadowBlur = 8;
            ctx.strokeRect(barX, barY, barW, barH);
            ctx.shadowBlur = 0;
            ctx.restore();
            return;
        }

        // Line metrics — build a trapezoid spanning [index-1 .. index] OR [index .. index+1].
        // Pick the segment that contains the cursor, or default to the right segment if at index 0.
        const cursorX = (window.__trendCursorX != null) ? window.__trendCursorX : meta.data[index].x;
        let i0 = index, i1 = index + 1;
        if (index > 0 && (index === meta.data.length - 1 || cursorX < meta.data[index].x)) {
            i0 = index - 1; i1 = index;
        }
        if (i1 >= meta.data.length) { i1 = meta.data.length - 1; i0 = i1 - 1; }
        if (i0 < 0) i0 = 0;
        const p0 = meta.data[i0];
        const p1 = meta.data[i1];
        if (!p0 || !p1) return;

        // Determine the "bottom" of this dataset's filled area:
        //  - For stacked NQI: top edge of the dataset BELOW (cumulative pixel)
        //  - For non-stacked lines: the zero baseline of this dataset's axis
        const axis = chart.scales[ds.yAxisID] || chart.scales.yTb;
        let baseY0, baseY1;

        if (ds.__metric === 'nqi') {
            // Walk back through NQI datasets to find the one stacked directly below
            let belowIndex = -1;
            for (let j = datasetIndex - 1; j >= 0; j--) {
                const dj = chart.data.datasets[j];
                if (dj.__metric === 'nqi' && chart.isDatasetVisible(j)) { belowIndex = j; break; }
            }
            if (belowIndex >= 0) {
                const belowMeta = chart.getDatasetMeta(belowIndex);
                baseY0 = belowMeta.data[i0]?.y ?? (axis ? axis.getPixelForValue(0) : ca.bottom);
                baseY1 = belowMeta.data[i1]?.y ?? (axis ? axis.getPixelForValue(0) : ca.bottom);
            } else {
                const zero = axis ? axis.getPixelForValue(0) : ca.bottom;
                baseY0 = baseY1 = zero;
            }
        } else {
            const zero = axis ? axis.getPixelForValue(0) : ca.bottom;
            baseY0 = baseY1 = zero;
        }

        ctx.save();

        // Soft vertical crosshair at the hovered x-point
        const hoverPt = meta.data[index];
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(128,128,128,0.28)';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.moveTo(hoverPt.x, ca.top);
        ctx.lineTo(hoverPt.x, ca.bottom);
        ctx.stroke();
        ctx.setLineDash([]);

        // Trapezoid fill
        ctx.beginPath();
        ctx.moveTo(p0.x, p0.y);
        ctx.lineTo(p1.x, p1.y);
        ctx.lineTo(p1.x, baseY1);
        ctx.lineTo(p0.x, baseY0);
        ctx.closePath();
        ctx.fillStyle = color;
        ctx.globalAlpha = 0.22;
        ctx.fill();
        ctx.globalAlpha = 1;

        // Trapezoid outline (top edge + sides) for definition
        ctx.beginPath();
        ctx.moveTo(p0.x, baseY0);
        ctx.lineTo(p0.x, p0.y);
        ctx.lineTo(p1.x, p1.y);
        ctx.lineTo(p1.x, baseY1);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.shadowColor = color;
        ctx.shadowBlur = 6;
        ctx.stroke();
        ctx.shadowBlur = 0;

        // Center dot at the hovered point
        ctx.beginPath();
        ctx.arc(hoverPt.x, hoverPt.y, 5.5, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.95)';
        ctx.lineWidth = 2.5;
        ctx.stroke();

        ctx.restore();
    }
};

// ==============================================================================
// 5. CHART ENGINE & CUSTOM PLUGINS
// ==============================================================================
window.handleHtmlLegendClick = function(e, chartId, datasetIndex) {
    const chart = Chart.getChart(chartId);
    if (!chart) return;
    const labelStr = chart.data.datasets[datasetIndex].label;
    
    const match = labelStr.match(/NQI (\d)/);
    let filterVals = [];
    if (match) { filterVals = [match[1]]; }
    if (filterVals.length > 0) handleTrendFilterClick(filterVals, labelStr);
};

const handleTrendFilterClick = (filterVals, labelStr) => {
    if (!activeFilters.NQI) activeFilters.NQI = [];

    const allExist = filterVals.every(v => activeFilters.NQI.includes(v));

    if (allExist) {
        activeFilters.NQI = activeFilters.NQI.filter(v => !filterVals.includes(v));
    } else {
        filterVals.forEach(v => {
            if (!activeFilters.NQI.includes(v)) activeFilters.NQI.push(v);
        });
    }

    if (activeFilters.NQI.length === 0) {
        activeFilters.NQI = null;
        activeFilters._NQI_label = null;
        showToast('Cleared NQI Filters');
    } else {
        activeFilters._NQI_label = `Selected NQIs (${activeFilters.NQI.length})`;
        showToast(`NQI Filter: ${activeFilters.NQI.join(', ')}`);
    }

    runFilterPipeline();
    syncTopChartVisibility();
};

function getDatasetFromMouseY(e, chart) {
    if (!e || !chart) return null;
    const xElements = chart.getElementsAtEventForMode(e, 'index', { intersect: false }, false);
    if (!xElements.length) return null;
    const index = xElements[0].index;

    // Detect stacked NQI metric (yTb axis with stacking)
    const stackedDatasets = chart.data.datasets
        .map((ds, i) => ({ ds, i }))
        .filter(({ ds }) => ds.__metric === 'nqi' && chart.isDatasetVisible(({ds: ds, i: 0}).i ?? 0));

    // Helper to get the right axis for a dataset
    const yAxisFor = (ds) => chart.scales[ds.yAxisID] || chart.scales.y || chart.scales.yTb;

    // For stacked NQI, find which band the cursor is in based on cumulative pixels
    if (stackedDatasets.length) {
        const axis = yAxisFor(stackedDatasets[0].ds);
        if (!axis || typeof axis.getValueForPixel !== 'function') return null;
        const yValue = axis.getValueForPixel(e.y);
        let cumulativeY = 0;
        for (const { ds, i } of stackedDatasets) {
            if (!chart.isDatasetVisible(i)) continue;
            const val = Number(ds.data[index]) || 0;
            if (val > 0 && yValue >= cumulativeY && yValue <= cumulativeY + val) {
                return { datasetIndex: i, index };
            }
            cumulativeY += val;
        }
    }

    // Fallback — pick the dataset whose rendered point is closest to the cursor Y
    const nearest = chart.getElementsAtEventForMode(e, 'nearest', { intersect: false }, false);
    if (nearest.length > 0) {
        return { datasetIndex: nearest[0].datasetIndex, index: nearest[0].index };
    }
    return null;
}

const chartAreaClickFilter = (e, activeElements, chart) => {
    const resolvedElement = getDatasetFromMouseY(e, chart);
    if (!resolvedElement) {
        return;
    }
    const datasetIndex = resolvedElement.datasetIndex;
    const labelStr = chart.data.datasets[datasetIndex].label;
    
    const match = labelStr.match(/NQI (\d)/);
    if (match) handleTrendFilterClick([match[1]], labelStr);
};

const buildClickHandler = (key) => {
    return function(e, elements, chart) {
        if (!elements || elements.length === 0) {
            return;
        }
        const index = elements[0].index;
        let label = chart.data.labels[index];
        if (key === 'NQI') label = String(label).replace('NQI ', '').replace('Score ', '');

        // "Others" is a rollup of less-common categories. Filter using the underlying values.
        if (String(label) === 'Others') {
            const vals = (chart.__othersValues || []).map(String);
            if (!vals.length) {
                showToast('No "Others" categories to filter by');
                return;
            }
            const currentLabel = activeFilters[`_${key}_label`];
            if (currentLabel === 'Others') {
                activeFilters[key] = null;
                activeFilters[`_${key}_label`] = null;
                showToast('Removed filter: Others');
            } else {
                activeFilters[key] = vals;
                activeFilters[`_${key}_label`] = 'Others';
                showToast(`Applied filter: Others (${vals.length} categories)`);
            }
            runFilterPipeline();
            return;
        }

        if (activeFilters[key] === String(label)) {
            activeFilters[key] = null; 
            activeFilters[`_${key}_label`] = null;
            showToast(`Removed filter: ${label}`);
        } else {
            activeFilters[key] = String(label); 
            activeFilters[`_${key}_label`] = String(label);
            showToast(`Applied filter: ${label}`);
        }
        runFilterPipeline();
    };
};

// ==============================================================================
// Info bar: per-card hover indicator (pill + details)
// ==============================================================================
function pickContrastTextColor(bg) {
    if (!bg || typeof bg !== 'string') return '#ffffff';
    const m = bg.match(/^#([0-9a-fA-F]{6})/);
    if (!m) return '#ffffff';
    const h = m[1];
    const r = parseInt(h.slice(0, 2), 16);
    const g = parseInt(h.slice(2, 4), 16);
    const b = parseInt(h.slice(4, 6), 16);
    const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return lum > 0.65 ? '#0f172a' : '#ffffff';
}

// ==============================================================================
// Notification Rail (bottom gavel) — single channel for chart hover info + toasts
// Toasts take priority and lock the rail until they expire; hover info fills idle time.
// ==============================================================================
const _notifState = {
    toastUntil: 0,        // timestamp; while > now, hover updates are blocked
    lastHover: null,      // {pill, text} so hover restoration after toast works
};

function _renderNotif(pill, text, kind) {
    const rail = document.getElementById('notifRail');
    const pillEl = document.getElementById('notifPill');
    const textEl = document.getElementById('notifText');
    if (!rail || !pillEl || !textEl) return;

    if (!pill && !text) {
        pillEl.innerHTML = '';
        textEl.innerHTML = '';
        textEl.className = 'notif-text';
        rail.classList.remove('has-notif');
        document.body.classList.remove('has-notif-bar');
        return;
    }
    pillEl.innerHTML = pill || '';
    textEl.innerHTML = text || '';
    textEl.className = 'notif-text' + (kind ? ' toast-' + kind : '');
    rail.classList.add('has-notif');
    document.body.classList.add('has-notif-bar');
}

function showNotifHover(pillHtml, textHtml) {
    _notifState.lastHover = { pill: pillHtml, text: textHtml };
    if (Date.now() < _notifState.toastUntil) return; // toast holds the rail
    _renderNotif(pillHtml, textHtml, null);
}

function showNotifToast(message, kind = 'info', durationMs = 2400) {
    _notifState.toastUntil = Date.now() + durationMs;
    _renderNotif('', message, kind);
    setTimeout(() => {
        if (Date.now() >= _notifState.toastUntil - 5) {
            // restore last hover state if any, otherwise idle
            if (_notifState.lastHover) {
                _renderNotif(_notifState.lastHover.pill, _notifState.lastHover.text, null);
            } else {
                _renderNotif(null, null);
            }
        }
    }, durationMs);
}

// Per-card hover bar — sits at the bottom of each chart card, in flow (not floating).
// It's hidden when empty so the card height stays compact, fades in on hover.
function _ensureCardInfoBar(chartId) {
    const canvas = document.getElementById(chartId);
    if (!canvas) return null;
    const card = canvas.closest('.chart-container, .trend-container');
    if (!card) return null;
    let bar = card.querySelector(':scope > .card-info-bar');
    if (!bar) {
        bar = document.createElement('div');
        bar.className = 'card-info-bar';
        card.appendChild(bar);
    }
    return bar;
}

function setInfoBar(chartId, pill, detailsHtml) {
    const el = _ensureCardInfoBar(chartId);
    if (!el) return;

    if (!pill) {
        el.classList.remove('show');
        clearTimeout(el.__hideT);
        el.__hideT = setTimeout(() => {
            if (!el.classList.contains('show')) el.innerHTML = '';
        }, 220);
        return;
    }
    clearTimeout(el.__hideT);
    const fg = pill.fg || pickContrastTextColor(pill.bg);
    const pillHtml = `<span class="info-pill" style="background:${pill.bg};color:${fg};">${pill.label}</span>`;
    el.innerHTML = `${pillHtml}<span class="card-info-bar-text">${detailsHtml || ''}</span>`;
    el.classList.add('show');
}

function describeBottomChartHover(chart, datasetIndex, index) {
    const id = chart.canvas.id;
    const ds = chart.data.datasets[datasetIndex];
    if (!ds) return null;
    const label = chart.data.labels?.[index];
    const val = ds.data[index];
    const muted = (s) => `<span style="color:var(--text-muted);">${s}</span>`;

    if (id === 'nqiChart') {
        const score = String(label).replace('NQI ', '');
        return {
            pill: { label: label, bg: getNqiColor(score), fg: getNqiTextColor(score) },
            details: `<strong>${val.toLocaleString()}</strong> ${muted('files')}`
        };
    }
    if (id === 'resChart') {
        return {
            pill: { label: label, bg: stringToColor(label) },
            details: `<strong>${val.toLocaleString()}</strong> ${muted('files')}`
        };
    }
    if (id === 'resSizeChart') {
        return {
            pill: { label: label, bg: stringToColor(label) },
            details: `<strong>${val}</strong> ${muted('GB')}`
        };
    }
    if (id === 'catSizeChart') {
        const meta = chart.__catMeta?.[label];
        const extra = meta ? ` · ${meta.count.toLocaleString()} files · ${formatRuntimeHours(meta.dur_sec)}` : '';
        return {
            pill: { label: label, bg: getCatColor(label) },
            details: `<strong>${Number(val).toLocaleString()}</strong> ${muted('GB' + extra)}`
        };
    }
    if (id === 'seriesHogChart') {
        const st = chart.__seriesMeta?.[label];
        const extra = st
            ? ` · ${st.count} files · ${formatRuntimeHours(st.dur_sec)}${st.reclaim_bytes > 0 ? ' · ' + formatGb(st.reclaim_bytes) + ' reclaimable' : ''}`
            : '';
        return {
            pill: { label: label, bg: st ? getCatColor(st.cat) : '#38bdf8' },
            details: `<strong>${Number(val).toLocaleString()}</strong> ${muted('GB' + extra)}`
        };
    }
    if (id === 'catEfficiencyChart') {
        const meta = chart.__effMeta?.[label];
        const extra = meta ? ` · ${formatRuntimeHours(meta.dur_sec)} total (${Math.round(meta.gb).toLocaleString()} GB)` : '';
        return {
            pill: { label: label, bg: getCatColor(label) },
            details: `<strong>${val}</strong> ${muted('GB/hr' + extra)}`
        };
    }
    if (id === 'codecChart' || id === 'audioChart' || id === 'hdrChart') {
        const bgArr = ds.backgroundColor;
        const bg = Array.isArray(bgArr) ? bgArr[index] : bgArr;
        const total = ds.data.reduce((a, b) => a + (Number(b) || 0), 0);
        const pct = total > 0 ? ((val / total) * 100).toFixed(1) : '0.0';
        return {
            pill: { label: label, bg: bg },
            details: `<strong>${val.toLocaleString()}</strong> ${muted('files · ' + pct + '%')}`
        };
    }
    if (id === 'bitrateByResChart') {
        return {
            pill: { label: label, bg: stringToColor(label) },
            details: `<strong>${val}</strong> ${muted('Mbps avg')}`
        };
    }
    if (id === 'bitrateHistChart') {
        const bgArr = ds.backgroundColor;
        const bg = Array.isArray(bgArr) ? bgArr[index] : bgArr;
        return {
            pill: { label: `${label} M`, bg: bg },
            details: `<strong>${val.toLocaleString()}</strong> ${muted('files')}`
        };
    }
    if (id === 'bitrateScatterChart') {
        const pt = ds.data[index];
        if (!pt) return null;
        const nqiText = String(pt.nqi).includes('NQI') ? pt.nqi : 'NQI ' + pt.nqi;
        if (pt.__cluster) {
            return {
                pill: { label: `Cluster · ${pt.__count}`, bg: getNqiColor(pt.nqi), fg: getNqiTextColor(pt.nqi) },
                details: `<span style="color:var(--text-main);">${pt.__count} files cluster</span> ${muted('· ~' + pt.x.toFixed(1) + 'M · ~' + pt.y.toFixed(1) + 'GB · click to expand')}`
            };
        }
        return {
            pill: { label: nqiText, bg: getNqiColor(pt.nqi), fg: getNqiTextColor(pt.nqi) },
            details: `<span style="color:var(--text-main);">${pt.file}</span> ${muted('· ' + pt.x + 'M · ' + pt.y + 'GB')}`
        };
    }
    return null;
}

const bottomChartHover = (e, activeElements, chart) => {
    const id = chart.canvas.id;
    if (!activeElements || activeElements.length === 0) {
        setInfoBar(id, null);
        return;
    }
    const { datasetIndex, index } = activeElements[0];
    const info = describeBottomChartHover(chart, datasetIndex, index);
    if (info) setInfoBar(id, info.pill, info.details);
    else setInfoBar(id, null);
};

const pointerHover = (e, activeElements, chart) => {
    const isTrend = chart.canvas.id === 'trendChartHist';
    if (!isTrend) return;

    const evt = e.native || e;
    const cursorX = evt.offsetX ?? evt.layerX;
    const cursorY = evt.offsetY ?? evt.layerY;
    if (cursorX != null) window.__trendCursorX = cursorX;

    let resolvedElement = null;
    if (activeElements && activeElements.length > 0 && cursorX != null && cursorY != null) {
        // Find the segment under the cursor for each visible dataset. For each segment
        // that the cursor X falls inside, compute the Y of the line at cursor X (linear
        // interp between segment endpoints). Pick the dataset whose interpolated Y is
        // closest to cursorY — that's the one the cursor visually sits on.
        let best = null;
        let bestDist = Infinity;
        const datasets = chart.data.datasets;
        for (let di = 0; di < datasets.length; di++) {
            if (!chart.isDatasetVisible(di)) continue;
            const meta = chart.getDatasetMeta(di);
            if (!meta?.data?.length) continue;
            // Find segment [j .. j+1] where pts[j].x <= cursorX <= pts[j+1].x
            const pts = meta.data;
            for (let j = 0; j < pts.length - 1; j++) {
                if (pts[j].x <= cursorX && cursorX <= pts[j + 1].x) {
                    const t = (cursorX - pts[j].x) / Math.max(1, pts[j + 1].x - pts[j].x);
                    const lineY = pts[j].y + t * (pts[j + 1].y - pts[j].y);
                    const dist = Math.abs(lineY - cursorY);
                    if (dist < bestDist) {
                        bestDist = dist;
                        // Snap to whichever endpoint the cursor is closer to (for the dot + tooltip)
                        const snapIdx = (cursorX - pts[j].x) < (pts[j + 1].x - cursorX) ? j : j + 1;
                        best = { datasetIndex: di, index: snapIdx };
                    }
                    break;
                }
            }
        }
        resolvedElement = best || { datasetIndex: activeElements[0].datasetIndex, index: activeElements[0].index };
    } else {
        window.__trendCursorX = null;
    }

    const prev = JSON.stringify(trendHoveredElement);
    trendHoveredElement = resolvedElement || null;
    if (JSON.stringify(trendHoveredElement) !== prev) chart.draw();

    if (resolvedElement) {
        const { datasetIndex, index } = resolvedElement;
        const ds = chart.data.datasets[datasetIndex];
        const dateLabel = chart.data.labels[index];
        const raw = Number(ds.data[index]) || 0;
        const formatted = ds.__format ? ds.__format(raw) : String(raw);
        const bg = ds.borderColor;
        const fg = pickContrastTextColor(bg);
        const muted = (s) => `<span style="color:var(--text-muted);">${s}</span>`;
        setInfoBar('trendChartHist',
            { label: ds.label, bg, fg },
            `<strong>${formatted}</strong> ${muted('· ' + dateLabel)}`
        );
    } else {
        setInfoBar('trendChartHist', null);
    }
};

window.generateHtmlLegend = function(chart) {
    const container = document.getElementById(`legend-${chart.canvas.id}`);
    if (!container) return;
    
    let html = '';
    chart.data.datasets.forEach((ds, i) => {
        const isHidden = !chart.isDatasetVisible(i);
        const match = ds.label.match(/NQI (\d)/);
        const score = match ? match[1] : '';
        const baseColor = getNqiColor(score);
        
        const textColor = isHidden ? 'var(--text-muted)' : getNqiTextColor(score);
        const bgColor = isHidden ? 'transparent' : baseColor;
        const opacity = isHidden ? 0.4 : 1;

        html += `<button class="legend-pill" onclick="handleHtmlLegendClick(event, '${chart.canvas.id}', ${i})" 
            style="background:${bgColor};color:${textColor};opacity:${opacity};">${ds.label}</button>`;
    });
    container.innerHTML = html;
};

// Pill-style legend for category-based charts (codec / audio / hdr)
function generateCategoryLegend(chart, filterKey) {
    const container = document.getElementById(`legend-${chart.canvas.id}`);
    if (!container) return;

    const labels = chart.data.labels || [];
    const ds = chart.data.datasets[0];
    const colors = ds ? ds.backgroundColor : [];
    const active = activeFilters[filterKey];
    const hasFilter = Array.isArray(active) ? active.length > 0 : !!active;
    const isActive = (lbl) => {
        if (!hasFilter) return false;
        if (Array.isArray(active)) return active.includes(String(lbl));
        return String(active) === String(lbl);
    };

    let html = '';
    labels.forEach((lbl, i) => {
        const bg = Array.isArray(colors) ? colors[i] : colors;
        const fg = pickContrastTextColor(bg);
        const dimmed = hasFilter && !isActive(lbl);
        const opacity = dimmed ? 0.35 : 1;
        const safeLbl = String(lbl).replace(/'/g, "\\'");
        html += `<button class="legend-pill" onclick="handleCategoryLegendClick('${filterKey}','${safeLbl}')"
            style="background:${bg};color:${fg};opacity:${opacity};">${lbl}</button>`;
    });
    container.innerHTML = html;
}

// Map filterKey → chart instance (so legend handler can read __othersValues)
function chartForFilterKey(filterKey) {
    if (filterKey === 'VIDEO' && typeof bCodecChart !== 'undefined') return bCodecChart;
    if (filterKey === 'AUDIO_BASE' && typeof bAudioChart !== 'undefined') return bAudioChart;
    if (filterKey === 'HDR' && typeof bHdrChart !== 'undefined') return bHdrChart;
    return null;
}

window.handleCategoryLegendClick = function(filterKey, label) {
    // "Others" is a rollup — apply it as the array of underlying values
    if (String(label) === 'Others') {
        const chart = chartForFilterKey(filterKey);
        const vals = (chart && chart.__othersValues || []).map(String);
        if (!vals.length) {
            showToast('No "Others" categories to filter by');
            return;
        }
        const currentLabel = activeFilters[`_${filterKey}_label`];
        if (currentLabel === 'Others') {
            activeFilters[filterKey] = null;
            activeFilters[`_${filterKey}_label`] = null;
            showToast('Removed: Others');
        } else {
            activeFilters[filterKey] = vals;
            activeFilters[`_${filterKey}_label`] = 'Others';
            showToast(`Added: Others (${vals.length} categories)`);
        }
        runFilterPipeline();
        syncCategoryLegends();
        return;
    }

    if (!Array.isArray(activeFilters[filterKey])) {
        activeFilters[filterKey] = activeFilters[filterKey] ? [String(activeFilters[filterKey])] : [];
    }
    const idx = activeFilters[filterKey].indexOf(String(label));
    if (idx > -1) {
        activeFilters[filterKey].splice(idx, 1);
        showToast(`Removed: ${label}`);
    } else {
        activeFilters[filterKey].push(String(label));
        showToast(`Added: ${label}`);
    }
    if (activeFilters[filterKey].length === 0) {
        activeFilters[filterKey] = null;
        activeFilters[`_${filterKey}_label`] = null;
    } else {
        activeFilters[`_${filterKey}_label`] = activeFilters[filterKey].join(', ');
    }
    runFilterPipeline();
    syncCategoryLegends();
};

function syncCategoryLegends() {
    if (typeof bCodecChart !== 'undefined' && bCodecChart) generateCategoryLegend(bCodecChart, 'VIDEO');
    if (typeof bAudioChart !== 'undefined' && bAudioChart) generateCategoryLegend(bAudioChart, 'AUDIO_BASE');
    if (typeof bHdrChart   !== 'undefined' && bHdrChart)   generateCategoryLegend(bHdrChart,   'HDR');
}

function syncTopChartVisibility() {
    if (!chartHist) return;
    chartHist.data.datasets.forEach((ds, i) => {
        if (!activeFilters.NQI || activeFilters.NQI.length === 0) {
            chartHist.setDatasetVisibility(i, true);
        } else {
            const m = ds.label.match(/NQI (\d)/);
            let shouldShow = false;
            if (m) { shouldShow = activeFilters.NQI.includes(m[1]); }
            chartHist.setDatasetVisibility(i, shouldShow);
        }
    });
    chartHist.update();
    generateHtmlLegend(chartHist);
}

// ==============================================================================
// 6. CHART INITIALIZERS
// Cluster scatter points into "fog bubbles" when there are too many to plot individually.
// Grid-bins points by (x, y) so dense areas become big translucent bubbles, sparse areas
// keep their individual dots. Returns a flat array suitable for Chart.js scatter dataset.
function _clusterScatterPoints(rawPts, threshold = 50, gridXBins = 16, gridYBins = 12) {
    if (!rawPts || rawPts.length <= threshold) return rawPts.map(p => ({ ...p, __cluster: false }));

    // Find bounds
    let xmin = Infinity, xmax = -Infinity, ymin = Infinity, ymax = -Infinity;
    for (const p of rawPts) {
        if (p.x < xmin) xmin = p.x; if (p.x > xmax) xmax = p.x;
        if (p.y < ymin) ymin = p.y; if (p.y > ymax) ymax = p.y;
    }
    const xRange = Math.max(0.0001, xmax - xmin);
    const yRange = Math.max(0.0001, ymax - ymin);
    const xStep = xRange / gridXBins;
    const yStep = yRange / gridYBins;

    // Bin
    const bins = new Map();
    for (const p of rawPts) {
        const xi = Math.min(gridXBins - 1, Math.floor((p.x - xmin) / xStep));
        const yi = Math.min(gridYBins - 1, Math.floor((p.y - ymin) / yStep));
        const key = xi + ':' + yi;
        if (!bins.has(key)) bins.set(key, []);
        bins.get(key).push(p);
    }

    // For each bin: 1 point → keep as-is; 2-3 points → keep individual; 4+ → cluster bubble
    const out = [];
    for (const [, pts] of bins) {
        if (pts.length <= 3) {
            for (const p of pts) out.push({ ...p, __cluster: false });
            continue;
        }
        // Cluster: average position, count by NQI for color
        let sx = 0, sy = 0;
        const nqiCounts = {};
        for (const p of pts) {
            sx += p.x; sy += p.y;
            nqiCounts[p.nqi] = (nqiCounts[p.nqi] || 0) + 1;
        }
        const dominantNqi = Object.entries(nqiCounts).sort((a, b) => b[1] - a[1])[0][0];
        out.push({
            x: sx / pts.length,
            y: sy / pts.length,
            __cluster: true,
            __count: pts.length,
            __ids: pts.map(p => p.id),
            nqi: dominantNqi,
            file: `${pts.length} files in this region`
        });
    }
    return out;
}

function updateBitrateCharts(data) {
    if (!bBitrateScatterChart || !bBitrateByResChart || !bBitrateHistChart) return;

    const rawScatterPts = data
        .map(f => {
            const mbps = parseMbps(f.BITRATE);
            return mbps !== null ? { x: mbps, y: parseFloat((f.size_bytes / (1024**3)).toFixed(2)), id: f.id, nqi: f.NQI, file: f.file } : null;
        })
        .filter(Boolean);

    // Aggressive bucketing: cluster when count > 50 to avoid plotting hundreds of individual dots
    const scatterPts = _clusterScatterPoints(rawScatterPts, 50);

    const radii = scatterPts.map(p => {
        if (!p.__cluster) return 4;
        return Math.min(34, 6 + Math.sqrt(p.__count) * 2.2);
    });
    const bgs = scatterPts.map(p => {
        const base = getNqiColor(p.nqi);
        return p.__cluster ? base + '33' : base + '88';
    });
    const borders = scatterPts.map(p => getNqiColor(p.nqi) + (p.__cluster ? 'bb' : 'ff'));

    bBitrateScatterChart.data.datasets[0].data = scatterPts;
    bBitrateScatterChart.data.datasets[0].backgroundColor = bgs;
    bBitrateScatterChart.data.datasets[0].borderColor = borders;
    bBitrateScatterChart.data.datasets[0].pointRadius = radii;
    bBitrateScatterChart.data.datasets[0].pointHoverRadius = radii.map(r => r + 3);
    bBitrateScatterChart.data.datasets[0].borderWidth = scatterPts.map(p => p.__cluster ? 2 : 1);

    bBitrateScatterChart.update();

    const resOrder = ['4K', '1080p', '720p', '480p'];
    const resBuckets = {};
    data.forEach(f => {
        const mbps = parseMbps(f.BITRATE);
        if (mbps === null) return;
        const r = f.RES || 'Unknown';
        if (!resBuckets[r]) resBuckets[r] = [];
        resBuckets[r].push(mbps);
    });
    const resLabels = resOrder.filter(r => resBuckets[r]).concat(Object.keys(resBuckets).filter(r => !resOrder.includes(r)));
    const resAvgs = resLabels.map(r => parseFloat((resBuckets[r].reduce((a,b)=>a+b,0)/resBuckets[r].length).toFixed(1)));
    bBitrateByResChart.data.labels = resLabels;
    bBitrateByResChart.data.datasets[0].data = resAvgs;
    bBitrateByResChart.data.datasets[0].backgroundColor = resLabels.map(stringToColor);
    bBitrateByResChart.update();

    const bucketSize = 5; 
    const buckets = {};
    data.forEach(f => {
        const mbps = parseMbps(f.BITRATE);
        if (mbps === null) return;
        const bucket = Math.floor(mbps / bucketSize) * bucketSize;
        const label = `${bucket}–${bucket + bucketSize}`;
        buckets[label] = (buckets[label] || 0) + 1;
    });
    const histEntries = Object.entries(buckets).sort((a,b) => parseInt(a[0]) - parseInt(b[0]));
    const histLabels = histEntries.map(e => e[0]);
    const histCounts = histEntries.map(e => e[1]);
    bBitrateHistChart.data.labels = histLabels;
    bBitrateHistChart.data.datasets[0].data = histCounts;
    bBitrateHistChart.data.datasets[0].backgroundColor = histLabels.map(stringToColor);
    bBitrateHistChart.update();
}

function updateStorageCharts(data) {
    if (!bCatSizeChart || !bSeriesHogChart || !bCatEfficiencyChart) return;

    const catMap = new Map();
    for (const f of data) {
        const cat = f.CAT || 'Other';
        let st = catMap.get(cat);
        if (!st) {
            st = { cat, count: 0, bytes: 0, dur_sec: 0 };
            catMap.set(cat, st);
        }
        st.count += 1;
        st.bytes += (f.size_bytes || 0);
        st.dur_sec += (f.DUR_SEC || 0);
    }

    const catEntries = [...catMap.values()]
        .filter(c => c.bytes > 0)
        .sort((a, b) => b.bytes - a.bytes);

    const catLabels = catEntries.map(c => c.cat);
    const catSizesGb = catEntries.map(c => parseFloat((c.bytes / (1024 ** 3)).toFixed(1)));
    const catMetaObj = {};
    catEntries.forEach(c => {
        c.gb = c.bytes / (1024 ** 3);
        c.gb_hr = c.dur_sec > 360 ? (c.gb / (c.dur_sec / 3600)) : 0;
        catMetaObj[c.cat] = c;
    });

    bCatSizeChart.data.labels = catLabels;
    bCatSizeChart.data.datasets[0].data = catSizesGb;
    bCatSizeChart.data.datasets[0].backgroundColor = catLabels.map(getCatColor);
    bCatSizeChart.__catMeta = catMetaObj;
    bCatSizeChart.update();

    const seriesAll = aggregateSeriesData(data).sort((a, b) => b.bytes - a.bytes);
    const topSeries = seriesAll.slice(0, 10);
    const seriesLabels = topSeries.map(s => s.show);
    const seriesSizesGb = topSeries.map(s => parseFloat((s.bytes / (1024 ** 3)).toFixed(1)));
    const seriesMetaObj = {};
    topSeries.forEach(s => { seriesMetaObj[s.show] = s; });

    bSeriesHogChart.data.labels = seriesLabels;
    bSeriesHogChart.data.datasets[0].data = seriesSizesGb;
    bSeriesHogChart.data.datasets[0].backgroundColor = topSeries.map(s => getCatColor(s.cat));
    bSeriesHogChart.__seriesMeta = seriesMetaObj;
    bSeriesHogChart.update();

    const effEntries = catEntries
        .filter(c => c.dur_sec >= 1800 && c.cat !== 'Temp' && c.cat !== 'Mnt')
        .sort((a, b) => b.gb_hr - a.gb_hr);
    const effLabels = effEntries.map(c => c.cat);
    const effVals = effEntries.map(c => parseFloat(c.gb_hr.toFixed(2)));

    bCatEfficiencyChart.data.labels = effLabels;
    bCatEfficiencyChart.data.datasets[0].data = effVals;
    bCatEfficiencyChart.data.datasets[0].backgroundColor = effLabels.map(getCatColor);
    bCatEfficiencyChart.__effMeta = catMetaObj;
    bCatEfficiencyChart.update();
}

function updateBottomCharts(data) {
    if (!bResChart || !bResSizeChart || !bNqiChart || !bCodecChart || !bAudioChart || !bHdrChart) return;

    const resAgg = aggData(data, 'RES', ['4K', '1080p', '720p', '480p']);
    bResChart.data.labels = resAgg.labels;
    bResChart.data.datasets[0].data = resAgg.dataCounts;
    bResChart.data.datasets[0].backgroundColor = resAgg.labels.map(stringToColor);
    bResChart.update();

    bResSizeChart.data.labels = resAgg.labels;
    bResSizeChart.data.datasets[0].data = resAgg.dataSizes;
    bResSizeChart.data.datasets[0].backgroundColor = resAgg.labels.map(stringToColor);
    bResSizeChart.update();

    const nqiAgg = aggData(data, 'NQI', ['NQI 7', 'NQI 6', 'NQI 5', 'NQI 4', 'NQI 3', 'NQI 2', 'NQI 1']);
    bNqiChart.data.labels = nqiAgg.labels;
    bNqiChart.data.datasets[0].data = nqiAgg.dataCounts;
    bNqiChart.data.datasets[0].backgroundColor = nqiAgg.labels.map(l => getNqiColor(l));
    bNqiChart.update();

    const vidAgg = aggData(data, 'VIDEO', null, 5);
    bCodecChart.data.labels = vidAgg.labels;
    bCodecChart.data.datasets[0].data = vidAgg.dataCounts;
    bCodecChart.data.datasets[0].backgroundColor = vidAgg.labels.map(stringToColor);
    bCodecChart.__othersValues = vidAgg.othersValues || [];
    bCodecChart.update();

    const audAgg = aggData(data, 'AUDIO_BASE', null, 5);
    bAudioChart.data.labels = audAgg.labels;
    bAudioChart.data.datasets[0].data = audAgg.dataCounts;
    bAudioChart.data.datasets[0].backgroundColor = audAgg.labels.map(stringToColor);
    bAudioChart.__othersValues = audAgg.othersValues || [];
    bAudioChart.update();

    const hdrAgg = aggData(data, 'HDR', null, 5);
    bHdrChart.data.labels = hdrAgg.labels;
    bHdrChart.data.datasets[0].data = hdrAgg.dataCounts;
    bHdrChart.data.datasets[0].backgroundColor = hdrAgg.labels.map(stringToColor);
    bHdrChart.__othersValues = hdrAgg.othersValues || [];
    bHdrChart.update();

    // Refresh HTML category legends so colors/data match the latest filtered data
    syncCategoryLegends();
}

function initSparkline() {
    if (typeof Chart === 'undefined' || !historyLog || historyLog.length === 0) return;

    const dates = historyLog.map(h => h.date);

    const totalFiles = historyLog.map(h => h.total_files || 0);
    const totalTb    = historyLog.map(h => {
        const c = h.nqi?.sizes_gb || {};
        const sum = ['1','2','3','4','5','6','7'].reduce((s, k) => s + (c[k] || 0), 0);
        return +(sum / 1024).toFixed(2);
    });
    const optimalCt  = historyLog.map(h => {
        const c = h.nqi?.counts || {};
        return (c['4'] || 0) + (c['5'] || 0);
    });
    const transcodeCt = historyLog.map(h => {
        const c = h.nqi?.counts || {};
        return (c['6'] || 0) + (c['7'] || 0);
    });
    const upgradeCt = historyLog.map(h => {
        const c = h.nqi?.counts || {};
        return (c['1'] || 0) + (c['2'] || 0);
    });

    const series = [
        { id: 'miniSparkline-files',     data: totalFiles,  color: '#38bdf8' },
        { id: 'miniSparkline-storage',   data: totalTb,     color: '#38bdf8' },
        { id: 'miniSparkline-optimal',   data: optimalCt,   color: '#34d399' },
        { id: 'miniSparkline-transcode', data: transcodeCt, color: '#d946ef' },
        { id: 'miniSparkline-upgrade',   data: upgradeCt,   color: '#f97316' }
    ];

    const hexToRgba = (hex, a) => {
        const r = parseInt(hex.slice(1,3), 16);
        const g = parseInt(hex.slice(3,5), 16);
        const b = parseInt(hex.slice(5,7), 16);
        return `rgba(${r},${g},${b},${a})`;
    };

    series.forEach(s => {
        const ctx = document.getElementById(s.id);
        if (!ctx) return;
        const existing = Chart.getChart(ctx);
        if (existing) existing.destroy();

        const minVal = Math.min(...s.data);
        const maxVal = Math.max(...s.data);
        const range = Math.max(1, maxVal - minVal);
        const yMin = Math.max(0, minVal - range * 0.15);
        const yMax = maxVal + range * 0.15;

        new Chart(ctx, {
            type: 'line',
            data: {
                labels: dates,
                datasets: [{
                    data: s.data,
                    borderColor: s.color,
                    backgroundColor: hexToRgba(s.color, 0.22),
                    fill: 'origin',
                    borderWidth: 2,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
                scales: {
                    x: { display: false },
                    y: { display: false, min: yMin, max: yMax }
                },
                layout: { padding: 0 },
                animation: { duration: 1800, easing: 'easeOutQuart' },
                events: []
            }
        });
    });
}

function initBottomCharts() {
    if (typeof Chart === 'undefined') return;
    
    const tooltipOff = { enabled: false };
    const minimalLegendPie = { display: false }; // replaced by HTML pill legend
    const chartPadding = { padding: { left: 0, right: 32, top: 16, bottom: 8 } };
    // Donut/pie charts have no axes — heavier bottom padding visually centers them in the card
    // (compensates for the header + legend stack above the chart-wrapper)
    const donutPadding = { padding: { left: 8, right: 8, top: 8, bottom: 50 } };

    try {
        const ctxNqi = document.getElementById('nqiChart');
        if(ctxNqi) {
            bNqiChart = new Chart(ctxNqi, {
                type: 'bar', data: { labels: [], datasets: [{ label: 'Files', data: [], backgroundColor: [], borderRadius: 4 }] },
                options: { 
                    maintainAspectRatio: false, responsive: true, layout: chartPadding,
                    plugins: { tooltip: tooltipOff, title: { display: false }, subtitle: { display: false }, legend: {display: false} }, 
                    scales: { y: { beginAtZero: true } }, 
                    onClick: buildClickHandler('NQI'),
                    onHover: bottomChartHover
                }
            });
        }
    } catch(e) { console.error(e); }

    try {
        const ctxRes = document.getElementById('resChart');
        if(ctxRes) {
            bResChart = new Chart(ctxRes, {
                type: 'bar', data: { labels: [], datasets: [{ label: 'Files', data: [], backgroundColor: NNUVA_PALETTE, borderRadius: 4 }] },
                options: { 
                    maintainAspectRatio: false, responsive: true, layout: chartPadding,
                    plugins: { tooltip: tooltipOff, title: { display: false }, subtitle: { display: false }, legend: {display: false} }, 
                    scales: { y: { beginAtZero: true } }, 
                    onClick: buildClickHandler('RES'),
                    onHover: bottomChartHover
                }
            });
        }
    } catch(e) { console.error(e); }

    try {
        const ctxResSize = document.getElementById('resSizeChart');
        if(ctxResSize) {
            bResSizeChart = new Chart(ctxResSize, {
                type: 'bar', data: { labels: [], datasets: [{ label: 'Storage', data: [], backgroundColor: NNUVA_PALETTE, borderRadius: 4 }] },
                options: { 
                    maintainAspectRatio: false, responsive: true, layout: chartPadding,
                    plugins: { tooltip: tooltipOff, title: { display: false }, subtitle: { display: false }, legend: {display: false} }, 
                    scales: { y: { beginAtZero: true } }, 
                    onClick: buildClickHandler('RES'),
                    onHover: bottomChartHover
                }
            });
        }
    } catch(e) { console.error(e); }

    try {
        const ctxCatSize = document.getElementById('catSizeChart');
        if(ctxCatSize) {
            bCatSizeChart = new Chart(ctxCatSize, {
                type: 'bar', data: { labels: [], datasets: [{ label: 'Storage (GB)', data: [], backgroundColor: NNUVA_PALETTE, borderRadius: 4 }] },
                options: {
                    maintainAspectRatio: false, responsive: true, layout: chartPadding,
                    plugins: { tooltip: tooltipOff, title: { display: false }, subtitle: { display: false }, legend: {display: false} },
                    scales: { y: { beginAtZero: true, ticks: { callback: v => v.toLocaleString() + ' GB' } } },
                    onClick: buildClickHandler('CAT'),
                    onHover: bottomChartHover
                }
            });
        }
    } catch(e) { console.error(e); }

    try {
        const ctxSeriesHog = document.getElementById('seriesHogChart');
        if(ctxSeriesHog) {
            bSeriesHogChart = new Chart(ctxSeriesHog, {
                type: 'bar', data: { labels: [], datasets: [{ label: 'Total GB', data: [], backgroundColor: NNUVA_PALETTE, borderRadius: 4 }] },
                options: {
                    indexAxis: 'y',
                    maintainAspectRatio: false, responsive: true, layout: chartPadding,
                    plugins: { tooltip: tooltipOff, title: { display: false }, subtitle: { display: false }, legend: {display: false} },
                    scales: { x: { beginAtZero: true, ticks: { callback: v => v + ' GB' } } },
                    onClick: buildClickHandler('SHOW'),
                    onHover: bottomChartHover
                }
            });
        }
    } catch(e) { console.error(e); }

    try {
        const ctxCatEff = document.getElementById('catEfficiencyChart');
        if(ctxCatEff) {
            bCatEfficiencyChart = new Chart(ctxCatEff, {
                type: 'bar', data: { labels: [], datasets: [{ label: 'GB / Hour', data: [], backgroundColor: NNUVA_PALETTE, borderRadius: 4 }] },
                options: {
                    maintainAspectRatio: false, responsive: true, layout: chartPadding,
                    plugins: { tooltip: tooltipOff, title: { display: false }, subtitle: { display: false }, legend: {display: false} },
                    scales: { y: { beginAtZero: true, ticks: { callback: v => v + ' GB/h' } } },
                    onClick: buildClickHandler('CAT'),
                    onHover: bottomChartHover
                }
            });
        }
    } catch(e) { console.error(e); }

    try {
        const ctxCodec = document.getElementById('codecChart');
        if(ctxCodec) {
            bCodecChart = new Chart(ctxCodec, {
                type: 'doughnut', data: { labels: [], datasets: [{ label: 'Files', data: [], backgroundColor: NNUVA_PALETTE, borderWidth: 0 }] },
                options: { 
                    maintainAspectRatio: false, responsive: true, layout: donutPadding,
                    plugins: { tooltip: tooltipOff, title: { display: false }, subtitle: { display: false }, legend: minimalLegendPie }, 
                    cutout: '65%', 
                    onClick: buildClickHandler('VIDEO'),
                    onHover: bottomChartHover
                }
            });
        }
    } catch(e) { console.error(e); }

    try {
        const ctxAudio = document.getElementById('audioChart');
        if(ctxAudio) {
            bAudioChart = new Chart(ctxAudio, {
                type: 'doughnut', data: { labels: [], datasets: [{ label: 'Files', data: [], backgroundColor: NNUVA_PALETTE, borderWidth: 0 }] },
                options: { 
                    maintainAspectRatio: false, responsive: true, layout: donutPadding,
                    plugins: { tooltip: tooltipOff, title: { display: false }, subtitle: { display: false }, legend: minimalLegendPie }, 
                    cutout: '65%', 
                    onClick: buildClickHandler('AUDIO_BASE'),
                    onHover: bottomChartHover
                }
            });
        }
    } catch(e) { console.error(e); }

    try {
        const ctxHdr = document.getElementById('hdrChart');
        if(ctxHdr) {
            bHdrChart = new Chart(ctxHdr, {
                type: 'doughnut', data: { labels: [], datasets: [{ label: 'Files', data: [], backgroundColor: NNUVA_PALETTE, borderWidth: 0 }] },
                options: { 
                    maintainAspectRatio: false, responsive: true, layout: donutPadding,
                    plugins: { tooltip: tooltipOff, title: { display: false }, subtitle: { display: false }, legend: minimalLegendPie }, 
                    cutout: '65%', 
                    onClick: buildClickHandler('HDR'),
                    onHover: bottomChartHover
                }
            });
        }
    } catch(e) { console.error(e); }

    try {
        const ctxScatter = document.getElementById('bitrateScatterChart');
        if(ctxScatter) {
            bBitrateScatterChart = new Chart(ctxScatter, {
                type: 'scatter',
                data: { datasets: [{ label: 'Media Files', data: [], backgroundColor: [], borderColor: [], pointRadius: 4, pointHoverRadius: 8, hitRadius: 10, borderWidth: 1 }] },
                options: {
                    maintainAspectRatio: false, responsive: true, layout: chartPadding,
                    plugins: { tooltip: tooltipOff, title: { display: false }, subtitle: { display: false }, legend: {display: false} },
                    scales: { x: { title: {display: true, text: 'Bitrate (Mbps)'} }, y: { title: {display: true, text: 'File Size (GB)'} } },
                    onHover: bottomChartHover,
                    onClick: (e, elements, chart) => {
                        if (!elements.length) return;
                        const pt = chart.data.datasets[0].data[elements[0].index];
                        if (!pt) return;
                        if (pt.__cluster) {
                            // Apply a range filter that zooms to this cluster's region — clustered points
                            // will then split into individuals because the filtered count drops below the threshold.
                            const xs = chart.scales.x;
                            const ys = chart.scales.y;
                            const xRange = (xs.max - xs.min) * 0.1; // ±10% window around cluster center
                            const yRange = (ys.max - ys.min) * 0.15;
                            activeFilters['BITRATE_RANGE'] = [pt.x - xRange, pt.x + xRange];
                            activeFilters['SIZE_RANGE_GB'] = [Math.max(0, pt.y - yRange), pt.y + yRange];
                            activeFilters['_BITRATE_RANGE_label'] = `${pt.x.toFixed(1)} ± ${xRange.toFixed(1)} Mbps`;
                            activeFilters['_SIZE_RANGE_GB_label'] = `~${pt.y.toFixed(1)} GB`;
                            showToast(`Zoomed into cluster: ${pt.__count} files`, 'info');
                            runFilterPipeline();
                        } else if (pt.id !== undefined) {
                            window.openFileModal(pt.id);
                        }
                    }
                }
            });
        }
    } catch(e) { console.error(e); }

    try {
        const ctxByRes = document.getElementById('bitrateByResChart');
        if(ctxByRes) {
            bBitrateByResChart = new Chart(ctxByRes, {
                type: 'bar',
                data: { labels: [], datasets: [{ label: 'Avg Bitrate (Mbps)', data: [], backgroundColor: [], borderWidth: 0, borderRadius: 4 }] },
                options: {
                    maintainAspectRatio: false, responsive: true, layout: chartPadding,
                    plugins: { tooltip: tooltipOff, title: { display: false }, subtitle: { display: false }, legend: {display: false} },
                    scales: { y: { ticks: { callback: v => v + ' Mbps' } } },
                    onHover: bottomChartHover,
                    onClick: (e, elements, chart) => {
                        if (elements.length > 0) {
                            const index = elements[0].index;
                            let label = chart.data.labels[index];
                            if (activeFilters['RES'] === String(label)) {
                                activeFilters['RES'] = null;
                                activeFilters['_RES_label'] = null;
                            } else {
                                activeFilters['RES'] = String(label);
                                activeFilters['_RES_label'] = String(label);
                            }
                            runFilterPipeline();
                        }
                    }
                }
            });
        }
    } catch(e) { console.error(e); }

    try {
        const ctxHist = document.getElementById('bitrateHistChart');
        if(ctxHist) {
            bBitrateHistChart = new Chart(ctxHist, {
                type: 'bar',
                data: { labels: [], datasets: [{ label: 'File Count', data: [], backgroundColor: [], borderWidth: 0, borderRadius: 4 }] },
                options: {
                    maintainAspectRatio: false, responsive: true, layout: chartPadding,
                    plugins: { tooltip: tooltipOff, title: { display: false }, subtitle: { display: false }, legend: {display: false} },
                    scales: { x: { title: {display: true, text: 'Mbps range'} }, y: { ticks: { callback: v => v + ' files' } } },
                    onHover: bottomChartHover,
                    onClick: (e, elements, chart) => {
                        if (!elements.length) return;
                        const index = elements[0].index;
                        const label = chart.data.labels[index];
                        if (!label) return;
                        // Labels look like "0–10" (en-dash). Parse both endpoints.
                        const parts = String(label).split(/[–\-]/).map(s => parseFloat(s.trim()));
                        if (parts.length !== 2 || parts.some(isNaN)) return;
                        const [lo, hi] = parts;
                        const cur = activeFilters['BITRATE_RANGE'];
                        // Toggle: if same range already applied, clear it
                        if (Array.isArray(cur) && cur[0] === lo && cur[1] === hi) {
                            activeFilters['BITRATE_RANGE'] = null;
                            activeFilters['_BITRATE_RANGE_label'] = null;
                        } else {
                            activeFilters['BITRATE_RANGE'] = [lo, hi];
                            activeFilters['_BITRATE_RANGE_label'] = `${lo}–${hi} Mbps`;
                        }
                        runFilterPipeline();
                    }
                }
            });
        }
    } catch(e) { console.error(e); }
}

function initTopCharts() {
    if (typeof Chart === 'undefined') return;

    const tooltipOff = { enabled: false };
    const histDates = historyLog.map(h => h.date);

    // ===== Per-metric data series =====
    const getNqiTb = (entry, score) => { const gb = entry.nqi?.sizes_gb?.[score] || 0; return +(gb / 1024).toFixed(2); };

    // Total storage (TB) per snapshot
    const totalStorageTb = historyLog.map(e => {
        const total = ['1','2','3','4','5','6','7'].reduce((s, k) => s + (e.nqi?.sizes_gb?.[k] || 0), 0);
        return +(total / 1024).toFixed(2);
    });
    const totalFiles = historyLog.map(e => e.total_files || 0);

    // Average NQI %: weight nqi tier counts (NQI 4 = 100% reference)
    const avgNqi = historyLog.map(e => {
        const counts = e.nqi?.counts || {};
        let sumPct = 0, sumN = 0;
        for (let s = 1; s <= 7; s++) {
            const n = counts[String(s)] || 0;
            // Score 4 ≈ 100%. 1 = ~30%, 2 = 60%, 3 = 85%, 5 = 105%, 6 = 130%, 7 = 200%
            const ratioMap = { 1: 30, 2: 60, 3: 85, 4: 100, 5: 105, 6: 130, 7: 200 };
            sumPct += (ratioMap[s] || 100) * n;
            sumN += n;
        }
        return sumN ? +(sumPct / sumN).toFixed(1) : 0;
    });

    // Library updates (added & removed counts)
    const updatesAdded = historyLog.map(e => e.delta?.added || 0);
    const updatesRemoved = historyLog.map(e => -(e.delta?.removed || 0)); // negative so they bar downward

    // NQI tier breakdown TB per tier (stacked)
    const nqiTiers = ['1','2','3','4','5','6','7'].map(score => ({
        label: 'NQI ' + score,
        score,
        data: historyLog.map(e => getNqiTb(e, score))
    }));
    const NQI_BG_COLORS = {
        '1': 'rgba(248, 113, 113, 0.55)', '2': 'rgba(251, 146, 60, 0.55)',
        '3': 'rgba(251, 191, 36, 0.55)', '4': 'rgba(52, 211, 153, 0.55)',
        '5': 'rgba(34, 211, 238, 0.55)', '6': 'rgba(217, 70, 239, 0.45)',
        '7': 'rgba(203, 213, 225, 0.7)'
    };
    const NQI_BORDER = {
        '1': '#f87171', '2': '#fb923c', '3': '#fbbf24', '4': '#34d399',
        '5': '#22d3ee', '6': '#d946ef', '7': '#cbd5e1'
    };

    // ===== Metric registry — each defines how to add itself to the chart =====
    window.__trendMetricBuilders = {
        storage: () => [{
            label: 'Total Storage',
            data: totalStorageTb,
            backgroundColor: 'rgba(56, 189, 248, 0.08)',
            borderColor: '#38bdf8',
            borderWidth: 2.5,
            pointRadius: 0,
            pointHoverRadius: 0,
            fill: 'origin',
            tension: 0.25,
            yAxisID: 'yTb',
            __unit: 'TB',
            __format: v => v + ' TB'
        }],
        files: () => [{
            label: 'File Count',
            data: totalFiles,
            backgroundColor: 'rgba(168, 85, 247, 0.10)',
            borderColor: '#a855f7',
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 0,
            fill: false,
            tension: 0.25,
            yAxisID: 'yFiles',
            __unit: 'files',
            __format: v => v.toLocaleString() + ' files'
        }],
        quality: () => [{
            label: 'Avg NQI %',
            data: avgNqi,
            backgroundColor: 'rgba(52, 211, 153, 0.10)',
            borderColor: '#34d399',
            borderWidth: 2,
            borderDash: [5, 4],
            pointRadius: 0,
            pointHoverRadius: 0,
            fill: false,
            tension: 0.25,
            yAxisID: 'yPct',
            __unit: '%',
            __format: v => v + '%'
        }],
        updates: () => [
            {
                label: 'Added',
                data: updatesAdded,
                backgroundColor: 'rgba(52, 211, 153, 0.65)',
                borderColor: '#34d399',
                borderWidth: 0,
                type: 'bar',
                yAxisID: 'yFiles',
                __unit: 'files',
                __format: v => '+' + v + ' files'
            },
            {
                label: 'Removed',
                data: updatesRemoved,
                backgroundColor: 'rgba(248, 113, 113, 0.65)',
                borderColor: '#f87171',
                borderWidth: 0,
                type: 'bar',
                yAxisID: 'yFiles',
                __unit: 'files',
                __format: v => v + ' files'  // already negative
            }
        ],
        added: () => [{
            label: 'Added',
            data: updatesAdded,
            backgroundColor: 'rgba(52, 211, 153, 0.65)',
            borderColor: '#34d399',
            borderWidth: 0,
            type: 'bar',
            yAxisID: 'yFiles',
            __unit: 'files',
            __format: v => '+' + v + ' files'
        }],
        removed: () => [{
            label: 'Removed',
            data: updatesRemoved.map(v => Math.abs(v)),  // show as positive bars now that it's its own metric
            backgroundColor: 'rgba(248, 113, 113, 0.65)',
            borderColor: '#f87171',
            borderWidth: 0,
            type: 'bar',
            yAxisID: 'yFiles',
            __unit: 'files',
            __format: v => '−' + v + ' files'
        }],
        nqi: () => nqiTiers.map(t => ({
            label: t.label,
            data: t.data,
            backgroundColor: NQI_BG_COLORS[t.score],
            borderColor: NQI_BORDER[t.score],
            borderWidth: 1.5,
            pointRadius: 0,
            pointHoverRadius: 0,
            fill: true,
            tension: 0.2,
            yAxisID: 'yTb',
            stack: 'nqi',
            __metricGroup: 'nqi',
            __unit: 'TB',
            __format: v => v + ' TB'
        }))
    };

    // Default set: all metrics active. Order matters for layering.
    const DEFAULT_METRICS = ['added', 'removed', 'nqi', 'storage', 'files', 'quality'];
    window.__trendDefaultMetrics = new Set(DEFAULT_METRICS);
    window.__trendActiveMetrics = new Set(['storage', 'files']); // overview default
    window.__trendIsolated = false;

    // Curated presets. Each preset is a metric set + its own meaning.
    window.__trendPresets = {
        overview: { label: 'Overview', metrics: ['storage', 'files'] },
        activity: { label: 'Activity', metrics: ['added', 'removed'] },
        quality:  { label: 'Quality',  metrics: ['quality', 'storage'] },
        tiers:    { label: 'Tiers',    metrics: ['nqi'] },
        all:      { label: 'All',      metrics: DEFAULT_METRICS }
    };
    window.__trendActivePreset = 'overview';

    function setActivePresetTab(presetKey) {
        window.__trendActivePreset = presetKey;
        document.querySelectorAll('.trend-preset-tab').forEach(tab => {
            tab.classList.toggle('active', tab.getAttribute('data-preset') === presetKey);
        });
    }

    // Detect which preset (if any) the current active set matches exactly
    function detectMatchingPreset() {
        const active = window.__trendActiveMetrics;
        for (const [key, preset] of Object.entries(window.__trendPresets)) {
            if (preset.metrics.length !== active.size) continue;
            if (preset.metrics.every(m => active.has(m))) return key;
        }
        return null;
    }

    window.applyTrendPreset = function(presetKey) {
        const preset = window.__trendPresets[presetKey];
        if (!preset) return;
        window.__trendActiveMetrics.clear();
        preset.metrics.forEach(m => window.__trendActiveMetrics.add(m));
        // Presets are not "isolated" mode — they're a curated state. Pills hidden.
        window.__trendIsolated = false;
        setActivePresetTab(presetKey);
        applyTrendState();
    };

    function applyTrendState() {
        const active = window.__trendActiveMetrics;
        document.querySelectorAll('.trend-rail-btn').forEach(btn => {
            const m = btn.getAttribute('data-metric');
            btn.classList.toggle('active', active.has(m));
        });
        if (chartHist) {
            chartHist.data.datasets = buildDatasets();
            chartHist.options.scales = buildScales();
            chartHist.update();
            generateTrendLegend(chartHist);
        }
    }

    function buildDatasets() {
        const out = [];
        for (const m of window.__trendActiveMetrics) {
            const ds = window.__trendMetricBuilders[m]?.() || [];
            ds.forEach(d => { d.__metric = m; });
            out.push(...ds);
        }
        return out;
    }

    function buildScales() {
        const active = window.__trendActiveMetrics;
        const showTb = active.has('storage') || active.has('nqi');
        const showFiles = active.has('files') || active.has('added') || active.has('removed');
        const showPct = active.has('quality');
        const stacked = active.has('nqi');

        return {
            yTb: {
                display: showTb,
                position: 'left',
                stacked: stacked,
                beginAtZero: true,
                grid: { color: 'rgba(128,128,128,0.08)', drawBorder: false, drawOnChartArea: showTb },
                border: { display: false },
                ticks: { color: 'var(--text-muted)', callback: v => v + ' TB' },
                title: { display: showTb, text: 'Storage (TB)', color: 'var(--text-muted)', font: { size: 11 } }
            },
            yFiles: {
                display: showFiles,
                position: 'right',
                beginAtZero: true,
                grid: { drawOnChartArea: false, drawBorder: false, display: false },
                border: { display: false },
                ticks: { color: 'var(--text-muted)', callback: v => v.toLocaleString() },
                title: { display: showFiles, text: 'Files', color: 'var(--text-muted)', font: { size: 11 } }
            },
            yPct: {
                display: false,
                position: 'right',
                min: 0, max: 220,
                grid: { drawOnChartArea: false, drawBorder: false, display: false },
                border: { display: false },
                ticks: { display: false }
            },
            x: {
                ticks: {
                    display: true,
                    maxTicksLimit: 6,
                    maxRotation: 0,
                    autoSkip: true,
                    color: 'var(--text-muted)',
                    font: { family: 'monospace', size: 10 }
                },
                grid: { display: true, drawBorder: false, color: 'rgba(128,128,128,0.08)' },
                border: { display: false }
            }
        };
    }

    window.toggleTrendMetric = function(metric) {
        const active = window.__trendActiveMetrics;

        // First click from a preset state → ISOLATE the clicked metric
        if (!window.__trendIsolated) {
            active.clear();
            active.add(metric);
            window.__trendIsolated = true;
        } else {
            // Already isolated — additive toggle. If removing the last one, restore Overview.
            if (active.has(metric)) {
                active.delete(metric);
                if (active.size === 0) {
                    return window.applyTrendPreset('overview');
                }
            } else {
                active.add(metric);
            }
        }

        // If the new set matches a preset exactly, switch back to that preset (clean state)
        const matched = detectMatchingPreset();
        if (matched) {
            window.__trendIsolated = false;
            setActivePresetTab(matched);
        } else {
            setActivePresetTab(null);
        }
        applyTrendState();
    };

    window.clearTrendMetrics = function() {
        window.applyTrendPreset('overview');
    };

    // Legend pills below the trend chart were removed — preset tabs + bottom rail hover info
    // already convey active state. Keep this function as a no-op so existing call sites don't break.
    window.generateTrendLegend = function() { /* legend row removed by design */ };

    try {
        const ctxHist = document.getElementById('trendChartHist');
        if (ctxHist) {
            chartHist = new Chart(ctxHist, {
                type: 'line',
                plugins: [trendAreaPlugin],
                data: { labels: histDates, datasets: buildDatasets() },
                options: {
                    maintainAspectRatio: false, responsive: true,
                    layout: { padding: { left: 16, right: 16, top: 8, bottom: 12 } },
                    plugins: { title: { display: false }, subtitle: { display: false }, legend: { display: false }, tooltip: tooltipOff },
                    scales: buildScales(),
                    interaction: { mode: 'index', intersect: false },
                    onHover: pointerHover,
                    onClick: chartAreaClickFilter
                }
            });
            generateTrendLegend(chartHist);
        }
    } catch(e) { console.error(e); }
}

// ==============================================================================
// 7. THEME ENGINE & BOOTSTRAPPER
// ==============================================================================
const NNUVA_THEMES = ['light', 'dark', 'oled'];
const NNUVA_THEME_ICONS = {
    light: '<svg viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" fill="none" stroke-width="2.2"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>',
    dark: '<svg viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" fill="none" stroke-width="2.2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>',
    oled: '<span style="font-size:0.95rem;line-height:1;color:var(--primary);">⬢</span>'
};

window.setTheme = function(mode) {
    if (!NNUVA_THEMES.includes(mode)) mode = 'oled';
    try { localStorage.setItem('nnuva_theme_mode', mode); } catch (_) {}
    applyTheme();
};

window.cycleTheme = function() {
    let cur = 'oled';
    try { cur = localStorage.getItem('nnuva_theme_mode') || 'oled'; } catch (_) {}
    const idx = NNUVA_THEMES.indexOf(cur);
    const next = NNUVA_THEMES[(idx + 1) % NNUVA_THEMES.length];
    window.setTheme(next);
};

function applyTheme() {
    let mode = 'oled';
    try {
        const saved = localStorage.getItem('nnuva_theme_mode');
        if (saved && NNUVA_THEMES.includes(saved)) mode = saved;
    } catch (_) {}

    const color = mode === 'light' ? '#0284c7' : '#38bdf8';
    document.documentElement.setAttribute('data-theme', mode);
    document.documentElement.style.setProperty('--primary', color);
    document.documentElement.style.setProperty('--primary-glow', `rgba(${hexToRgb(color)}, 0.25)`);
    document.documentElement.style.setProperty('--primary-bg', `rgba(${hexToRgb(color)}, 0.12)`);

    document.querySelectorAll('[data-theme-opt]').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-theme-opt') === mode);
    });

    const label = mode === 'oled' ? 'OLED' : (mode.charAt(0).toUpperCase() + mode.slice(1));
    document.querySelectorAll('.theme-cycle-btn').forEach(btn => {
        btn.title = `Theme: ${label} (click to switch)`;
        const iconSpan = btn.querySelector('.theme-cycle-icon');
        if (iconSpan) iconSpan.innerHTML = NNUVA_THEME_ICONS[mode] || NNUVA_THEME_ICONS.oled;
    });

    const rootStyle = getComputedStyle(document.documentElement);
    const gridColor = rootStyle.getPropertyValue('--grid-line').trim() || (mode === 'light' ? '#e2e8f0' : 'rgba(148, 163, 184, 0.14)');
    const themeBgCard = rootStyle.getPropertyValue('--bg-card').trim() || (mode === 'light' ? '#ffffff' : '#080b11');
    const textMuted = rootStyle.getPropertyValue('--text-muted').trim() || '#94a3b8';
    const textMain = rootStyle.getPropertyValue('--text-main').trim() || '#f8fafc';

    try {
        if (typeof Chart !== 'undefined') {
            Chart.defaults.color = textMuted;
            const chartsToUpdate = [chartHist, bResChart, bNqiChart, bResSizeChart, bCatSizeChart, bSeriesHogChart, bCatEfficiencyChart, bCodecChart, bAudioChart, bHdrChart, bBitrateScatterChart, bBitrateByResChart, bBitrateHistChart, window.modalChartInstance];
            chartsToUpdate.forEach(c => {
                if (!c) return;
                if (c.options.scales) {
                    if (c.options.scales.x) {
                        if (c.options.scales.x.grid) c.options.scales.x.grid.color = gridColor;
                        if (c.options.scales.x.ticks) c.options.scales.x.ticks.color = textMuted;
                        if (c.options.scales.x.title) c.options.scales.x.title.color = textMuted;
                    }
                    if (c.options.scales.y) {
                        if (c.options.scales.y.grid) c.options.scales.y.grid.color = gridColor;
                        if (c.options.scales.y.ticks) c.options.scales.y.ticks.color = textMuted;
                        if (c.options.scales.y.title) c.options.scales.y.title.color = textMuted;
                    }
                    if (c.options.scales.r) {
                        if (c.options.scales.r.grid) c.options.scales.r.grid.color = gridColor;
                        if (c.options.scales.r.angleLines) c.options.scales.r.angleLines.color = gridColor;
                        if (c.options.scales.r.pointLabels) c.options.scales.r.pointLabels.color = textMain;
                    }
                }
                if (c.config.type === 'line' || c.data.datasets.some(d => d.type === 'line')) {
                    c.data.datasets.forEach(ds => {
                        ds.pointHoverBackgroundColor = themeBgCard;
                        ds.pointHoverBorderColor = ds.borderColor || ds.backgroundColor;
                    });
                }
                c.update('none');
            });
        }
    } catch(e) { console.error("Theme apply error:", e); }
}

window.triggerMockCrash = function() {
    document.getElementById('hexMenu')?.classList.remove('show');
    setTimeout(() => {
        try {
            throw new Error("Simulated core pipeline failure. Database integrity check aborted.");
        } catch (e) {
            if (typeof renderCrash === 'function') {
                renderCrash('MANUAL SYSTEM HALT', e.message, 'app.js', 42, 12, e.stack);
            }
        }
    }, 100);
};

async function bootDashboard() {
    try {
        console.log("NNUVA Dashboard Booting...");
        assertDOM();
        applyTheme();

        // Eagerly create the per-card info bar inside every chart card so it's
        // always visible (empty by default), preventing any layout shift on hover.
        document.querySelectorAll('.chart-container, .trend-container').forEach(card => {
            if (card.querySelector(':scope > .card-info-bar')) return;
            const bar = document.createElement('div');
            bar.className = 'card-info-bar';
            card.appendChild(bar);
        });

        const histStr = document.getElementById('historyData')?.textContent.trim();
        const fileStr = document.getElementById('filesData')?.textContent.trim();
        
        if (histStr) historyLog = await decompressGzipBase64(histStr);
        if (fileStr) rawFiles = await decompressGzipBase64(fileStr);
        
        if (Array.isArray(rawFiles) && rawFiles.length > 0) {
            rawFiles.forEach((f, i) => {
                f.id = i;
                enrichFileMetadata(f);
            });
            currentFilteredData = rawFiles; 
        }
    } catch (e) {
        if (typeof renderCrash === 'function') {
            renderCrash('CRITICAL PARSING ERROR', e.message, 'app.js', 0, 0, e.stack);
        } else {
            alert("Fatal Error: " + e.message);
        }
        return;
    }

    try {
        const qaClearBtn = document.getElementById('qaClearBtn');
        if (qaClearBtn) qaClearBtn.addEventListener('click', clearAllFilters);

        const qaExportBtn = document.getElementById('qaExportBtn');
        if (qaExportBtn) qaExportBtn.addEventListener('click', exportDataToCSV);

        const searchInput = document.getElementById('globalSearch');
        if (searchInput) {
            searchInput.addEventListener('input', function() {
                searchQuery = this.value;
                syncSearchInputs(this.id);
                runFilterPipeline();
            });
            searchInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    jumpToLibrary();
                }
            });
        }

        const libSearchInput = document.getElementById('librarySearch');
        if (libSearchInput) {
            libSearchInput.addEventListener('input', function() {
                searchQuery = this.value;
                syncSearchInputs(this.id);
                runFilterPipeline();
            });
            libSearchInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    jumpToLibrary();
                }
            });
        }

        const heroSearchInput = document.getElementById('heroSearch');
        if (heroSearchInput) {
            heroSearchInput.addEventListener('input', function() {
                searchQuery = this.value;
                syncSearchInputs(this.id);
                runFilterPipeline();
            });
            heroSearchInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    jumpToLibrary();
                }
            });
        }

        const menuGuideBtn = document.getElementById('menuGuideBtn');
        if (menuGuideBtn) menuGuideBtn.addEventListener('click', () => openGuideModal('intro'));

        const menuChangelogBtn = document.getElementById('menuChangelogBtn');
        if (menuChangelogBtn) menuChangelogBtn.addEventListener('click', openChangelog);

        const meatballChangelogBtn = document.getElementById('meatballChangelogBtn');
        if (meatballChangelogBtn) meatballChangelogBtn.addEventListener('click', function() {
            document.getElementById('meatballMenu')?.classList.remove('show');
            document.getElementById('footerKebabBtn')?.classList.remove('active');
            openChangelog();
        });

        applyTheme();

        // Floating top-gavel: appears once the hero header bar scrolls out of view
        (function setupFloatingGavel() {
            const hero = document.querySelector('.hero-bar');
            if (!hero) {
                document.body.classList.add('has-floating-gavel');
                return;
            }
            let ticking = false;
            let wasFloating = false;
            const update = () => {
                const rect = hero.getBoundingClientRect();
                const shouldFloat = rect.bottom < 8;
                if (shouldFloat !== wasFloating) {
                    wasFloating = shouldFloat;
                }
                document.body.classList.toggle('has-floating-gavel', shouldFloat);
                ticking = false;
            };
            window.addEventListener('scroll', () => {
                if (!ticking) {
                    requestAnimationFrame(update);
                    ticking = true;
                }
            }, { passive: true });
            window.addEventListener('resize', update);
            update();
        })();
        
        if (typeof Chart === 'undefined') {
            showToast('Visualization engine blocked by network. Tables active.', 'Check if your adblocker or firewall is preventing the Chart.js CDN from loading.');
        } else {
            initBottomCharts();
            if (historyLog.length > 0) {
                initTopCharts();
                initSparkline();
            }
            applyTheme();
        }
        
        if (Array.isArray(rawFiles) && rawFiles.length > 0) {
            runFilterPipeline();
            renderLibraryChanges();
        } else {
            const kpiFiles = document.getElementById('kpi-files');
            if(kpiFiles) kpiFiles.innerText = '0';
            const kpiStorage = document.getElementById('kpi-storage');
            if(kpiStorage) kpiStorage.innerText = '0 GB';
            const kpiOptimal = document.getElementById('kpi-optimal');
            if(kpiOptimal) kpiOptimal.innerText = '0';
            const kpiTranscode = document.getElementById('kpi-transcode');
            if(kpiTranscode) kpiTranscode.innerText = '0';
            const kpiUpgrade = document.getElementById('kpi-upgrade');
            if(kpiUpgrade) kpiUpgrade.innerText = '0';
            
            const tableFiltered = document.getElementById('table-filtered');
            if(tableFiltered) tableFiltered.innerHTML = "<tr><td colspan='7'>No data available in cache.</td></tr>";
            const tableTranscode = document.getElementById('table-transcode');
            if(tableTranscode) tableTranscode.innerHTML = "<tr><td colspan='7'>No transcode targets found.</td></tr>";
            const tableUpgrade = document.getElementById('table-upgrade');
            if(tableUpgrade) tableUpgrade.innerHTML = "<tr><td colspan='7'>No upgrade targets found.</td></tr>";
            const tableLargest = document.getElementById('table-largest');
            if(tableLargest) tableLargest.innerHTML = "<tr><td colspan='7'>No files found.</td></tr>";
        }
    } catch (e) {
        if (typeof renderCrash === 'function') {
            renderCrash('CRITICAL BOOT CRASH', e.message, 'app.js', 0, 0, e.stack);
        } else {
            alert("Fatal Error: " + e.message);
        }
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootDashboard);
} else {
    bootDashboard();
}
