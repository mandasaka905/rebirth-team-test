"""Versioned, evidence-checked collaboration contracts for new analysis runs."""
import hashlib
import json
from .domain import ValidationError

ROLES = ('inventory', 'customer', 'cash')
FOCUS = {'inventory': '商品可售性、库存与供应时序',
         'customer': '客户需求证据、渠道与低成本验证',
         'cash': '必要付款、投入与回款时序、现金底线'}
PRIMARY = {'inventory': 'inventory_analyze', 'customer': 'customer_evidence', 'cash': 'cash_baseline'}


def stable_id(prefix, value):
    return prefix + hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 3000:
        raise ValidationError(label+'须为1至3000字的说明')


def refs(value, allowed):
    if not isinstance(value, list) or not value or not all(isinstance(x, str) for x in value) or not set(value) <= allowed:
        raise ValidationError('协作主张必须引用本角色、本阶段实际取得的工具证据')


def objection_id(role, objection):
    return stable_id('ob_', [role, objection['proposal_id'], objection['version'], objection['reason'], objection['request']])


def requirements(reviews):
    result = []
    for row in reviews:
        common = {'proposal_id': row['proposal_id'], 'version': row['version'], 'owner': row['owner']}
        if row.get('questions'):
            item = {**common, 'kind': 'missing_data', 'details': row['questions']}
            item['id'] = stable_id('req_', item)
            result.append(item)
        for kind, values in [('constraint', row.get('tool_checks', {}).get('checks', [])),
                             ('missing_data', row.get('tool_checks', {}).get('unknowns', []))]:
            if values:
                item = {**common, 'kind': kind, 'details': values}
                item['id'] = stable_id('req_', item)
                result.append(item)
        for objection in row.get('objections', []):
            item = {**common, 'kind': 'objection', 'details': objection}
            item['id'] = stable_id('req_', [common, objection['id']])
            result.append(item)
    return result


