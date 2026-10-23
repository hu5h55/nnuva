#!/usr/bin/env bash
# ==============================================================================
# NNUVA & NNUVA-REPORT Unified Installer & Environment Manager
# https://github.com/hu5h55/nnuva
# ==============================================================================

set -eo pipefail

INSTALLER_VERSION="1.0.0"
REPO_NNUVA="https://raw.githubusercontent.com/hu5h55/nnuva/main"
GIT_NNUVA="https://github.com/hu5h55/nnuva.git"
GIT_REPORT="https://github.com/hu5h55/nnuva-report.git"

# Color Palette
RESET='\033[0m'
BOLD='\033[1m'
CYAN='\033[96m'
GREEN='\033[92m'
YELLOW='\033[93m'
RED='\033[91m'
GRAY='\033[90m'

# Default configurations
INSTALL_SCOPE="user"        # "user" (~/.local/bin) or "system" (/usr/local/bin)
TARGET_BIN=""
COMPONENTS="all"            # "all", "nnuva", or "report"
ENABLE_CRON=false
CRON_SCHEDULE="0 4 * * *"
DEFAULT_MEDIA_DIR="/media/videos"
DEFAULT_OUTPUT_DIR="/var/www/html/nnuva"
NON_INTERACTIVE=false
DO_UNINSTALL=false
DO_PURGE=false

# Locate current script directory if run locally
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "")"
REPO_NNUVA="https://raw.githubusercontent.com/hu5h55/nnuva/main"
GIT_NNUVA="https://github.com/hu5h55/nnuva.git"

print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "  ⬢ NNUVA & NNUVA-REPORT UNIFIED INSTALLER ⬢"
    echo -e "  ${GRAY}High-Performance Media Analyzer & Interactive Dashboard${RESET}"
    echo ""
}

show_help() {
    echo -e "${BOLD}Usage:${RESET} $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --user                 Install in user space (~/.local/bin, no root required) [Default]"
    echo "  --system               Install system-wide (/usr/local/bin, requires sudo)"
    echo "  --components [MODE]    Components to install: all, nnuva, report (Default: all)"
    echo "  --media-dir [PATH]     Default video library path for automated scans"
    echo "  --output-dir [PATH]    Destination directory for generated HTML dashboard"
    echo "  --cron [SCHEDULE]      Register automated cron job (e.g. \"0 4 * * *\")"
    echo "  --no-cron              Skip automated cron setup"
    echo "  --uninstall            Remove installed binaries, cron job, and helper scripts"
    echo "  --purge                Delete ~/.nnuva configuration, databases, and caches"
    echo "  -y, --yes              Accept defaults and run non-interactively"
    echo "  -h, --help             Show this help message"
    echo ""
    echo "Quick 1-Line Install:"
    echo "  curl -fsSL ${REPO_NNUVA}/install.sh | bash"
    echo ""
}

# Parse Command-Line Arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --user)
            INSTALL_SCOPE="user"
            shift
            ;;
        --system)
            INSTALL_SCOPE="system"
            shift
            ;;
        --components)
            COMPONENTS="$2"
            shift 2
            ;;
        --media-dir)
            DEFAULT_MEDIA_DIR="$2"
            shift 2
            ;;
        --output-dir)
            DEFAULT_OUTPUT_DIR="$2"
            shift 2
            ;;
        --cron)
            ENABLE_CRON=true
            if [[ -n "${2:-}" && "$2" != --* ]]; then
                CRON_SCHEDULE="$2"
                shift
            fi
            shift
            ;;
        --no-cron)
            ENABLE_CRON=false
            shift
            ;;
        --uninstall)
            DO_UNINSTALL=true
            shift
            ;;
        --purge)
            DO_PURGE=true
            shift
            ;;
        -y|--yes)
            NON_INTERACTIVE=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${RESET}"
            show_help
            exit 1
            ;;
    esac
done

# Set binary target path
if [[ "$INSTALL_SCOPE" == "system" ]]; then
    TARGET_BIN="/usr/local/bin"
    RUNNER_DIR="/usr/local/bin"
else
    TARGET_BIN="${HOME}/.local/bin"
    RUNNER_DIR="${HOME}/.local/bin"
fi

