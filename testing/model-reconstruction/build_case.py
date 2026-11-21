"""Constructed comparison fixture, not an AI-generated or real merchant case."""
from pathlib import Path
from copy import deepcopy
import json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from rebirth.model_comparison import compare


def fixture():
    l=json.loads((ROOT/'examples/planning.synthetic.json').read_text(encoding='utf-8'))
    baseline=deepcopy(l['business_models'][0]);baseline.update(period_days=14,unit_revenue='70.00',unit_cost='40.00',
        fixed_cost='200.00',investment='0.00',assumed_orders=20,costs_confirmed=False,
        source_note='构造的现货单件增量试验假设；不含原店租与原人工，不是市场报价或全店利润')
    l['business_models']=[baseline]
    def component(id,label,value):return {'id':id,'label':label,'amount':value,'basis':'构造测算假设，待核实','basis_kind':'assumption'}
    def draft(id,name):
        m=deepcopy(baseline);m.update(id=id,status='candidate',name=name)
        return {'id':id,'version':1,'owner':'customer','model':m,'rationale':'比较获客与交付结构，订单量不是预测',
            'assumptions':['全部数字为构造假设','比较只覆盖声明的增量成本'],
            'supply_requirements':[{'sku':l['products'][0]['sku'],'quantity':20}],
            'validation_plan':'先记录真实询问与可接受的交付时段，再核实费用、工时和商品范围；通过后另建行动方案核算现金时序',
            'evidence_ids':['fixture_not_agent_evidence']}
    pickup=draft('pickup','预约到店自提候选')
    pickup['model'].update(channel='自愿咨询后的预约入口',fulfilment='约定时段到店自提',revenue_method='交付后按件结算',
        unit_revenue='68.00',unit_cost='41.00',fixed_cost='60.00',investment='80.00',weekly_hours=4,
        unit_cost_components=[component('goods','商品','40.00'),component('pack','包装','1.00')])
    delivery=draft('delivery','即时配送候选')
    delivery['model'].update(channel='第三方平台获客，条件未核实',fulfilment='接单后即时配送',revenue_method='平台代收后结算，时序待核实',
        unit_cost=None,fixed_cost='300.00',investment='300.00',weekly_hours=10,
        required_skills='接待\n库存核对\n配送协调',unit_cost_components=[component('goods','商品','40.00'),
        component('pack','包装','1.00'),component('platform','平台费用',None),component('delivery','配送','7.00')])
    revised=deepcopy(delivery);revised.update(version=2,rationale='构造修订：放弃即时配送，改为预约集中自提以检验交付能力')
    revised['model'].update(name='平台展示后预约集中自提候选',fulfilment='约定时段集中自提，不提供即时配送',
        channel='平台展示规则待核实，先限自愿咨询范围',revenue_method='到店交付后结算',weekly_hours=4,
        required_skills=baseline['required_skills'],unit_cost='41.00',fixed_cost='100.00',investment='100.00',
        unit_cost_components=[component('goods','商品','40.00'),component('pack','包装','1.00')])
    scope='同店同款现货、每单一件、14天；只计声明的增量成本，不含原店租与原人工；口径待商户核实'
    args={'baseline_ref':{'id':baseline['id'],'version':baseline['version']},'drafts':[pickup,delivery],'scope':scope}
    return l,args,revised


if __name__=='__main__':
    l,args,revised=fixture();before=compare(l,args);after=compare(l,{**args,'drafts':[args['drafts'][0],revised]})
    assert before['rows'][2]['assessment']['unit_contribution'] is None and before['rows'][2]['blockers']
    assert not after['rows'][2]['blockers'] and after['selected_winner'] is None
    result={'kind':'constructed_local_comparison_not_ai_run','ledger':l,'arguments':args,'before':before,'revised_draft':revised,'after':after,'cloud_calls':0}
    (Path(__file__).parent/'case-and-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'constructed_case_verified':True,'alternatives':2,'unknown_cost_retained':True,'automatic_winner':False,'cloud_calls':0}))
