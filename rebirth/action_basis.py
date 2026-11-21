"""Link deterministic agenda tasks to saved evidence, without inventing claims."""
from copy import deepcopy


def basis(report, entry, role):
    events=report.get('events',[])
    tools={e['id']:e for e in events if e['kind']=='tool_result'}
    proposal=entry['proposal'] if entry else None
    reasons=[];refs=[]
    for event in reversed(events):
        if event['kind']!='agent_result' or event['actor']!=role:continue
        result=event['data'].get('result',{})
        review=next((r for r in result.get('proposal_reviews',[]) if proposal
                     and r['proposal_id']==proposal['id'] and r['version']==proposal['version']),None)
        assessment=result.get('assessment') if not proposal and event['data'].get('phase')=='investigate' else None
        claim=review or assessment
        if claim:
            reasons=[claim.get('reason',claim.get('conclusion',''))]
            refs=[r for r in claim.get('evidence_ids',[]) if r in tools and tools[r]['actor']==role]
            break
    if proposal:
        for event in events:
            data=event.get('data',{})
            p=data.get('arguments',{}).get('proposal',{}) if data.get('tool')=='proposal_evaluate' else {}
            if event['kind']=='tool_result' and p.get('id')==proposal['id'] and p.get('version')==proposal['version']:
                refs.append(event['id'])
    return {'source_run':report['run_id'],'proposal_id':proposal['id'] if proposal else None,
            'proposal_version':proposal['version'] if proposal else None,'perspective':role,
            'reasons':[r for r in reasons if r], 'evidence_ids':list(dict.fromkeys(refs)),
            'notice':'引用对应任务的保存记录；引用存在不等于判断已证明。' if refs else '本项按核查流程安排，暂无对应的已保存工具证据。'}


def merchant_followups(report,entry):
    plans=[e for e in report.get('events',[]) if e['kind']=='coordination_plan']
    if not plans:return []
    plan=plans[-1];p=entry['proposal'] if entry else None
    requirements={r['id']:r for r in plan['data'].get('requirements',[])
                  if r.get('proposal_id') is None or (p and r.get('proposal_id')==p['id'] and r.get('version')==p['version'])}
    result=[]
    for task in plan['data'].get('tasks',[]):
        if task.get('disposition')!='ask_merchant' or task.get('requirement_id') not in requirements:continue
        result.append({**deepcopy(task),'event_id':plan['id'],
                       'proposal_id':requirements[task['requirement_id']].get('proposal_id'),
                       'proposal_version':requirements[task['requirement_id']].get('version')})
    return result