check_prerequisites() {
    echo -e "${BOLD}Checking environment prerequisites:${RESET}"
    
    # 1. Python 3
    if command -v python3 >/dev/null 2>&1; then
        PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        echo -e "  [${GREEN}✓${RESET}] Python ${PY_VER} detected"
    else
        echo -e "  [${RED}✗${RESET}] Python 3 is missing. Please install Python 3.8+."
        exit 1
    fi

    # 2. ffprobe
    if command -v ffprobe >/dev/null 2>&1; then
        echo -e "  [${GREEN}✓${RESET}] ffprobe detected"
    else
        echo -e "  [${YELLOW}!${RESET}] ${BOLD}ffprobe is not installed.${RESET} NNUVA requires ffprobe to inspect video streams."
        echo -e "      Install it via: ${CYAN}sudo apt install -y ffmpeg${RESET} or ${CYAN}brew install ffmpeg${RESET}"
    fi

    # 3. git
    if command -v git >/dev/null 2>&1; then
        echo -e "  [${GREEN}✓${RESET}] git detected"
    else
        echo -e "  [${YELLOW}!${RESET}] git not found (curl will be used for fallback downloads)"
    fi
    echo ""
}

perform_uninstall() {
    echo -e "${RED}${BOLD}=== NNUVA UNINSTALLATION ===${RESET}"
    
    # Remove binaries
    BIN_TARGETS=(
        "${HOME}/.local/bin/nnuva"
        "${HOME}/.local/bin/nnuva-report"
        "/usr/local/bin/nnuva"
        "/usr/local/bin/nnuva-report"
        "${HOME}/.local/bin/update_nnuva_dashboard.sh"
    )

    REMOVED_COUNT=0
    for b in "${BIN_TARGETS[@]}"; do
        if [[ -f "$b" || -L "$b" ]]; then
            rm -f "$b" 2>/dev/null || sudo rm -f "$b" 2>/dev/null || true
            echo -e "  [${GREEN}✓${RESET}] Removed ${b}"
            ((REMOVED_COUNT++)) || true
        fi
    done

    # Remove cron job
    if crontab -l 2>/dev/null | grep -q "update_nnuva_dashboard"; then
        crontab -l 2>/dev/null | grep -v "update_nnuva_dashboard" | crontab - || true
        echo -e "  [${GREEN}✓${RESET}] Removed automated NNUVA schedule from crontab"
    fi

    # Handle ~/.nnuva data directory
    CACHE_DIR="${HOME}/.nnuva"
    if [[ -d "$CACHE_DIR" ]]; then
        if [[ "$DO_PURGE" == true ]]; then
            rm -rf "$CACHE_DIR"
            echo -e "  [${GREEN}✓${RESET}] Purged ${CACHE_DIR}"
        elif [[ "$NON_INTERACTIVE" == false && -t 0 ]]; then
            read -r -p "  Purge database and cache in ${CACHE_DIR}? [y/N]: " confirm_purge
            if [[ "$confirm_purge" =~ ^[Yy]$ ]]; then
                rm -rf "$CACHE_DIR"
                echo -e "  [${GREEN}✓${RESET}] Purged ${CACHE_DIR}"
            else
                echo -e "  [${GRAY}-${RESET}] Retained ${CACHE_DIR}"
            fi
        else
            echo -e "  [${GRAY}-${RESET}] Retained ${CACHE_DIR} (use --purge to delete)"
        fi
    fi

    echo -e "\n${GREEN}${BOLD}NNUVA uninstalled successfully.${RESET}"
    exit 0
}

# If --uninstall was specified, execute uninstaller
if [[ "$DO_UNINSTALL" == true ]]; then
    print_banner
    perform_uninstall
fi

# Reusable interactive prompt supporting both local and curl|bash execution
prompt_read() {
    local prompt_msg="$1"
    local var_name="$2"
    local default_val="${3:-}"

    if [[ "$NON_INTERACTIVE" == true ]]; then
        eval "$var_name=\"\$default_val\""
        return
    fi

    local input_val=""
    if [[ -t 0 ]]; then
        read -r -p "$prompt_msg" input_val || true
    elif [[ -e /dev/tty ]]; then
        read -r -p "$prompt_msg" input_val < /dev/tty || true
    else
        input_val=""
    fi

    if [[ -z "$input_val" ]]; then
        input_val="$default_val"
    fi
    eval "$var_name=\"\$input_val\""
}

