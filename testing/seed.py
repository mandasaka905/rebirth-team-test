"""A fresh, explicitly synthetic usability sandbox; never copies developer databases."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import json
from rebirth.store import Store
from rebirth.domain import ValidationError


class TestStore(Store):
    def put_ledger(self, data):
        if data.get('synthetic') is not True:
            raise ValidationError('队员试用包只保存合成练习资料，请保持“合成测试数据”标记')
        return super().put_ledger(data)


def prepare(path, project):
    store = TestStore(path)
    if store.merchants():
        return store
    fixture = json.loads((Path(project)/'examples/planning.synthetic.json').read_text(encoding='utf-8'))
    for ident, name in [('try_a', '练习甲店（合成服装零售）'), ('try_b', '练习乙店（合成服装零售）')]:
        ledger = deepcopy(fixture)
        ledger.update(merchant_id=ident, name=name, synthetic=True)
        store.put_ledger(ledger)
    today = date.today().isoformat()
    r = store.support_request('try_a', dict(category='digital', problem='合成示范：不知如何核对一种商品的库存', goal='合成示范：独立整理一种商品的清单', availability='示范时段，不是真实预约', requested_on=today, next_on=today, local_consent=True, aggregate_consent=True))
    common = dict(request_id=r['id'], occurred_on=today, notes='预置合成示范，不对应实际人员、经营或受益', confirmed=True)
    p = store.support_event('try_a', {**common, 'expected_id':r['id'], 'action':'plan','helper_alias':'合成协助者','step':'只选一种商品，分列实盘与原单','planned_minutes':15,'next_on':today})
    v = store.support_event('try_a', {**common, 'expected_id':p['id'], 'action':'visit','actual_minutes':10,'extra_spend':'0','blockers':'合成示范：仍有原单缺失','next_on':today})
    store.support_event('try_a', {**common, 'expected_id':v['id'], 'action':'review','outcome':'partial','merchant_voice':'合成示范：学会一部分，缺单还没解决','next_choice':'先找原单，再做下一步'})
    store.experience_share('try_a', dict(request_id=r['id'],title='合成示范：先盘清一种商品',industry='retail',problem='库存记录杂乱，不知道从哪里开始',steps=['只选一种有原单的商品，先核对实盘数量','把缺单和不确定的数字单列，暂不补造'],fits='有原单和可用于核对的短暂空闲',stop_when='原单缺失或口径不一致时先停下',lesson='合成练习，仅解决一部分；缺单仍需人工补证，不代表经营改善',share_consent=True,anonymous_checked=True))
    return store
