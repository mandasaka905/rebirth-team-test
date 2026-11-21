"""Unambiguous request examples. Validation remains strict in the host."""


def clarify(envelope,context):
    contracts=envelope['output_contract']
    searches=[o for o in context.get('observations',[]) if o.get('tool')=='knowledge_search' and 'value' in o]
    if context.get('role') in ('inventory','customer','cash'):
        final=contracts.get('final_action',{}).get('result',{})
        if 'assessment' in final:
            final['assessment']['knowledge_citations']=[]
        if searches:
            envelope['stage_requirements']['retrieved_knowledge']=[
                {'evidence_id':o['evidence_id'],'document_ids':[d['id'] for d in o['value'].get('matches',[])]}
                for o in searches]
            envelope['stage_requirements']['instructions']+=(
                ' 本阶段已实际检索知识。用于专业判断的每条资料依据必须写入assessment.knowledge_citations，'
                '包含claim、document_id、supporting_text、evidence_id、scope_limit；supporting_text逐字取自对应content。'
                '只引用确实支持该主张的摘录；一般方法不能证明本店销量、成本或经营因果。'
                '若所有检索结果均不适用，引用留空并在notes明确说明未采用的原因，不强凑引用。')
    contracts['batch_tool_action']={'action':'tool','name':'read_tools','arguments':{'calls':[
        {'name':'inventory_analyze','arguments':{}},{'name':'data_readiness','arguments':{}}]}}
    contracts['batch_notice']='示例工具名须按本角色替换；calls必须位于顶层arguments内。不是parameters、tools、requests或顶层calls。'
    if any(o.get('tool')=='read_tools' and o.get('error') for o in context.get('observations',[])):
        observed={o.get('tool') for o in context.get('observations',[]) if 'value' in o}
        primary={'inventory':'inventory_analyze','customer':'customer_evidence','cash':'cash_baseline'}.get(context.get('role'))
        example=None
        if primary and primary not in observed:example={'action':'tool','name':primary,'arguments':{}}
        elif context.get('proposals'):
            done={(o.get('arguments',{}).get('proposal',{}).get('id'),o.get('arguments',{}).get('proposal',{}).get('version')) for o in context.get('observations',[]) if o.get('tool')=='proposal_evaluate' and 'value' in o}
            pending=next((p for p in context['proposals'] if (p['id'],p['version']) not in done),None)
            if pending:example={'action':'tool','name':'proposal_evaluate','arguments':{'proposal':pending}}
        contracts.pop('batch_tool_action',None)
        if example:contracts['single_tool_recovery_example']=example
        envelope['stage_requirements']['instructions']+=' 本阶段批量请求已失败，请停止使用read_tools，改为每次一个普通tool动作；single_tool_recovery_example仅说明下一项尚缺取证的合法请求，不代表经营判断。已有所需证据时直接final。'
    envelope['stage_requirements']['instructions']+=(
        ' 批量动作严格使用output_contract.batch_tool_action的结构。工具参数字段只能叫arguments。'
        ' 当前phase不是review时，objections必须省略或为空，不能提前提交质询。'
        ' propose只能生成版本1的新编号方案；不能在此阶段修改candidate_for_review或冒用其编号。'
        ' 若只核查已有候选，propose可返回proposals=[]，仍提供本阶段有依据的assessment；实际候选稍后会统一送审。'
        ' revise才允许修改context.proposals中本角色方案，版本恰为原版加1。'
        ' evidence_ids只取本次current_evidence_ids，不能引用own_memory中的旧阶段编号。')
    if context.get('role')=='coordinator':
        ids=[r['id'] for r in context.get('coordination_requirements',[])]
        envelope['stage_requirements']['coordination_slot_ids']=ids
        envelope['stage_requirements']['coordination_task_count']=len(ids)
        envelope['stage_requirements']['instructions']+=' coordination_tasks严格一项对应coordination_slot_ids的一个编号；列表恰为coordination_task_count项，不能把一个编号的多条details拆成多项，也不能把多个编号合并。只用给定编号，不自创编号；处理方式、行动和验收条件仍由你决定。'
        envelope['stage_requirements']['fresh_tool_required']=False
        envelope['stage_requirements']['next_action_hint']='现在返回final：逐项处理coordination_requirements，不需要再次读取业务工具。'
        envelope['stage_requirements']['instructions']+=' 当前是协调角色，前文通用的每阶段取证要求不适用；已有context.reviews中的宿主计算和专业审查，直接完成协调任务，不重复查询。'
    elif context.get('phase')=='revise':
        role=context.get('role');slots=[]
        for p in context.get('proposals',[]):
            tasks=[t['requirement_id'] for row in context.get('reviews',[]) if row['proposal_id']==p['id'] for t in row.get('coordination_tasks',[]) if t['assignee']==role]
            if p['owner']==role or tasks:slots.append({'proposal_id':p['id'],'previous_version':p['version'],'may_modify':p['owner']==role,'assigned_requirement_ids':tasks})
        envelope['stage_requirements']['revision_response_slots']=slots
        envelope['stage_requirements']['global_evidence_task_ids']=[t['requirement_id'] for row in context.get('reviews',[]) if row['proposal_id'] is None for t in row.get('coordination_tasks',[]) if t['assignee']==role]
        envelope['stage_requirements']['instructions']+=' global_evidence_task_ids是独立的全店补证任务，不能遗漏或重复：在revision_responses另列needs_data或unresolved回应，并绑定你自己名下的方案编号与原版本；不能混进modified回应。它们与各方案assigned_requirement_ids分别完整覆盖。'
        envelope['stage_requirements']['instructions']+=' revision_responses须覆盖revision_response_slots。may_modify=false仅回应分派给自己的补证，状态限needs_data或unresolved，不改他人方案。自己方案若任何实际安排改变，至少一条回应必须为modified；仍缺商户资料另列needs_data，不能把改动和全店待补证任务合并成一条modified。版本、任务与证据编号必须精确引用。'
    elif context.get('phase')=='review':
        models={(o.get('arguments',{}).get('draft',{}).get('id'),o.get('arguments',{}).get('draft',{}).get('version')) for o in context.get('observations',[]) if o.get('tool')=='model_draft_evaluate' and 'value' in o}
        targets={(d['id'],d['version']) for d in context.get('model_drafts',[])}
        if targets and targets<=models:
            envelope['stage_requirements']['next_action_hint']='全部当前模式草案已有本阶段计算。直接输出final、assessment和model_reviews，不再重复取证；保留未知条件。'
        reviewed={(o.get('arguments',{}).get('proposal',{}).get('id'),o.get('arguments',{}).get('proposal',{}).get('version'))
                  for o in context.get('observations',[]) if o.get('tool')=='proposal_evaluate' and 'value' in o}
        expected={(p['id'],p['version']) for p in context.get('proposals',[])}
        if expected and expected<=reviewed:
            envelope['stage_requirements']['next_action_hint']='全部当前版本方案已取得计算证据。直接返回完整final及逐方案proposal_reviews，不重复查询；保留未解决的质询。'