interactive_wizard() {
    print_banner
    check_prerequisites

    echo -e "${BOLD}Select installation options:${RESET}"
    echo "  1) User space (~/.local/bin) [Recommended - No root required]"
    echo "  2) System-wide (/usr/local/bin) [Requires sudo]"
    prompt_read "Target destination [1]: " dest_choice "1"
    if [[ "$dest_choice" == "2" ]]; then
        INSTALL_SCOPE="system"
        TARGET_BIN="/usr/local/bin"
        RUNNER_DIR="/usr/local/bin"
    else
        INSTALL_SCOPE="user"
        TARGET_BIN="${HOME}/.local/bin"
        RUNNER_DIR="${HOME}/.local/bin"
    fi
    echo ""

    echo "Components to install:"
    echo "  1) Both 'nnuva' (Core Scanner) & 'nnuva-report' (Interactive HTML Dashboard)"
    echo "  2) Only 'nnuva' CLI scanner"
    prompt_read "Selection [1]: " comp_choice "1"
    if [[ "$comp_choice" == "2" ]]; then
        COMPONENTS="nnuva"
    else
        COMPONENTS="all"
    fi
    echo ""

    if [[ "$COMPONENTS" == "all" ]]; then
        prompt_read "Enable automated daily cron scan & dashboard update? [Y/n]: " cron_choice "Y"
        if [[ ! "$cron_choice" =~ ^[Nn]$ ]]; then
            ENABLE_CRON=true
            prompt_read "Default video media directory [${DEFAULT_MEDIA_DIR}]: " custom_media "${DEFAULT_MEDIA_DIR}"
            DEFAULT_MEDIA_DIR="$custom_media"

            prompt_read "HTML dashboard output folder [${DEFAULT_OUTPUT_DIR}]: " custom_out "${DEFAULT_OUTPUT_DIR}"
            DEFAULT_OUTPUT_DIR="$custom_out"
        else
            ENABLE_CRON=false
        fi
        echo ""
    fi
}

if [[ "$NON_INTERACTIVE" == false && ( -t 0 || -e /dev/tty ) ]]; then
    interactive_wizard
else
    print_banner
    check_prerequisites
fi

mkdir -p "$TARGET_BIN"

# --- Install Suite Components ---
if [[ -f "${SCRIPT_DIR}/nnuva.py" && -f "${SCRIPT_DIR}/nnuva-report" ]]; then
    # Local repository mode: symlink directly to keep in sync with git
    SOURCE_DIR="${SCRIPT_DIR}"
else
    # Remote 1-liner mode: clone/pull unified repository into ~/.local/share/nnuva
    SOURCE_DIR="${HOME}/.local/share/nnuva"
    mkdir -p "${HOME}/.local/share"
    if [[ -d "${SOURCE_DIR}/.git" ]]; then
        (cd "$SOURCE_DIR" && git pull --quiet origin main 2>/dev/null || true)
    elif command -v git >/dev/null 2>&1; then
        echo -e "${BOLD}Cloning NNUVA repository...${RESET}"
        git clone --quiet "$GIT_NNUVA" "$SOURCE_DIR"
    else
        mkdir -p "$SOURCE_DIR"
        curl -fsSL "${REPO_NNUVA}/nnuva.py" -o "${SOURCE_DIR}/nnuva.py"
        curl -fsSL "${REPO_NNUVA}/nnuva-report" -o "${SOURCE_DIR}/nnuva-report"
        chmod +x "${SOURCE_DIR}/nnuva.py" "${SOURCE_DIR}/nnuva-report"
    fi
fi

if [[ "$COMPONENTS" == "all" || "$COMPONENTS" == "nnuva" ]]; then
    echo -e "${BOLD}Installing nnuva CLI...${RESET}"
    DEST_NNUVA="${TARGET_BIN}/nnuva"
    ln -sf "${SOURCE_DIR}/nnuva.py" "$DEST_NNUVA"
    chmod +x "${SOURCE_DIR}/nnuva.py" 2>/dev/null || true
    echo -e "  [${GREEN}✓${RESET}] Linked ${DEST_NNUVA} -> ${SOURCE_DIR}/nnuva.py"
fi

if [[ "$COMPONENTS" == "all" || "$COMPONENTS" == "report" ]]; then
    echo -e "${BOLD}Installing nnuva-report...${RESET}"
    DEST_REPORT="${TARGET_BIN}/nnuva-report"
    ln -sf "${SOURCE_DIR}/nnuva-report" "$DEST_REPORT"
    chmod +x "${SOURCE_DIR}/nnuva-report" 2>/dev/null || true
    echo -e "  [${GREEN}✓${RESET}] Linked ${DEST_REPORT} -> ${SOURCE_DIR}/nnuva-report"
fi

