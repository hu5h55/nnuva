import sys
import os
from pathlib import Path
from . import APP_NAME, VERSION

class Color:
    RESET   = '\033[0m'
    BOLD    = '\033[1m'
    RED     = '\033[91m'
    GREEN   = '\033[92m'
    YELLOW  = '\033[93m'
    CYAN    = '\033[96m'
    GRAY    = '\033[90m'
    WHITE   = '\033[97m'

class SystemManager:
    def __init__(self):
        self.app_name = APP_NAME
        self.version = VERSION
        self.brand = f"{Color.WHITE}{Color.BOLD}⬢-{self.app_name}{Color.RESET}"
        self.home_dir = Path.home()
        self.db_dir = self.home_dir / '.nnuva'
        
        self.target_dir = self.home_dir / '.local' / 'bin'
        if 'ios' in sys.platform.lower() or '/var/mobile' in str(self.home_dir): 
            self.target_dir = self.home_dir / 'bin'
        elif not self.target_dir.exists() and (self.home_dir / 'bin').exists(): 
            self.target_dir = self.home_dir / 'bin'
            
        self.target_path = self.target_dir / self.app_name

    def info(self):
        """Prints environment configuration and cache sizes."""
        cache_filepath = self.db_dir / 'ffprobe_cache.json'
        db_filepath = self.db_dir / 'nnuva.db'
        
        print(f"\n{self.brand} {Color.CYAN}System Info{Color.RESET}")
        print(f"{Color.GRAY}----------------------------------------{Color.RESET}")
        print(f" {Color.BOLD}Running Version:{Color.RESET} v{self.version}")
        print(f" {Color.BOLD}Database Path:{Color.RESET}   {self.db_dir.absolute()}")
        
        c_size = f"{round(cache_filepath.stat().st_size / (1024*1024), 2)} MB" if cache_filepath.exists() else "0 MB"
        db_size = f"{round(db_filepath.stat().st_size / (1024*1024), 2)} MB" if db_filepath.exists() else "0 MB"
        
        print(f" {Color.BOLD}JSON Cache:{Color.RESET}      {c_size}")
        print(f" {Color.BOLD}SQLite DB:{Color.RESET}       {db_size}")
        print(f"{Color.GRAY}----------------------------------------{Color.RESET}\n")