def validate(role, phase, result, observations, proposals, prior_reviews, required):
    allowed = {o['evidence_id'] for o in observations if 'value' in o}
    if role in ROLES:
        if phase != 'review' and not any(o.get('tool') == PRIMARY[role] for o in observations):
            raise ValidationError('专业角色须先调用本角色主工具取证：'+PRIMARY[role])
        if phase == 'investigate' and not any(o.get('tool') == 'data_readiness' for o in observations):
            raise ValidationError('调查阶段须调用data_readiness，逐项核对本角色已知资料缺口')
        assessment = result.get('assessment')
        if not isinstance(assessment, dict) or assessment.get('perspective') != role:
            raise ValidationError('专业角色须提交assessment，perspective必须为本角色')
        text(assessment.get('conclusion'), '专业判断')
        refs(assessment.get('evidence_ids'), allowed)
        from .knowledge_claims import validate as validate_knowledge_claims
        validate_knowledge_claims(assessment.get('knowledge_citations',[]),observations)
        for field in ('assumptions', 'limits'):
            values = assessment.get(field)
            if not isinstance(values, list) or not values:
                raise ValidationError('assessment.'+field+'须明确列出假设和判断边界')
            for item in values:
                text(item, field)
        missing = assessment.get('missing_data')
        if not isinstance(missing, list) or len(missing) > 12:
            raise ValidationError('assessment.missing_data须为至多12项的列表')
        for question in missing:
            if not isinstance(question, dict) or question.get('owner') not in (*ROLES, 'coordinator'):
                raise ValidationError('补证问题须指定负责核查的专业角色')
            for field in ('question', 'why_needed', 'completion_condition'):
                text(question.get(field), '补证'+field)
            refs(question.get('evidence_ids'), allowed)
        if phase == 'investigate':
            checks = [o for o in observations if o.get('tool') == 'data_readiness']
            expected = {q['id'] for o in checks for q in o['value']['questions'] if q['owner'] == role}
            reported = {q.get('field_id') for q in missing}
            if not expected <= reported:
                raise ValidationError('assessment.missing_data须覆盖data_readiness中的本角色field_id，不能漏掉已知缺口')
        for objection in result.get('objections', []):
            if objection.get('topic') not in ('inventory', 'demand', 'cash', 'data'):
                raise ValidationError('质询须注明topic：inventory、demand、cash或data')
            if objection.get('severity') not in ('blocking', 'needs_data'):
                raise ValidationError('质询须注明blocking或needs_data')
            text(objection.get('acceptance'), '解除质询的可检查条件')
            refs(objection.get('evidence_ids'), allowed)
        if phase == 'review':
            rows = result.get('proposal_reviews')
            if not isinstance(rows, list) or len(rows) != len(proposals):
                raise ValidationError('审查阶段必须逐一提交所有当前方案的proposal_reviews，不得漏审')
            expected = {(p['id'], p['version']) for p in proposals}
            seen = set()
            for review in rows:
                if not isinstance(review, dict):
                    raise ValidationError('每份方案审查必须为对象')
                key = (review.get('proposal_id'), review.get('version'))
                if key not in expected or key in seen or review.get('status') not in ('pass', 'needs_data', 'blocked'):
                    raise ValidationError('方案审查版本、状态或覆盖范围无效')
                seen.add(key)
                text(review.get('reason'), '审查理由')
                refs(review.get('evidence_ids'), allowed)
                targeted = {o['evidence_id'] for o in observations if o.get('tool') == 'proposal_evaluate'
                            and o.get('arguments', {}).get('proposal', {}).get('id') == key[0]
                            and o['arguments']['proposal'].get('version') == key[1]}
                if not set(review['evidence_ids']) & targeted:
                    raise ValidationError('每份方案审查须引用本阶段对该精确版本实际重算的工具证据')
                objections = [o for o in result.get('objections', []) if o['proposal_id'] == key[0]]
                if review['status'] == 'pass' and objections:
                    raise ValidationError('同一角色不能一边通过方案一边保留质询')
                if review['status'] != 'pass' and not objections:
                    raise ValidationError('未通过的审查须给出有依据的质询和解除条件')
                previous = [o for r in prior_reviews if r['proposal_id'] == key[0]
                            for o in r.get('objections', []) if o.get('from') == role]
                responses = review.get('responses', [])
                if isinstance(responses, list) and any(not isinstance(r, dict) for r in responses):
                    raise ValidationError('复审回应必须为对象')
                if not isinstance(responses, list) or {r.get('objection_id') for r in responses} != {o['id'] for o in previous} or len(responses) != len(previous):
                    raise ValidationError('复审须逐项回应本角色此前的质询，不得让异议静默消失')
                for response in responses:
                    if response.get('outcome') not in ('resolved', 'retained', 'needs_data'):
                        raise ValidationError('复审回应状态无效')
                    if review['status'] == 'pass' and response['outcome'] != 'resolved':
                        raise ValidationError('质询仍待处理时不得通过审查')
                    text(response.get('reason'), '复审回应理由')
                    refs(response.get('evidence_ids'), allowed)
        if phase == 'revise':
            owned = {p['id']: p for p in proposals if p['owner'] == role}
            foreign={p['id']:p for p in proposals if p['owner']!=role and any(row['proposal_id']==p['id'] and any(t['assignee']==role for t in row.get('coordination_tasks',[])) for row in prior_reviews)}
            responses = result.get('revision_responses')
            if isinstance(responses, list) and any(not isinstance(r, dict) for r in responses):
                raise ValidationError('修订回应必须为对象')
            if not isinstance(responses, list) or {r.get('proposal_id') for r in responses} != set(owned)|set(foreign):
                raise ValidationError('修订角色须逐项说明自己原方案如何处理，不能静默跳过')
            for pid,p in foreign.items():
                expected={t['requirement_id'] for row in prior_reviews if row['proposal_id']==pid for t in row.get('coordination_tasks',[]) if t['assignee']==role}
                covered_foreign=[]
                for response in [r for r in responses if r.get('proposal_id')==pid]:
                    if response.get('previous_version')!=p['version'] or response.get('status') not in ('needs_data','unresolved'):
                        raise ValidationError('跨角色补证只能保留needs_data或unresolved，不能修改他人方案')
                    text(response.get('reason'),'跨角色补证说明');refs(response.get('evidence_ids'),allowed)
                    ids=response.get('requirement_ids')
                    if not isinstance(ids,list) or not set(ids)<=expected:raise ValidationError('跨角色回应只能引用明确分派给本角色的任务')
                    covered_foreign.extend(ids)
                if set(covered_foreign)!=expected or len(covered_foreign)!=len(expected):raise ValidationError('跨角色补证任务须逐项且不重复回应')
            covered = {pid: [] for pid in owned}
            global_ids = {t['requirement_id'] for row in prior_reviews if row['proposal_id'] is None
                          for t in row.get('coordination_tasks', []) if t['assignee'] == role}
            covered_global = []
            for response in responses:
                if response['proposal_id'] in foreign:continue
                previous = owned[response['proposal_id']]
                if response.get('previous_version') != previous['version'] or response.get('status') not in ('modified', 'needs_data', 'unresolved'):
                    raise ValidationError('修订回应须对应原版本，并明确modified、needs_data或unresolved')
                text(response.get('reason'), '修订处理理由')
                refs(response.get('evidence_ids'), allowed)
                task_ids = {t['requirement_id'] for row in prior_reviews if row['proposal_id'] == previous['id']
                            for t in row.get('coordination_tasks', []) if t['assignee'] == role}
                ids = response.get('requirement_ids')
                if not isinstance(ids, list) or not set(ids) <= (task_ids | global_ids) or len(ids) != len(set(ids)):
                    raise ValidationError('修订回应引用了未知或重复的任务编号')
                if set(ids) & global_ids and response['status'] == 'modified':
                    raise ValidationError('全店补证问题不能仅凭方案修改标记完成，须保留待补证或未解决状态')
                covered[previous['id']].extend(x for x in ids if x in task_ids)
                covered_global.extend(x for x in ids if x in global_ids)
                after = next((p for p in result.get('proposals', []) if p['id'] == previous['id']), previous)
                changed = any(previous.get(k) != after.get(k) for k in
                              ('upfront_cost', 'other_cost', 'spend_date', 'weekly_hours', 'items', 'procurements', 'model_refs', 'stop_conditions'))
                if response['status'] == 'modified' and not changed:
                    raise ValidationError('modified必须对应实际安排变化；无法修改须保留待补证或未解决状态')
            for pid, previous in owned.items():
                task_ids = {t['requirement_id'] for row in prior_reviews if row['proposal_id'] == pid
                            for t in row.get('coordination_tasks', []) if t['assignee'] == role}
                if set(covered[pid]) != task_ids or len(covered[pid]) != len(set(covered[pid])):
                    raise ValidationError('修订回应须完整且不重复地覆盖该方案所有分派任务')
                after = next((p for p in result.get('proposals', []) if p['id'] == pid), previous)
                changed = any(previous.get(k) != after.get(k) for k in
                              ('upfront_cost', 'other_cost', 'spend_date', 'weekly_hours', 'items', 'procurements', 'model_refs', 'stop_conditions'))
                if changed and not any(r['proposal_id'] == pid and r['status'] == 'modified' for r in responses):
                    raise ValidationError('实际安排发生变化时必须明确报告modified')
            if owned and (set(covered_global) != global_ids or len(covered_global) != len(set(covered_global))):
                raise ValidationError('分派给本角色的全店补证任务须完整且不重复地保留处理说明')
    elif role == 'coordinator':
        tasks = result.get('coordination_tasks')
        if not isinstance(tasks, list) or len(tasks) != len(required):
            raise ValidationError('协调角色须逐项处理coordination_requirements，不能漏掉约束、异议或缺口')
        expected = {r['id']: r for r in required}
        seen = set()
        for task in tasks:
            if not isinstance(task, dict):
                raise ValidationError('协调任务必须为对象')
            rid = task.get('requirement_id')
            if rid not in expected or rid in seen:
                raise ValidationError('协调任务引用了不存在或重复的问题编号')
            seen.add(rid)
            if task.get('assignee') not in ROLES or task.get('disposition') not in ('revise', 'ask_merchant', 'retain_unresolved'):
                raise ValidationError('协调任务须指定专业负责人和处理方式')
            if task['disposition'] == 'revise' and task['assignee'] != expected[rid]['owner']:
                raise ValidationError('方案修改只能分派给该方案负责人；其他角色负责补证和复核')
            for field in ('action', 'acceptance'):
                text(task.get(field), '协调任务'+field)
        requested = {t['assignee'] for t in tasks if t['disposition'] == 'revise'}
        if set(result.get('revise_roles', [])) != requested:
            raise ValidationError('revise_roles须与实际修改任务负责人一致')


