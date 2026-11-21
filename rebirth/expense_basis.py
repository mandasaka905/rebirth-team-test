"""Optional expense detail: arithmetic consistency is not proof of a quote."""
from .domain import ValidationError, money, integer, nonempty


def validate(proposal):
    rows=proposal.get('expense_breakdown')
    if rows is None:return
    if not isinstance(rows,list) or not 1<=len(rows)<=20:
        raise ValidationError('费用明细应为1至20项')
    total=money('0.00');seen=set()
    for row in rows:
        if not isinstance(row,dict):raise ValidationError('每项费用须有名称、数量、单价和依据')
        nonempty(row.get('id'),'费用编号');nonempty(row.get('label'),'费用名称')
        if row['id'] in seen:raise ValidationError('费用编号不能重复')
        seen.add(row['id'])
        integer(row.get('quantity'),'费用数量',1000000)
        cost=money(row.get('unit_cost'))*row['quantity']
        if cost!=money(row.get('amount')):raise ValidationError('费用数量乘单价与小计不一致')
        nonempty(row.get('basis'),'费用依据')
        if row.get('basis_kind') not in ('assumption','merchant_record'):
            raise ValidationError('费用依据须区分构造假设和商户记录')
        if row['basis_kind']=='assumption' and proposal['costs_confirmed']:
            raise ValidationError('假设费用不能标为已经核实')
        total+=cost
    if total!=money(proposal['upfront_cost'])+money(proposal['other_cost']):
        raise ValidationError('费用明细合计须等于前期支出与其他固定支出，不包括单件成交费用或新增采购')
