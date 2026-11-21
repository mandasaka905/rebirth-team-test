"""Compare declared business structures and scenarios without picking a winner."""
from copy import deepcopy
from .domain import ValidationError,nonempty,money,amount
from .linkage import validate_refs
from .planning import assess_models
from .model_drafts import assess_draft,validate_draft

STRUCTURE=('customer_segment','customer_problem','value_proposition','channel','fulfilment','revenue_method','key_resources','required_skills')


def compare(ledger,args):
    if not isinstance(args,dict):raise ValidationError('模式比较参数须为对象')
    scope=nonempty(args.get('scope'),'比较口径')
    ref=args.get('baseline_ref');validate_refs([ref])
    baseline=next((m for m in ledger.get('business_models',[]) if m['id']==ref['id'] and m.get('version',1)==ref['version'] and m['status']=='current'),None)
    if baseline is None:raise ValidationError('须选择当前账目中存在且版本一致的现行经营模式')
    drafts=args.get('drafts')
    if not isinstance(drafts,list) or not 1<=len(drafts)<=4:raise ValidationError('每次比较1至4个候选模式草案')
    seen=set();rows=[]
    def row(model,assessment,draft=None):
        unit=assessment['unit_contribution'];fixed=model['fixed_cost'];orders=model.get('assumed_orders')
        scenarios=[]
        for name,n in [('zero_orders',0),('half_declared',orders//2 if orders is not None else None),('declared',orders)]:
            value=None
            if n is not None and fixed is not None and (n==0 or unit is not None):
                value=amount((money(unit,negative=True)*n if n else money('0.00'))-money(fixed))
            scenarios.append({'scenario':name,'orders':n,'period_contribution':value})
        changes=[{'field':k,'before':baseline[k],'after':model[k]} for k in STRUCTURE if baseline[k]!=model[k]] if draft else []
        return {'kind':'candidate' if draft else 'baseline','draft_id':draft['id'] if draft else None,
                'draft_version':draft['version'] if draft else None,'model':deepcopy(model),'assessment':assessment,
                'structural_field_changes':changes,'structural_change_notice':'字段变化只用于核对设计，不自动证明商业创新或客户需求。',
                'scenarios':scenarios,'comparable_period':model['period_days']==baseline['period_days']}
    base=assess_models({**ledger,'business_models':[baseline]})['models'][0]
    rows.append(row(baseline,base))
    for raw in drafts:
        draft=validate_draft(deepcopy(raw))
        if draft['id'] in seen:raise ValidationError('同一模式草案的不同版本不可作为两个独立候选重复比较')
        seen.add(draft['id']);ev=assess_draft(ledger,draft);r=row(draft['model'],ev['assessment'],draft)
        r['blockers']=ev['blockers'];r['warnings']=ev['warnings'];r['perspectives']=ev['perspectives']
        r['evidence_ids']=list(draft['evidence_ids']);r['validation_plan']=draft['validation_plan']
        if not r['structural_field_changes']:r['warnings'].append('客户、渠道、履约等结构字段未改变；目前只体现数值或文案调整。')
        rows.append(r)
    return {'baseline_ref':deepcopy(ref),'scope':scope,'scope_confirmed':False,'rows':rows,
            'same_period':all(r['comparable_period'] for r in rows),'selected_winner':None,
            'notice':'按声明口径比较经营方式，不预测订单或自动选出最优模式。期间贡献不扣初始投入；投入不重复当费用。回款、库存和必要付款须在具体行动方案中另做逐日核查。'}


def for_report(ledger,drafts):
    current=[m for m in ledger.get('business_models',[]) if m['status']=='current']
    if not drafts:return None
    if len(current)!=1:return {'rows':[],'notice':'请明确登记一个现行经营模式作为比较基准；已有草案仍可分别审阅。'}
    baseline=current[0]
    return compare(ledger,{'baseline_ref':{'id':baseline['id'],'version':baseline.get('version',1)},
                   'drafts':drafts,'scope':'同店已登记的经营方式；每单商品与服务范围仍须商户核对，不能直接据此排名。'})
