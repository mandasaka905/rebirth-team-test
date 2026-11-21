"""Optional per-order cost decomposition. Recorded amounts are not verified quotes."""
from .domain import ValidationError,money,nonempty


def validate(model):
    rows=model.get('unit_cost_components')
    if rows is None:return
    if not isinstance(rows,list) or not 1<=len(rows)<=12:
        raise ValidationError('每单成本分项须为1至12项')
    total=money('0.00');seen=set();unknown=False
    for row in rows:
        if not isinstance(row,dict):raise ValidationError('每单成本分项须为对象')
        for field in ('id','label','basis'):nonempty(row.get(field),'成本分项'+field)
        if row['id'] in seen:raise ValidationError('每单成本分项编号重复')
        seen.add(row['id'])
        if row.get('basis_kind') not in ('assumption','merchant_record'):
            raise ValidationError('每单成本依据须区分假设与商户记录')
        if row['basis_kind']=='assumption' and model['costs_confirmed']:
            raise ValidationError('假设的每单成本不能标为已核实')
        if row.get('amount') is None:unknown=True
        else:total+=money(row['amount'])
    if unknown:
        if model.get('unit_cost') is not None:raise ValidationError('存在未知成本分项时，每单总成本须留空，不能当零相加')
        if model['costs_confirmed']:raise ValidationError('存在未知成本分项时不能确认费用齐全')
    elif model.get('unit_cost') is None or money(model['unit_cost'])!=total:
        raise ValidationError('每单成本分项合计须与每单总成本一致')
