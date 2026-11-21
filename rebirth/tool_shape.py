"""Normalize explicit parameter aliases; never infer a missing tool or argument."""
from copy import deepcopy
from .domain import ValidationError

def normalize(action):
    a=deepcopy(action)
    if 'parameters' in a:
        if 'arguments' in a:raise ValidationError('arguments与parameters同时出现，参数有歧义')
        a['arguments']=a.pop('parameters')
    if a.get('name')=='read_tools':
        if 'calls' in a:
            if 'arguments' in a:raise ValidationError('顶层calls与arguments同时出现')
            a['arguments']={'calls':a.pop('calls')}
        args=a.get('arguments')
        if isinstance(args,dict) and 'limit' in args:
            if type(args['limit']) is not int or args['limit']!=8 or 'calls' not in args:
                raise ValidationError('批量请求limit仅可为说明中的固定上限8，且必须明确提供calls')
            args.pop('limit')  # Redundant advertised metadata; server still enforces 1..8.
        if isinstance(args,dict) and set(args)=={'tools'}:args['calls']=args.pop('tools')
        if isinstance(args,dict) and isinstance(args.get('calls'),list):
            for call in args['calls']:
                if not isinstance(call,dict):continue
                for alias,target in [('tool','name'),('parameters','arguments'),('params','arguments')]:
                    if alias in call:
                        if target in call:raise ValidationError('批量工具参数别名重复，无法确定意图')
                        call[target]=call.pop(alias)
    return a,a!=action
