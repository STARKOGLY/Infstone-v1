#! /usr/bin/python3
# -*- coding: utf-8 -*- 
'''
Enhanced iDRAC Vulnerability Scanner with Discord Webhook Integration
- MULTI THREADS UPTO 64 
- PROXY SYSTEM 
- FAST SCANNER 
- BETTER EMBED 
MADE BY STARK - 2026
'''
import optparse
import requests
import json
import datetime
import os
import sys
import time
import socket
import re
from multiprocessing.dummy import Pool as ThreadPool
from itertools import repeat
from urllib.parse import urlparse
import threading

# Suppress SSL warnings
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
requests.warnings.filterwarnings('ignore', category=DeprecationWarning)

# ============= CONFIGURATION =============
CONFIG = {
    "discord_webhook": "YOUR_WEBHOOK_URL_HERE",  # REPLACE THIS!
    "timeout": 10,
    "max_threads": 100,
    "retry_attempts": 2,
    "rate_limit_delay": 0.1,
    "enable_discord": True,
    "enable_logging": True,
    "log_file": "idrac_scanner.log"
}

# Global tracking with thread safety
_stats_lock = threading.Lock()
_vulnerable_systems = []
_vulnerable_count = 0
_total_scanned = 0
_scan_start_time = None
_api_errors = 0

# Headers for requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive'
}

# Vulnerability database
VULNERABILITIES = {
    'CVE-2018-1207': {
        'name': 'iDRAC7/iDRAC8 Code Injection Vulnerability',
        'cvss_score': 9.8,
        'severity': 'CRITICAL',
        'affected_versions': ['iDRAC7 < 2.52.52', 'iDRAC8 < 2.52.52'],
        'exploit_available': True,
        'check_endpoint': '/cgi-bin/login?LD_DEBUG=files'
    },
    'CVE-2019-1010279': {
        'name': 'Information Disclosure via NTP Configuration',
        'cvss_score': 5.3,
        'severity': 'MEDIUM',
        'affected_versions': ['iDRAC7 < 2.60.60', 'iDRAC8 < 2.60.60'],
        'exploit_available': False,
        'check_endpoint': '/data?get=ntpConfiguration'
    }
}

class CustomHTTPAdapter(requests.adapters.HTTPAdapter):
    """Custom adapter for older SSL/TLS versions"""
    def init_poolmanager(self, *args, **kwargs):
        context = requests.ssl.create_default_context()
        context.set_ciphers('ALL:@SECLEVEL=0')
        context.check_hostname = False
        context.minimum_version = requests.ssl.TLSVersion.SSLv3
        super().init_poolmanager(*args, **kwargs, ssl_context=context)

def print_banner():
    banner = """
╔═══════════════════════════════════════════════════════════════════════════╗
║                    🚀 ENHANCED iDRAC VULNERABILITY SCANNER 🚀             ║
║                    Discord Integration | Multi-CVE Detection              ║
║                         Author: Enhanced Edition                          ║
╚═══════════════════════════════════════════════════════════════════════════╝
"""
    print(banner)
    print("[*] Features:")
    print("    • CVE-2018-1207 (Critical RCE) detection")
    print("    • CVE-2019-1010279 (Info Disclosure) detection")
    print("    • Real-time Discord notifications")
    print("    • Multi-threaded scanning")
    print("    • Proxy support")
    print("    • Export capabilities")
    print()

def log_to_file(message, level="INFO"):
    """Log messages to file with timestamp"""
    if not CONFIG["enable_logging"]:
        return
    
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] [{level}] {message}\n"
    
    try:
        with open(CONFIG["log_file"], 'a') as f:
            f.write(log_entry)
    except Exception as e:
        pass  # Silent fail for logging

