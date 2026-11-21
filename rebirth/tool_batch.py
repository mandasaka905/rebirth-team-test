"""Bounded read-only requests; each result retains its own audited evidence."""
from .domain import ValidationError
from .tools import TOOL_ARGS


def expand(name, arguments):
    if name != 'read_tools':
        return [(name, arguments)]
    if not isinstance(arguments,dict) or set(arguments)!={'calls'}:
        raise ValidationError('批量只读取证须提供calls列表')
    calls=arguments['calls']
    if not isinstance(calls,list) or not 1<=len(calls)<=8:
        raise ValidationError('一次批量取证应包含1至8个只读工具')
    result=[]
    for call in calls:
        if not isinstance(call,dict) or set(call)!={'name','arguments'} or not isinstance(call['name'],str) or call['name'] not in TOOL_ARGS or not isinstance(call['arguments'],dict):
            raise ValidationError('批量取证只允许已登记的只读工具，不允许嵌套、网络地址或执行指令')
        result.append((call['name'],call['arguments']))
    return result
