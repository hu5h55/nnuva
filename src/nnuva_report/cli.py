# src/nnuva_report/cli.py
import argparse
import sys
from .system import SystemManager, Color
from .engine import gather_metrics
from .generator import generate_html
from . import VERSION

def main():
    sys_mgr = SystemManager()

    parser = argparse.ArgumentParser(description=f'{sys_mgr.brand} {Color.CYAN}v{VERSION}{Color.RESET}')
    parser.add_argument('-i', '--info', action='store_true', help="Show system and database info")
    parser.add_argument('-o', '--output', type=str, help='Specify custom output path (directory or file)')
    parser.add_argument('-v', '--version', action='version', version=f'{sys_mgr.brand} v{VERSION}')
    
    args = parser.parse_args()

    if args.info:
        sys_mgr.info()
        sys.exit(0)

    # 1. Run the SQLite ETL Pipeline
    metrics = gather_metrics(sys_mgr)
    
    # 2. Compile the HTML Artifact
    if metrics:
        generate_html(sys_mgr, args, metrics)

if __name__ == '__main__':
    main()
