"""Generate reviewable deployment templates without changing system configuration."""
import argparse
from pathlib import Path
import re


def generate(domain, output, *, open_registration=False, demo_only=False, registration_limit=30):
    if not re.fullmatch(r'(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}',domain):
        raise ValueError('请填域名，不含https、端口或路径')
    domain=domain.lower();folder=Path(output);folder.mkdir(parents=True,exist_ok=False)
    if not 1<=registration_limit<=200:raise ValueError('测试名额应为1至200')
    flags=(' --open-registration' if open_registration else '')+(' --demo-only' if demo_only else '')+f' --registration-limit {registration_limit}'
    (folder/'rebirth.Caddyfile').write_text(f'''# Import this additional site block; do not replace configuration for other websites.
{domain} {{
    encode gzip
    request_body {{
        max_size 1MB
    }}
    header {{
        Strict-Transport-Security "max-age=31536000"
        X-Content-Type-Options nosniff
        Referrer-Policy no-referrer
    }}
    reverse_proxy 127.0.0.1:8080
}}
''',encoding='utf-8')
    (folder/'rebirth.service').write_text(f'''[Unit]
Description=Rebirth small merchant service
After=network.target

[Service]
Type=simple
User=rebirth
Group=rebirth
WorkingDirectory=/opt/rebirth
ExecStart=/opt/rebirth/.venv/bin/python -m rebirth.hosted --data-dir /var/lib/rebirth serve --origin https://{domain} --port 8080{flags}
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/rebirth

[Install]
WantedBy=multi-user.target
''',encoding='utf-8')
    (folder/'rebirth-backup.service').write_text('''[Unit]
Description=Backup Rebirth account and business databases

[Service]
Type=oneshot
User=rebirth
Group=rebirth
WorkingDirectory=/opt/rebirth
ExecStart=/opt/rebirth/.venv/bin/python -m rebirth.hosted --data-dir /var/lib/rebirth backup --output-root /var/backups/rebirth
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/rebirth /var/backups/rebirth
''',encoding='utf-8')
    (folder/'rebirth-backup.timer').write_text('''[Unit]
Description=Daily backup for Rebirth

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
''',encoding='utf-8')
    return folder


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--domain',required=True);parser.add_argument('--output',required=True);parser.add_argument('--open-registration',action='store_true');parser.add_argument('--demo-only',action='store_true');parser.add_argument('--registration-limit',type=int,default=30);args=parser.parse_args()
    print(generate(args.domain,args.output,open_registration=args.open_registration,demo_only=args.demo_only,registration_limit=args.registration_limit))
