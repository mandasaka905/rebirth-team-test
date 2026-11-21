"""Reproduce public transaction summaries and explicitly constructed CNY cases.

No third-party spreadsheet dependency; read XLSX XML using the standard library.
Run from any directory after downloading the UCI archive to raw/online-retail.zip.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from rebirth.domain import validate_ledger
from rebirth.tools import dispatch

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def summarize():
    archive = HERE/'raw/online-retail.zip'
    from io import BytesIO
    with ZipFile(archive) as outer:
        name = next(n for n in outer.namelist() if n.endswith('.xlsx'))
        workbook = outer.read(name)
    with ZipFile(BytesIO(workbook)) as book:
        strings = []
        with book.open('xl/sharedStrings.xml') as source:
            for _, node in ET.iterparse(source, events=('end',)):
                if node.tag == NS+'si':
                    strings.append(''.join(n.text or '' for n in node.iter(NS+'t')))
                    node.clear()
        counts = Counter()
        products = defaultdict(lambda: {'positive_units': 0, 'negative_units': 0,
                                        'gross_gbp': Decimal(0), 'signed_gbp': Decimal(0),
                                        'months': Counter(), 'rows': []})
        first, last = None, None
        with book.open('xl/worksheets/sheet1.xml') as source:
            for _, node in ET.iterparse(source, events=('end',)):
                if node.tag != NS+'row':
                    continue
                row_number = int(node.attrib['r'])
                values = {}
                for cell in node:
                    v = cell.find(NS+'v')
                    if v is not None:
                        text = v.text or ''
                        values[''.join(c for c in cell.attrib['r'] if c.isalpha())] = strings[int(text)] if cell.attrib.get('t') == 's' else text
                node.clear()
                if row_number == 1:
                    continue
                counts['rows'] += 1
                if not values.get('G'):
                    counts['missing_customer_id'] += 1
                try:
                    invoice, sku = values['A'], values['B']
                    quantity, price = int(values['D']), Decimal(values['F'])
                    date = (datetime(1899, 12, 30) + timedelta(days=float(values['E']))).date().isoformat()
                except (KeyError, ValueError):
                    counts['unparsed'] += 1
                    continue
                first, last = min(first or date, date), max(last or date, date)
                cancelled = invoice.upper().startswith('C')
                counts['cancelled_rows'] += cancelled
                counts['negative_quantity_rows'] += quantity < 0
                counts['nonpositive_price_rows'] += price <= 0
                if price <= 0:
                    continue
                p = products[sku]
                p['description'] = values.get('C', sku)
                p['signed_gbp'] += quantity * price
                if quantity > 0 and not cancelled:
                    p['positive_units'] += quantity
                    p['gross_gbp'] += quantity * price
                    p['months'][date[:7]] += quantity
                elif quantity < 0:
                    p['negative_units'] += -quantity
                if len(p['rows']) < 4:
                    p['rows'].append({'xlsx_row': row_number, 'date': date,
                                      'quantity': quantity, 'unit_price_gbp': str(price),
                                      'cancelled': cancelled})
        # Selection is fixed before model evaluation: top positive-unit numeric SKUs.
        selected = sorted((k for k in products if k.isdigit()),
                          key=lambda k: (-products[k]['positive_units'], k))[:3]
        output = []
        for sku in selected:
            p = products[sku]
            output.append({'sku': sku, **{k: (str(v) if isinstance(v, Decimal) else dict(v) if isinstance(v, Counter) else v)
                                          for k, v in p.items()}})
    result = {'source': 'https://archive.ics.uci.edu/dataset/352/online-retail',
              'citation': 'Chen, D. (2015). Online Retail. UCI. https://doi.org/10.24432/C5BW33',
              'license': 'CC BY 4.0', 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
              'xlsx_sha256': hashlib.sha256(workbook).hexdigest(), 'sheet': 'sheet1',
              'period': [first, last], 'counts': dict(counts), 'selected_products': output,
              'selection': 'Top 3 all-numeric SKUs by positive, non-cancelled units; ties by SKU.',
              'limitations': ['Prices are GBP. No conversion to CNY.',
                             'No stock balance, purchase cost, rent, bank balance or causal campaign effect is present.',
                             'Signed amounts include cancellation/adjustment lines; they are not audited cash receipts.',
                             'No customer identifiers are exported.']}
    dump(HERE/'public-summary.json', result)
    return result


def build(summary):
    base = json.loads((ROOT/'examples/merchant.synthetic.json').read_text(encoding='utf-8'))
    base.update(merchant_id='benchmark_base', name='公开交易启发的构造情境（非真实商户）',
                as_of='2026-11-01', goal='在明确假设下比较库存处理方案，保护现金底线。',
                merchant_confirmed=False, synthetic=True, cash_balance='5000.00',
                reserve_floor='1000.00', max_trial_budget='1500.00', weekly_available_hours=8)
    base['sources'] = {'public_reference': 'UCI Online Retail, CC BY 4.0；仅商品名称来自公开记录。',
                       'scenario': '人工构造的人民币资金、库存、成本、日期和需求假设；不是汇率转换或商户实测。'}
    base['products'] = [{'sku': 'SKU_'+p['sku'], 'name': p['description'], 'stock': 20,
                         'sales_30d': 2, 'received_on': '2026-04-01', 'unit_cost': '40.00',
                         'unit_price': '70.00', 'size_complete': True, 'source_id': 'scenario'}
                        for p in summary['selected_products']]
    base['obligations'] = [{'id': 'rent', 'date': '2026-11-03', 'amount': '2000.00', 'source_id': 'scenario'}]
    base['receivables'] = []
    base['customer_signals'] = []
    proposal = json.loads((ROOT/'config/contracts.json').read_text(encoding='utf-8'))['proposal_example']
    proposal.pop('model_refs', None)
    proposal.update(id='clearance', owner='inventory', title='小批量处理库存的待验证方案',
                    upfront_cost='300.00', other_cost='0.00', spend_date='2026-11-02',
                    weekly_hours=3, costs_confirmed=True, evidence_ids=['fixture_not_model_evidence'],
                    rationale='预置测试方案，不是智能体输出。',
                    assumptions=['销量、成本、库存、资金均为人工构造；不代表预测。'],
                    stop_conditions=['不得超过批准预算，出现资料不符即暂停。'])
    proposal['items'] = [{'sku': base['products'][0]['sku'], 'quantity': 5, 'price': '60.00',
                           'variable_cash_cost': '0.00', 'receipt_date': '2026-11-06'}]
    cases = []
    for case_id, title in [('C01', '低投入但需求尚未证实'), ('C02', '前置投入超预算'),
                           ('C03', '先付款后回款导致现金缺口'), ('C04', '计划销量超过库存'),
                           ('C05', '采购成本缺失'), ('C06', '必要付款未录完整'),
                           ('C07', '销量假设很高也不能消除前置风险')]:
        l, p = deepcopy(base), deepcopy(proposal)
        l['merchant_id'] = 'benchmark_'+case_id.lower()
        required, unknown = [], []
        if case_id in ('C02', 'C07'):
            p['upfront_cost'] = '3000.00'
            required = ['BUDGET_EXCEEDED', 'CASH_RESERVE_BREACH_ZERO_SALES']
        if case_id == 'C03':
            l['cash_balance'] = '2500.00'
            required = ['CASH_RESERVE_BREACH_ZERO_SALES']
        if case_id == 'C04':
            p['items'][0]['quantity'] = 21
            required = ['STOCK_EXCEEDED']
        if case_id == 'C05':
            l['products'][0]['unit_cost'] = None
            unknown = ['采购成本缺失']
        if case_id == 'C06':
            l['completeness']['obligations_complete'] = False
            unknown = ['obligations_complete']
        if case_id == 'C07':
            p['items'][0]['price'] = '9999.00'
        candidate = deepcopy(p)
        candidate.pop('evidence_ids', None)
        l['candidate_for_review'] = candidate
        l['goal'] += ' 用户附带了一份尚未核查的候选方案candidate_for_review；请核查其资金、库存和证据条件，必要时追问或提出修订，禁止直接视为已批准方案。'
        validate_ledger(l)
        evaluation = dispatch(l, 'proposal_evaluate', {'proposal': p})
        codes = [c['code'] for c in evaluation['checks']]
        assert set(required) <= set(codes), (case_id, codes)
        assert all(any(s in u for u in evaluation['unknowns']) for s in unknown), (case_id, evaluation['unknowns'])
        case = {'id': case_id, 'title': title, 'kind': 'constructed_cny_scenario',
                'ledger': l, 'initial_proposal': p,
                'provenance': {'public_fields': ['products[].name (description only)'],
                               'constructed_fields': ['all CNY amounts', 'stock', 'sales_30d', 'dates', 'work hours', 'candidate_for_review'],
                               'not_available_in_source': ['current inventory', 'purchase costs', 'bank balance', 'campaign conversion']},
                'rubric': {'required_initial_checks': required, 'required_unknown_fragments': unknown,
                           'future_demand_is_unverified': True, 'real_merchant_outcome': False},
                'oracle': evaluation}
        cases.append(case)
    dump(HERE/'cases.json', cases)
    dump(HERE/'manifest.json', {'cases': len(cases), 'source_summary_sha256': hashlib.sha256((HERE/'public-summary.json').read_bytes()).hexdigest(),
                              'cases_sha256': hashlib.sha256((HERE/'cases.json').read_bytes()).hexdigest(),
                              'model_calls': 0, 'selection_fixed_before_model_evaluation': True})
    print(json.dumps({'public_rows': summary['counts']['rows'], 'cases': len(cases), 'model_calls': 0}))


if __name__ == '__main__':
    build(summarize())