def rule_contract(context, result):
    """Explicit offline policy only. Never used to fill missing model outputs."""
    role, phase = context['role'], context['phase']
    observations = [o for o in context['observations'] if 'value' in o]
    evidence = [o['evidence_id'] for o in observations]
    if role == 'coordinator':
        tasks = []
        for r in context.get('coordination_requirements', []):
            missing = r['kind'] == 'missing_data' or (r['kind'] == 'objection' and r['details'].get('severity') == 'needs_data')
            details = r['details']
            if r['kind'] == 'objection':
                action = details['request']
                acceptance = details['acceptance']
            elif missing:
                action = '请店主核对：'+'；'.join(x.get('question', str(x)) if isinstance(x, dict) else str(x) for x in details)
                acceptance = '提供上述项目的原始来源并更新底账；由负责人重新取证，未知项不得补零。'
            else:
                action = '修改并重算这些约束：'+'、'.join(x.get('code', str(x)) if isinstance(x, dict) else str(x) for x in details)
                acceptance = '新版本的工具计算不再触发上述约束，并由原审查角色逐项回应旧质询。'
            tasks.append({'requirement_id': r['id'], 'assignee': r['owner'],
                          'disposition': 'ask_merchant' if missing else 'revise',
                          'action': action[:3000], 'acceptance': acceptance[:3000]})
        result['coordination_tasks'] = tasks
        result['revise_roles'] = sorted({t['assignee'] for t in tasks if t['disposition'] == 'revise'})
        return result
    primary = next((o for o in observations if o['tool'] == PRIMARY[role]), observations[0])
    own_questions = [q for o in observations if o['tool'] == 'data_readiness'
                     for q in o['value']['questions'] if q['owner'] == role]
    result['assessment'] = {'perspective': role, 'conclusion': '已按'+FOCUS[role]+'检查所列工具证据；这是离线规则判断。',
                            'evidence_ids': [primary['evidence_id']],
                            'assumptions': ['底账仅在已录入且核对的范围内有效；未来销量为情景假设。'],
                            'limits': ['不由规则推断需求因果或保证经营收益。'],
                            'missing_data': [{'field_id': q['id'], 'owner': role, 'question': q['question'], 'why_needed': q['reason'],
                                              'completion_condition': '由商户提供来源、核对并更新对应底账字段后重新分析。',
                                              'evidence_ids': [next(o['evidence_id'] for o in observations if o['tool'] == 'data_readiness')]}
                                             for q in own_questions[:12]]}
    if phase == 'review':
        reviews, objections = [], []
        for p in context['proposals']:
            observation = next(o for o in observations if o['tool'] == 'proposal_evaluate' and o['arguments']['proposal']['id'] == p['id'])
            evaluation = observation['value']
            # A deterministic role checks its primary perspective, never invents demand.
            codes = [c for c in evaluation['checks'] if (role == 'inventory') == (c['code'] in
                     ('SIZE_EVIDENCE_REQUIRED', 'STOCK_EXCEEDED', 'UNKNOWN_SKU', 'SUPPLY_MINIMUM', 'SUPPLY_CAPACITY', 'SUPPLY_OUTSIDE_HORIZON', 'SUPPLY_DATA_REQUIRED'))] if role != 'customer' else []
            unknowns = ([u for u in evaluation['unknowns'] if not any(label in u for label in
                         ('销量尚未由真实成交', '当前底账为合成', '商户尚未确认'))
                         and not (context['ledger']['synthetic'] and '活动及单件变动费用尚未核实' in u)] if role == 'cash' else
                        ['缺少客户观察；请先核实需求，不能承诺成交。'] if role == 'customer' and not context['ledger']['customer_signals'] else [])
            status = 'blocked' if codes else 'needs_data' if unknowns else 'pass'
            reason = json.dumps(codes, ensure_ascii=False) if codes else '；'.join(unknowns) if unknowns else '本角色的本轮工具检查未发现需阻止的条件；不代表收益得到验证。'
            if status != 'pass':
                objections.append({'proposal_id': p['id'], 'version': p['version'], 'reason': reason,
                                   'request': '调整违反约束的投入、数量或日期后重算。' if codes else '请商户补齐来源或先完成低投入需求验证。',
                                   'topic': {'inventory': 'inventory', 'customer': 'demand', 'cash': 'cash'}[role],
                                   'severity': 'blocking' if codes else 'needs_data',
                                   'acceptance': '新版本重算不再触发所列约束，并经原角色复审。' if codes else '提交对应的真实来源和核对记录；证据不足则保留待核实。',
                                   'evidence_ids': [observation['evidence_id']]})
            previous = [o for r in context.get('reviews', []) if r['proposal_id'] == p['id']
                        for o in r.get('objections', []) if o.get('from') == role]
            reviews.append({'proposal_id': p['id'], 'version': p['version'], 'status': status,
                            'reason': reason, 'evidence_ids': [observation['evidence_id']],
                            'responses': [{'objection_id': o['id'], 'outcome': 'resolved' if status == 'pass' else 'retained',
                                           'reason': reason, 'evidence_ids': [observation['evidence_id']]} for o in previous]})
        result.update(proposal_reviews=reviews, objections=objections)
    if phase == 'revise':
        responses = []
        for before in context.get('proposals', []):
            if before['owner'] != role:
                continue
            after = next((p for p in result.get('proposals', []) if p['id'] == before['id']), before)
            changed = any(before.get(k) != after.get(k) for k in
                          ('upfront_cost', 'other_cost', 'spend_date', 'weekly_hours', 'items', 'procurements', 'model_refs', 'stop_conditions'))
            responses.append({'proposal_id': before['id'], 'previous_version': before['version'],
                              'status': 'modified' if changed else 'unresolved',
                              'reason': '实际安排有变化，须按新版本再复核。' if changed else '现有证据不足以形成新的可行安排，原问题保留，不视作解决。',
                              'requirement_ids': [t['requirement_id'] for row in context.get('reviews', []) if row['proposal_id'] == before['id']
                                                  for t in row.get('coordination_tasks', []) if t['assignee'] == role],
                              'evidence_ids': evidence})
        global_tasks = [t['requirement_id'] for row in context.get('reviews', []) if row['proposal_id'] is None
                        for t in row.get('coordination_tasks', []) if t['assignee'] == role]
        if responses and global_tasks:
            responses.append({'proposal_id': responses[0]['proposal_id'], 'previous_version': responses[0]['previous_version'],
                              'status':'needs_data','reason':'全店资料缺口仍需店主提供来源，不能以方案调整代替补证。',
                              'requirement_ids':global_tasks,'evidence_ids':evidence})
        result['revision_responses'] = responses
    return result
