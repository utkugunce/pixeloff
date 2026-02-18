import os
import sys
import shutil
import socket
import subprocess
import requests
import time
import psutil
import platform

class SystemDiagnostics:
    def __init__(self):
        self.results = {}

    def run_all(self):
        """Runs all diagnostic checks and returns a dictionary of results."""
        self.results['System Info'] = self.get_system_info()
        self.results['Disk Usage'] = self.check_disk_usage()
        self.results['Memory Usage'] = self.check_memory_usage()
        self.results['Network Connectivity'] = self.check_network()
        self.results['Dependencies'] = self.check_dependencies()
        self.results['Browser Check'] = self.check_browser()
        return self.results

    def get_system_info(self):
        try:
            return {
                "OS": platform.system(),
                "Release": platform.release(),
                "Python Version": sys.version.split()[0],
                "Processor": platform.processor(),
                "Hostname": socket.gethostname()
            }
        except Exception as e:
            return {"Error": str(e)}

    def check_disk_usage(self):
        try:
            total, used, free = shutil.disk_usage("/")
            return {
                "Total (GB)": round(total / (2**30), 2),
                "Used (GB)": round(used / (2**30), 2),
                "Free (GB)": round(free / (2**30), 2),
                "Percent Used": f"{round((used / total) * 100, 1)}%"
            }
        except Exception as e:
            return {"Error": str(e)}

    def check_memory_usage(self):
        try:
            mem = psutil.virtual_memory()
            return {
                "Total (MB)": round(mem.total / (2**20), 2),
                "Available (MB)": round(mem.available / (2**20), 2),
                "Percent Used": f"{mem.percent}%"
            }
        except Exception as e:
            return {"Error": str(e)}

    def check_network(self):
        targets = [
            ("Google", "https://www.google.com"),
            ("Instagram", "https://www.instagram.com"),
            ("PyPI", "https://pypi.org")
        ]
        results = {}
        for name, url in targets:
            try:
                start = time.time()
                response = requests.get(url, timeout=5)
                latency = round((time.time() - start) * 1000, 2)
                results[name] = f"✅ (Status: {response.status_code}, {latency}ms)"
            except Exception as e:
                results[name] = f"❌ Error: {str(e)}"
        return results

    def check_dependencies(self):
        pkgs = ["playwright", "rembg", "streamlit", "PIL", "numpy", "requests"]
        results = {}
        for pkg in pkgs:
            try:
                __import__(pkg)
                results[pkg] = "✅ Installed"
            except ImportError:
                results[pkg] = "❌ Missing"
            except Exception as e:
                results[pkg] = f"⚠️ Error: {str(e)}"
        return results

    def check_browser(self):
        results = {}
        
        # 1. Check if Chromium executable exists (relying on Playwright CLI)
        try:
            cmd = [sys.executable, "-m", "playwright", "install", "--dry-run"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if "chromium" in res.stdout.lower():
                results["Ref"] = "✅ Playwright indicates Chromium is present"
            else:
                 results["Ref"] = "❓ Playwright did not explicitly confirm Chromium (Dry Run)"
        except Exception as e:
            results["Ref"] = f"❌ CLI Check Failed: {str(e)}"

        # 2. Try to launch browser
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
                context = browser.new_context()
                page = context.new_page()
                page.goto("https://example.com")
                title = page.title()
                browser.close()
                results["Launch Test"] = f"✅ Success! Title: {title}"
        except Exception as e:
            results["Launch Test"] = f"❌ Failed: {str(e)}"
            
        return results
