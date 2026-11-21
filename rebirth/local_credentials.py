"""Read explicitly local credentials without echoing their values."""
from pathlib import Path

FIELDS={'统筹':('coordinator','AGENTARTS_COORDINATOR_KEY'),
    '库存':('inventory','AGENTARTS_INVENTORY_KEY'),
    '客源':('customer','AGENTARTS_CUSTOMER_KEY'),
    '资金':('cash','AGENTARTS_CASH_KEY')}


def read_keys(path, *, roles=None):
    values={}
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():continue
        name,sep,value=line.partition('=');name=name.strip();value=value.strip()
        if not sep or name not in FIELDS:raise ValueError('密钥文件格式不正确，请保留四行的中文名称和等号')
        if name in values:raise ValueError(name+'出现重复行')
        values[name]=value
    result={}
    for name,(role,env) in FIELDS.items():
        if roles is not None and role not in roles:continue
        value=values.get(name,'')
        if value.lower().startswith('bearer '):value=value[7:].strip()
        if not value or '在这里粘贴' in value:raise ValueError(name+'密钥尚未填入')
        if any(ch.isspace() for ch in value):raise ValueError(name+'密钥包含空格或换行')
        result[env]=value
    return result