def print_status(total_ips, force=False):
    """Display scanning progress"""
    global _total_scanned, _scan_start_time
    
    if _scan_start_time:
        elapsed = time.time() - _scan_start_time
        ips_per_sec = _total_scanned / elapsed if elapsed > 0 else 0
        eta = (total_ips - _total_scanned) / ips_per_sec if ips_per_sec > 0 else 0
        
        status_line = (f"\r[*] Progress: {_total_scanned}/{total_ips} ({(_total_scanned/total_ips*100):.1f}%) | "
                      f"Vulnerable: {_vulnerable_count} | Speed: {ips_per_sec:.1f} IPs/sec | "
                      f"ETA: {eta:.1f}s | Errors: {_api_errors}")
        
        sys.stdout.write(status_line)
        sys.stdout.flush()

def send_discord_webhook(vulnerable_ip, hostname, version, firmware, cve, exploit_url, severity="CRITICAL"):
    """Enhanced Discord webhook with better formatting"""
    if not CONFIG["enable_discord"] or CONFIG["discord_webhook"] == "YOUR_WEBHOOK_URL_HERE":
        return False
    
    try:
        # Color coding based on severity
        colors = {
            "CRITICAL": 16711680,  # Red
            "HIGH": 16744448,      # Orange
            "MEDIUM": 16776960,    # Yellow
            "LOW": 32768           # Green
        }
        
        # Get CVSS score
        cvss_score = VULNERABILITIES.get(cve, {}).get('cvss_score', 'N/A')
        
        embed = {
            "title": f"🚨 {severity} VULNERABILITY DETECTED",
            "color": colors.get(severity, 16711680),
            "fields": [
                {"name": "📍 IP Address", "value": f"`{vulnerable_ip}`", "inline": False},
                {"name": "🏷️ Hostname", "value": f"`{hostname if hostname else 'Unknown'}`", "inline": True},
                {"name": "🔧 Version", "value": f"`{version}`", "inline": True},
                {"name": "📦 Firmware", "value": f"`{firmware}`", "inline": True},
                {"name": "🔍 CVE ID", "value": f"**{cve}**", "inline": True},
                {"name": "📊 CVSS Score", "value": f"`{cvss_score}`", "inline": True},
                {"name": "⚠️ Severity", "value": f"`{severity}`", "inline": True},
                {"name": "🔗 Exploit URL", "value": f"```{exploit_url}```", "inline": False},
                {"name": "📅 Detection Time", "value": f"`{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`", "inline": True}
            ],
            "footer": {
                "text": "Enhanced iDRAC Scanner | Action Required Immediately",
                "icon_url": "https://cdn-icons-png.flaticon.com/512/2173/2173475.png"
            },
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        payload = {
            "username": "iDRAC Security Monitor",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/2173/2173475.png",
            "embeds": [embed],
            "content": f"<@&ROLE_ID> **URGENT: Vulnerable iDRAC detected!**"  # Optional: Mention role
        }
        
        response = requests.post(CONFIG["discord_webhook"], json=payload, timeout=10)
        return response.status_code in [200, 204]
        
    except Exception as e:
        log_to_file(f"Discord webhook error: {str(e)}", "ERROR")
        return False

def send_batch_notification(vulnerable_systems_batch):
    """Send batch notification for multiple vulnerabilities"""
    if not CONFIG["enable_discord"] or not vulnerable_systems_batch:
        return
    
    try:
        systems_list = "\n".join([f"• `{v['ip']}` - {v['cve']} ({v['version']})" for v in vulnerable_systems_batch[:10]])
        if len(vulnerable_systems_batch) > 10:
            systems_list += f"\n• ... and {len(vulnerable_systems_batch) - 10} more"
        
        embed = {
            "title": f"📊 Vulnerability Summary - {len(vulnerable_systems_batch)} Systems",
            "color": 15105570,
            "description": f"**Multiple vulnerable iDRAC systems detected!**\n\n{systems_list}",
            "footer": {"text": "Immediate action recommended"},
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        payload = {"username": "iDRAC Scanner", "embeds": [embed]}
        requests.post(CONFIG["discord_webhook"], json=payload, timeout=10)
    except Exception as e:
        log_to_file(f"Batch notification error: {str(e)}", "ERROR")

def verify_cve_2018_1207(ip, proxy=None):
    """Verify CVE-2018-1207 exploitability"""
    url = f'https://{ip}/cgi-bin/login?LD_DEBUG=files'
    
    for attempt in range(CONFIG["retry_attempts"]):
        try:
            session = requests.Session()
            session.mount('https://', CustomHTTPAdapter())
            
            proxies = {'https': proxy} if proxy else None
            response = session.get(url, verify=False, headers=HEADERS, 
                                  proxies=proxies, timeout=CONFIG["timeout"])
            
            if response.status_code == 200 and 'calling init: /lib/' in response.text:
                return True, url
        except:
            time.sleep(0.5)
    
    return False, url

def verify_cve_2019_1010279(ip, proxy=None):
    """Verify CVE-2019-1010279 information disclosure"""
    url = f'https://{ip}/data?get=ntpConfiguration'
    
    try:
        session = requests.Session()
        session.mount('https://', CustomHTTPAdapter())
        
        proxies = {'https': proxy} if proxy else None
        response = session.get(url, verify=False, headers=HEADERS, 
                              proxies=proxies, timeout=CONFIG["timeout"])
        
        if response.status_code == 200 and 'ntpServer1' in response.text:
            return True, url
    except:
        pass
    
    return False, url

def fingerprint_idrac(args):
    """Main fingerprinting function"""
    global _total_scanned, _vulnerable_count, _api_errors
    
    ip, verbose, proxy, check_vulns, export_enabled, filter_mode = args
    
    with _stats_lock:
        _total_scanned += 1
    
    def output(msg):
        if not filter_mode or '[!' in msg or '[!!]' in msg:
            print(msg)
    
    try:
        # Test connection first
        test_url = f'https://{ip}'
        session = requests.Session()
        session.mount('https://', CustomHTTPAdapter())
        
        try:
            response = session.get(test_url, verify=False, timeout=CONFIG["timeout"])
            if response.status_code not in [200, 401, 403]:
                return
        except:
            with _stats_lock:
                _api_errors += 1
            return
        
        # iDRAC 6 Detection
        response = session.get(f'https://{ip}/login.html', verify=False, timeout=CONFIG["timeout"])
        if response and response.status_code == 200:
            if 'idrac6' in response.text.lower():
                hostname = ""
                for line in response.text.split('\n'):
                    if 'var tmphostname' in line.lower():
                        hostname = line.split('"')[1].strip()
                        break
                
                output(f'[+] {ip}: {hostname} (iDRAC6, Firmware Unknown)')
                if export_enabled:
                    _lstToWrite.append(f'{ip};iDRAC6;;{hostname};Unknown\n')
                return
        
        # iDRAC 7/8 Detection
        response = session.get(f'https://{ip}/data?get=prodServerGen', verify=False, timeout=CONFIG["timeout"])
        if response and response.status_code == 200:
            idrac_version = 'iDRAC7' if '12g' in response.text.lower() else 'iDRAC8'
            
            # Get license
            resp_license = session.get(f'https://{ip}/data?get=prodClassName', verify=False, timeout=CONFIG["timeout"])
            license_type = resp_license.text.split(r'<prodClassName>')[1].split(r'</prodClassName>')[0] if resp_license.status_code == 200 else 'Unknown'
            
            # Get system info
            resp_info = session.get(f'https://{ip}/session?aimGetProp=hostname,gui_str_title_bar,OEMHostName,fwVersion,sysDesc', 
                                   verify=False, timeout=CONFIG["timeout"])
            
            if resp_info and resp_info.status_code == 200:
                info_json = json.loads(resp_info.text)['aimGetProp']
                hostname = info_json.get('hostname', 'Unknown')
                firmware = info_json.get('fwVersion', 'Unknown')
                system = info_json.get('sysDesc', 'Unknown')
                
                output(f'[+] {ip}: {hostname} ({system}, {idrac_version} {license_type}, Firmware v{firmware})')
                
                if export_enabled:
                    _lstToWrite.append(f'{ip};{idrac_version} {license_type};{system};{hostname};{firmware}\n')
                
                # Vulnerability checking
                if check_vulns:
                    check_vulnerabilities(ip, hostname, idrac_version, firmware, system, proxy, filter_mode)
                return
        
        # iDRAC 9 Detection
        response = session.get(f'https://{ip}/restgui/locale/strings/locale_str_en.json', verify=False, timeout=CONFIG["timeout"])
        if response and response.status_code == 200:
            data = response.json()
            if data.get('app_title') == 'iDRAC9':
                # Get system info
                resp_rest = session.get(f'https://{ip}/restgui/js/services/resturi.js', verify=False, timeout=CONFIG["timeout"])
                if resp_rest and resp_rest.status_code == 200:
                    # Extract BMC info endpoint
                    bmc_match = re.search(r'var BMC_INFO\s*=\s*"([^"]+)"', resp_rest.text)
                    if bmc_match:
                        bmc_endpoint = bmc_match.group(1)
                        resp_attrs = session.get(f'https://{ip}{bmc_endpoint}', verify=False, timeout=CONFIG["timeout"])
                        
                        if resp_attrs and resp_attrs.status_code == 200:
                            attrs = resp_attrs.json().get('Attributes', {})
                            hostname = attrs.get('iDRACName', 'Unknown')
                            firmware = attrs.get('FwVer', attrs.get('FirmwareVersion', 'Unknown'))
                            system = attrs.get('SystemModelName', 'Unknown')
                            license_type = attrs.get('License', 'Unknown')
                            
                            output(f'[+] {ip}: {hostname} ({system}, iDRAC9 {license_type}, Firmware v{firmware})')
                            
                            if export_enabled:
                                _lstToWrite.append(f'{ip};iDRAC9 {license_type};{system};{hostname};{firmware}\n')
                            
                            if check_vulns:
                                check_vulnerabilities(ip, hostname, 'iDRAC9', firmware, system, proxy, filter_mode)
                            return
                            
    except Exception as e:
        if verbose:
            output(f'[-] Error scanning {ip}: {str(e)}')
        with _stats_lock:
            _api_errors += 1

def check_vulnerabilities(ip, hostname, version, firmware, system, proxy, filter_mode):
    """Check for known vulnerabilities"""
    global _vulnerable_count
    
    vulnerabilities_found = []
    
    # Check CVE-2018-1207 (Critical)
    if 'iDRAC7' in version or 'iDRAC8' in version:
        try:
            # Parse firmware version
            fw_clean = firmware.replace('v', '')
            if '.' in fw_clean:
                parts = fw_clean.split('.')
                if len(parts) >= 2:
                    major = int(parts[0])
                    minor = int(parts[1])
                    
                    # Vulnerable versions: < 2.52.52
                    if major < 2 or (major == 2 and minor < 52):
                        is_vulnerable, exploit_url = verify_cve_2018_1207(ip, proxy)
                        
                        if is_vulnerable:
                            vuln_msg = f'  [!!] {ip} is CRITICALLY VULNERABLE to CVE-2018-1207 (RCE)'
                            if filter_mode and '[!!]' in vuln_msg:
                                print(vuln_msg)
                            elif not filter_mode:
                                print(vuln_msg)
                            
                            vulnerabilities_found.append({
                                'cve': 'CVE-2018-1207',
                                'severity': 'CRITICAL',
                                'exploit_url': exploit_url
                            })
        except Exception as e:
            pass
    
    # Check CVE-2019-1010279 (Medium)
    is_vulnerable, exploit_url = verify_cve_2019_1010279(ip, proxy)
    if is_vulnerable:
        vuln_msg = f'  [!] {ip} is vulnerable to CVE-2019-1010279 (Info Disclosure)'
        if filter_mode and '[!]' in vuln_msg:
            print(vuln_msg)
        elif not filter_mode:
            print(vuln_msg)
        
        vulnerabilities_found.append({
            'cve': 'CVE-2019-1010279',
            'severity': 'MEDIUM',
            'exploit_url': exploit_url
        })
    
    # Send Discord notifications
    for vuln in vulnerabilities_found:
        with _stats_lock:
            _vulnerable_count += 1
            _vulnerable_systems.append({
                'ip': ip,
                'hostname': hostname,
                'version': version,
                'firmware': firmware,
                'cve': vuln['cve'],
                'severity': vuln['severity'],
                'exploit_url': vuln['exploit_url']
            })
        
        send_discord_webhook(ip, hostname, version, firmware, 
                            vuln['cve'], vuln['exploit_url'], vuln['severity'])
        
        log_to_file(f"Vulnerable: {ip} - {vuln['cve']} ({vuln['severity']})", "WARNING")

def get_ips_from_target(target):
    """Parse IP addresses from various input formats"""
    ips = []
    
    if os.path.isfile(target):
        with open(target, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    ips.extend(expand_cidr(line))
    else:
        ips.extend(expand_cidr(target))
    
    return list(set(ips))  # Remove duplicates

def expand_cidr(cidr):
    """Expand CIDR notation to individual IPs"""
    ips = []
    
    # Single IP
    if '/' not in cidr:
        try:
            socket.inet_aton(cidr)
            ips.append(cidr)
        except:
            pass
        return ips
    
    # CIDR range
    try:
        from ipaddress import ip_network
        network = ip_network(cidr, strict=False)
        for ip in network.hosts():
            ips.append(str(ip))
    except:
        pass
    
    return ips

def send_scan_summary(total_ips):
    """Send final scan summary to Discord"""
    if not CONFIG["enable_discord"] or CONFIG["discord_webhook"] == "YOUR_WEBHOOK_URL_HERE":
        return
    
    try:
        elapsed = time.time() - _scan_start_time if _scan_start_time else 0
        
        # Group vulnerabilities by severity
        critical = [v for v in _vulnerable_systems if v['severity'] == 'CRITICAL']
        high = [v for v in _vulnerable_systems if v['severity'] == 'HIGH']
        medium = [v for v in _vulnerable_systems if v['severity'] == 'MEDIUM']
        
        embed = {
            "title": "📊 SCAN COMPLETED - Vulnerability Report",
            "color": 3447003,
            "fields": [
                {"name": "🎯 Target", "value": f"```{sys.argv[1] if len(sys.argv) > 1 else 'Unknown'}```", "inline": False},
                {"name": "🔍 Total Scanned", "value": f"```{_total_scanned}```", "inline": True},
                {"name": "⚠️ Vulnerable Found", "value": f"```{_vulnerable_count}```", "inline": True},
                {"name": "🔥 Critical", "value": f"```{len(critical)}```", "inline": True},
                {"name": "🟡 Medium", "value": f"```{len(medium)}```", "inline": True},
                {"name": "⏱️ Time Elapsed", "value": f"```{elapsed:.1f} seconds```", "inline": True},
                {"name": "📈 Scan Speed", "value": f"```{_total_scanned/elapsed:.1f} IPs/sec```", "inline": True}
            ],
            "footer": {"text": "Enhanced iDRAC Scanner - Security Report"},
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        # Add critical findings
        if critical:
            critical_list = "\n".join([f"• `{v['ip']}` - {v['cve']} ({v['version']})" for v in critical[:5]])
            if len(critical) > 5:
                critical_list += f"\n• ... and {len(critical) - 5} more"
            embed["fields"].append({"name": "🔥 CRITICAL FINDINGS", "value": critical_list, "inline": False})
        
        payload = {"username": "iDRAC Scanner", "embeds": [embed]}
        response = requests.post(CONFIG["discord_webhook"], json=payload, timeout=10)
        
        if response.status_code in [200, 204]:
            print("\n[✓] Summary report sent to Discord")
        else:
            print(f"\n[!] Failed to send summary: {response.status_code}")
            
    except Exception as e:
        print(f"\n[!] Error sending summary: {str(e)}")

def main():
    global _scan_start_time, _lstToWrite
    
    print_banner()
    
    # Parse command line arguments
    parser = optparse.OptionParser(usage="%prog [options] TARGET")
    parser.add_option('-t', '--threads', dest='threads', type='int', default=50,
                     help='Number of threads (default: 50)')
    parser.add_option('-p', '--proxy', dest='proxy', help='HTTP proxy (e.g., 127.0.0.1:8080)')
    parser.add_option('-o', '--output', dest='output', help='Output file for results')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', help='Verbose output')
    parser.add_option('-f', '--filter', action='store_true', dest='filter', 
                     help='Only show vulnerability findings')
    parser.add_option('--no-vuln', action='store_false', dest='check_vulns', default=True,
                     help='Disable vulnerability checking')
    parser.add_option('--no-discord', action='store_false', dest='discord', default=True,
                     help='Disable Discord notifications')
    parser.add_option('--webhook', dest='webhook', help='Custom Discord webhook URL')
    
    options, args = parser.parse_args()
    
    # Update configuration
    if options.webhook:
        CONFIG["discord_webhook"] = options.webhook
    if options.no_discord:
        CONFIG["enable_discord"] = False
    
    if not args:
        target = input("[?] Enter target (IP, CIDR, or file): ").strip()
        if not target:
            target = "192.168.1.0/24"
    else:
        target = args[0]
    
    # Get IP list
    print(f"[*] Resolving targets from: {target}")
    ip_list = get_ips_from_target(target)
    
    if not ip_list:
        print("[!] No valid IP addresses found!")
        sys.exit(1)
    
    print(f"[*] Loaded {len(ip_list)} IP addresses for scanning")
    print(f"[*] Using {options.threads} threads")
    print(f"[*] Timeout: {CONFIG['timeout']} seconds")
    print(f"[*] Discord notifications: {'ON' if CONFIG['enable_discord'] else 'OFF'}")
    print(f"[*] Vulnerability checking: {'ON' if options.check_vulns else 'OFF'}")
    print()
    
    # Prepare for scanning
    _lstToWrite = []
    _scan_start_time = time.time()
    
    # Create thread pool
    pool = ThreadPool(options.threads)
    
    # Prepare arguments
    args_list = zip(ip_list, 
                   repeat(options.verbose),
                   repeat(options.proxy),
                   repeat(options.check_vulns),
                   repeat(bool(options.output)),
                   repeat(options.filter))
    
    # Run scan
    print("[*] Starting scan...\n")
    try:
        pool.map(fingerprint_idrac, args_list)
    except KeyboardInterrupt:
        print("\n\n[!] Scan interrupted by user!")
        pool.terminate()
    finally:
        pool.close()
        pool.join()
    
    # Print final statistics
    elapsed = time.time() - _scan_start_time
    print(f"\n\n{'='*60}")
    print("SCAN COMPLETE")
    print(f"{'='*60}")
    print(f"Total IPs scanned: {_total_scanned}")
    print(f"Vulnerable systems: {_vulnerable_count}")
    print(f"API errors: {_api_errors}")
    print(f"Time elapsed: {elapsed:.1f} seconds")
    print(f"Scan speed: {_total_scanned/elapsed:.1f} IPs/second")
    
    # Print vulnerable systems
    if _vulnerable_systems:
        print(f"\n{'='*60}")
        print("VULNERABLE SYSTEMS")
        print(f"{'='*60}")
        
        for idx, vuln in enumerate(_vulnerable_systems, 1):
            print(f"\n[{idx}] {vuln['ip']}")
            print(f"    Hostname: {vuln['hostname']}")
            print(f"    Version: {vuln['version']}")
            print(f"    Firmware: {vuln['firmware']}")
            print(f"    CVE: {vuln['cve']} ({vuln['severity']})")
            print(f"    Exploit: {vuln['exploit_url']}")
        
        print(f"\n[!] URGENT: {_vulnerable_count} vulnerable systems require immediate patching!")
    else:
        print(f"\n[+] No vulnerable systems detected.")
    
    # Save results to file
    if options.output and _lstToWrite:
        with open(options.output, 'w') as f:
            f.writelines(_lstToWrite)
        print(f"\n[✓] Results saved to: {options.output}")
    
    # Send summary to Discord
    if CONFIG["enable_discord"] and CONFIG["discord_webhook"] != "YOUR_WEBHOOK_URL_HERE":
        print("\n[*] Sending summary to Discord...")
        send_scan_summary(len(ip_list))
    
    print("\n[*] Scan finished!")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[!] Program terminated by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n[!] Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
