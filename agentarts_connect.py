"""Local masked credential entry. No keys on disk, in command arguments, or in logs."""
from pathlib import Path
import json
import os
import sys
import threading

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.agentarts-deps'))
CONFIG=ROOT/'config/agentarts.managed.local.json'
ROLES=[('coordinator','统筹'),('inventory','库存'),('customer','客源'),('cash','资金')]


def normalize_keys(values, required_roles=None):
    """Validate the complete form before updating any process credentials."""
    result={};missing=[]
    for role,label in ROLES:
        if required_roles is not None and role not in required_roles:continue
        value=values.get(role,'').strip()
        if value.lower().startswith('bearer '):value=value[7:].strip()
        if not value:missing.append(label);continue
        if any(ch.isspace() for ch in value):raise ValueError(label+'密钥含有空格或换行，请重新复制完整密钥')
        result[role]=value
    if missing:raise ValueError('这些输入框没有读到密钥：'+'、'.join(missing)+'。请查看旁边的字符数，或点击该行“粘贴”。')
    return result


def main():
    import tkinter as tk
    from tkinter import ttk, messagebox
    from rebirth.providers import AgentArtsProvider
    from rebirth.control import RunControl
    root=tk.Tk();root.title('逆势重生 · AgentArts连接（修复输出计数）');root.geometry('900x590')
    root.minsize(800,590)
    frame=ttk.Frame(root,padding=24);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='填入四个智能体的调用密钥',font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w')
    ttk.Label(frame,text='在各角色运行时的 URN / API Key 页面复制。这里不是 MaaS 模型密钥。',wraplength=650).pack(anchor='w',pady=(10,2))
    ttk.Label(frame,text='点击输入框后按 Ctrl+V，或右键粘贴。密钥不写入文件，仅用于本次连接。',wraplength=800).pack(anchor='w',pady=(0,10))
    entries={};config=json.loads(CONFIG.read_text(encoding='utf-8'))
    show_keys=tk.BooleanVar(value=True)
    def toggle_keys():
        for entry in entries.values():entry.configure(show='' if show_keys.get() else '*')
    ttk.Checkbutton(frame,text='显示密钥（取消勾选即可隐藏）',variable=show_keys,command=toggle_keys).pack(anchor='w',pady=(0,8))
    for role,label in ROLES:
        row=ttk.Frame(frame);row.pack(fill='x',pady=5)
        ttk.Label(row,text=label+'密钥',width=11).pack(side='left')
        value=tk.StringVar()
        entry=ttk.Entry(row,textvariable=value);entry.pack(side='left',fill='x',expand=True);entries[role]=entry
        count=tk.StringVar(value='未填写')
        def update_count(*args,v=value,c=count):
            length=len(v.get().strip());c.set(str(length)+' 字符' if length else '未填写')
        value.trace_add('write',update_count)
        def paste_into(e=entry):
            try:text=root.clipboard_get()
            except tk.TclError:messagebox.showinfo('无法粘贴','剪贴板里没有文字，请先复制该角色的调用密钥。');return
            e.delete(0,'end');e.insert(0,text);e.focus_set()
        def paste_event(event,paste=paste_into):
            paste();return 'break'
        for shortcut in ('<Control-v>','<Control-V>','<Shift-Insert>','<<Paste>>'):
            entry.bind(shortcut,paste_event)
        menu=tk.Menu(entry,tearoff=False)
        menu.add_command(label='粘贴密钥  Ctrl+V',command=paste_into)
        menu.add_command(label='全选',command=lambda e=entry:(e.focus_set(),e.selection_range(0,'end')))
        def show_menu(event,m=menu,e=entry):
            e.focus_set()
            try:m.tk_popup(event.x_root,event.y_root)
            finally:m.grab_release()
            return 'break'
        entry.bind('<Button-3>',show_menu)
        ttk.Button(row,text='粘贴',width=6,command=paste_into).pack(side='left',padx=6)
        ttk.Label(row,textvariable=count,width=12).pack(side='left')
    status=tk.StringVar(value='只填统筹密钥就能测试连接；打开网站时再填齐另外三项。不会自动调用。')
    ttk.Label(frame,textvariable=status,wraplength=650).pack(anchor='w',pady=18)
    state={'server':None,'testing':False,'verified':False}
    def fill_keys(required_roles=None):
        values=normalize_keys({role:entry.get() for role,entry in entries.items()}, required_roles)
        for role in values:
            os.environ[config['agents'][role]['token_env']]=values[role]
    def test():
        if state['testing']:return
        try: fill_keys(('coordinator',))
        except ValueError as exc: messagebox.showinfo('还差一步',str(exc));return
        state['testing']=True;state['verified']=False;status.set('正在测试统筹接口，最多1次请求，可能需等待约1分钟……')
        def work():
            try:
                # Future transport fixes load on the next click, keeping entries intact.
                import importlib
                from rebirth import providers,managed_ws
                importlib.reload(providers);importlib.reload(managed_ws)
                provider=providers.AgentArtsProvider(CONFIG,required_roles=('coordinator',),control=RunControl(max_calls=1,max_input_bytes=20000,max_output_bytes=300000,max_seconds=70))
                action=provider.step({'run_id':'connection-test','role':'coordinator','phase':'coordinate',
                    'ledger':{},'tools':{},'proposals':[],'reviews':[],
                    'test_only':True,'request':'仅核验连接，不做经营分析。返回action=final，result包含revise_roles空列表和notes字符串列表。'})
                if action.get('action')!='final' or not isinstance(action.get('result'),dict):
                    raise ValueError('接口已返回，但输出不是预期的最终JSON动作；需检查统筹提示词')
                state['verified']=True
                message='统筹已返回可解析的最终JSON。其余三个角色尚未实测；现在可打开本地网站。'
            except Exception as exc:
                from rebirth.providers import ProviderError
                from rebirth.control import LimitExceeded,RunCancelled
                message=str(exc) if isinstance(exc,(ProviderError,LimitExceeded,RunCancelled,ValueError)) else '连接测试失败；未显示原始响应，避免泄露敏感信息。'
            state['testing']=False
            root.after(0,lambda:status.set(message))
        threading.Thread(target=work,daemon=True).start()
    def open_site():
        import webbrowser
        if not state['verified']:
            messagebox.showinfo('先测连接','请先点击“测试统筹”，成功后再打开网站。');return
        try:fill_keys()
        except ValueError as exc:messagebox.showinfo('还差一步',str(exc));return
        if state['server'] is None:
            from http.server import ThreadingHTTPServer
            from rebirth.server import make_handler
            from rebirth.onboarding import PracticeStore,seed_practice
            store=PracticeStore(ROOT/'var/agentarts-practice/business.sqlite3');seed_practice(store,ROOT)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(store,CONFIG,allow_cloud=True))
            state['server']=server;threading.Thread(target=server.serve_forever,daemon=True).start()
            for entry in entries.values():entry.configure(state='disabled')
        url='http://127.0.0.1:'+str(state['server'].server_port)+'/'
        status.set('本地网页已启动：'+url+'。每次真实分析仍需在网页确认；保持此窗口打开。')
        webbrowser.open(url)
    buttons=ttk.Frame(frame);buttons.pack(fill='x')
    ttk.Button(buttons,text='1. 测试统筹（1次请求，可能少量计费）',command=test).pack(side='left',padx=(0,12))
    ttk.Button(buttons,text='2. 打开本地网站',command=open_site).pack(side='left')
    ttk.Label(frame,text='首次只用虚构练习店铺。测试成功仅证明统筹接口可调用，不代表完整多智能体功能已验收。',wraplength=650).pack(anchor='w',pady=16)
    def close():
        if state['server']:state['server'].shutdown();state['server'].server_close()
        for role,_ in ROLES:
            os.environ.pop(config['agents'][role]['token_env'],None)
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close);root.mainloop()


if __name__=='__main__':main()
