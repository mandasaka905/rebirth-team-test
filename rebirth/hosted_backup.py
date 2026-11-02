"""SQLite online backup; never copy a live database without its WAL transactions."""
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import sqlite3


def backup_all(source, destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination==source or source in destination.parents:
        raise ValueError('备份目录必须位于数据目录外面')
    if not (source/'accounts.sqlite3').is_file():raise ValueError('找不到账号数据库')
    destination.mkdir(parents=True,exist_ok=False,mode=0o700)
    def copy_database(original,target):
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        src=sqlite3.connect(f'{original.as_uri()}?mode=ro',uri=True)
        out=sqlite3.connect(target)
        try:
            src.backup(out)
            if out.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('备份完整性检查未通过')
        finally:src.close();out.close()
    copy_database(source/'accounts.sqlite3',destination/'accounts.sqlite3')
    db=sqlite3.connect(destination/'accounts.sqlite3')
    try:
        user_ids=[r[0] for r in db.execute('SELECT id FROM users')]
        # Restoring backups must not revive old login cookies.
        db.execute('DELETE FROM sessions');db.execute('DELETE FROM attempts');db.commit()
    finally:db.close()
    copied=0
    for uid in user_ids:
        if not re.fullmatch('[a-f0-9]{32}',uid):raise ValueError('账号路径不正确')
        rel=Path('shops')/uid/'business.sqlite3'
        if (source/rel).exists():copy_database(source/rel,destination/rel);copied+=1
    notice={'created_at':datetime.now(timezone.utc).isoformat(),'accounts':len(user_ids),'business_databases':copied,'sessions_revoked_in_backup':True,'scope':'Each isolated account database is transaction-consistent. There is no cross-account shared business transaction.'}
    (destination/'backup-info.json').write_text(json.dumps(notice,indent=2),encoding='utf-8')
    return notice