# --- Establish Homebase Structure ---
mkdir -p "${HOME}/.nnuva"
HOMEBASE_FILE="${HOME}/.nnuva/homebase.json"
if [[ ! -f "$HOMEBASE_FILE" ]]; then
    cat <<EOF > "$HOMEBASE_FILE"
{
    "installed_at": "$(date -Iseconds)",
    "installed_by": "install.sh",
    "bin_path": "${TARGET_BIN}"
}
EOF
fi

# --- Configure Automated Cron Runner ---
if [[ "$ENABLE_CRON" == true ]]; then
    echo -e "${BOLD}Configuring automated cron job...${RESET}"
    RUNNER_SCRIPT="${RUNNER_DIR}/update_nnuva_dashboard.sh"
    LOG_FILE="${HOME}/.nnuva/cron_update.log"
    LOCK_FILE="/tmp/nnuva_dashboard_cron.lock"

    cat <<EOF > "$RUNNER_SCRIPT"
#!/usr/bin/env bash
# Automated NNUVA Scan & Dashboard Builder
set -euo pipefail

export PATH="${TARGET_BIN}:/usr/local/bin:/usr/bin:/bin"
MEDIA_DIR="${DEFAULT_MEDIA_DIR}"
OUTPUT_DIR="${DEFAULT_OUTPUT_DIR}"
LOG_FILE="${LOG_FILE}"
LOCK_FILE="${LOCK_FILE}"

mkdir -p "\$(dirname "\$LOG_FILE")" "\$OUTPUT_DIR"

exec 9>"\$LOCK_FILE"
if ! flock -n 9; then
    echo "[\$(date -Is)] Skipping: another NNUVA update is currently running." >> "\$LOG_FILE"
    exit 0
fi

{
    echo "============================================================"
    echo "[\$(date -Is)] Starting scheduled NNUVA scan & dashboard build"
    
    # 1. Scan and automatically prune stale keys for deleted/moved files
    if command -v nnuva >/dev/null 2>&1; then
        nnuva -s "\$MEDIA_DIR" --prune || true
    fi

    # 2. Rebuild HTML and JSON dashboard metrics
    if command -v nnuva-report >/dev/null 2>&1; then
        nnuva-report -o "\$OUTPUT_DIR" || true
    fi

    # 3. If Homepage services config exists, update cachebuster
    HOMEPAGE_CONF="${HOME}/docker/homepage/config/services.yaml"
    if [[ -f "\$HOMEPAGE_CONF" ]]; then
        sed -i -E "s|href: /nnuva/index\\.html(\\?v=[^[:space:]]*)?|href: /nnuva/index.html?v=\$(date +%Y%m%d%H%M)|" "\$HOMEPAGE_CONF" 2>/dev/null || true
    fi

    echo "[\$(date -Is)] Completed NNUVA dashboard update successfully"
} >> "\$LOG_FILE" 2>&1
EOF
    chmod +x "$RUNNER_SCRIPT"
    echo -e "  [${GREEN}✓${RESET}] Created runner: ${RUNNER_SCRIPT}"

    # Register into user crontab
    CRON_LINE="${CRON_SCHEDULE} ${RUNNER_SCRIPT}"
    CURRENT_CRON=$(crontab -l 2>/dev/null || true)
    if echo "$CURRENT_CRON" | grep -q "$RUNNER_SCRIPT"; then
        echo -e "  [${GRAY}-${RESET}] Crontab already contains runner entry"
    else
        (echo "$CURRENT_CRON" | grep -v "update_nnuva_dashboard"; echo "$CRON_LINE") | crontab -
        echo -e "  [${GREEN}✓${RESET}] Registered crontab: ${CRON_LINE}"
    fi
fi

# Ensure PATH includes TARGET_BIN
if [[ ":$PATH:" != *":${TARGET_BIN}:"* ]]; then
    echo ""
    echo -e "${YELLOW}Notice: ${TARGET_BIN} is not currently in your active PATH.${RESET}"
    echo -e "Add it to your shell by running: ${CYAN}export PATH=\"${TARGET_BIN}:\$PATH\"${RESET}"
fi

echo ""
echo -e "${GREEN}${BOLD}✓ Installation complete!${RESET}"
echo -e "Run ${CYAN}nnuva --help${RESET} or ${CYAN}nnuva${RESET} to scan your media library."
if [[ "$ENABLE_CRON" == true ]]; then
    echo -e "Dashboard updates run daily at ${CYAN}${CRON_SCHEDULE}${RESET} -> outputting to ${CYAN}${DEFAULT_OUTPUT_DIR}${RESET}."
fi
