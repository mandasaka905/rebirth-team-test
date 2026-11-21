const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
// Exercise the actual export functions without a browser or a server.
const source=fs.readFileSync(path.join(__dirname,'../dist/agenda.js'),'utf8');const from=source.indexOf(' const escapeIcs=');const to=source.indexOf(" document.addEventListener('change'",from);const scope={Date,TextEncoder};vm.createContext(scope);vm.runInContext(source.slice(from,to)+';this.makeCalendar=calendar;this.escapeCalendar=escapeIcs;',scope);
const fixture={id:'agenda_local',stale:false,days:[{date:'2026-10-29',tasks:[{id:'task_1',status:'pending',kind:'preparation',title:'核对现金，先守住生活',steps:['核对实物;单据','换行\n来源,甲'],deliverable:'记录'.repeat(60)}]}],stop_conditions:['低于现金线暂停'],notice:'商户自报进度'};
test('calendar is an all-day tentative agenda with valid CRLF, escaping and UTF-8 folding',()=>{const data=scope.makeCalendar(fixture);assert.ok(data.startsWith('BEGIN:VCALENDAR\r\n'));assert.ok(data.endsWith('END:VCALENDAR\r\n'));assert.equal(data.replaceAll('\r\n','').includes('\n'),false);assert.ok(data.includes('DTSTART;VALUE=DATE:20261029'));assert.ok(data.includes('DTEND;VALUE=DATE:20261030'));assert.ok(data.includes('STATUS:TENTATIVE'));assert.ok(data.includes('TRANSP:TRANSPARENT'));assert.ok(data.includes('\\;'));assert.ok(data.includes('\\n'));for(const line of data.split('\r\n'))assert.ok(Buffer.byteLength(line,'utf8')<=75);assert.equal((data.match(/BEGIN:VEVENT/g)||[]).length,1)});
test('completed tasks are omitted and stale calendars are blocked',()=>{assert.throws(()=>scope.makeCalendar({...fixture,stale:true}));const copy=structuredClone(fixture);copy.days[0].tasks[0].status='done';assert.ok(!scope.makeCalendar(copy).includes('BEGIN:VEVENT'))});

test('downloaded text keeps action evidence and legacy agendas remain readable',()=>{
 const from=source.indexOf(' function textAgenda('),to=source.indexOf(' globalThis.RebirthAgenda=',from);
 const c={};vm.createContext(c);vm.runInContext(source.slice(from,to)+';this.exportText=textAgenda;',c);
 const a=structuredClone(fixture);a.merchant_name='构造小店';a.scope='补证准备';a.plan_spend_cap='0.00';
 a.summary={reserve_floor:'1000.00',source:'规则快照',gates:['费用待核对']};a.backlog=[];
 assert.match(c.exportText(a),/费用待核对/);
 a.days[0].tasks[0].basis={reasons:['报价尚未核实'],evidence_ids:['e9'],notice:'对应任务保存记录'};
 assert.match(c.exportText(a),/报价尚未核实/);assert.match(c.exportText(a),/工具记录：e9/);
});
