"""Assemble a clean Windows x64 teammate kit from an explicit source allow-list."""
from datetime import datetime
from pathlib import Path
from shutil import copy2, copytree
from zipfile import ZipFile, ZIP_DEFLATED
import argparse
import hashlib
import json

PROJECT = Path(__file__).resolve().parents[1]


def write_script(destination,scenarios):
    lines=['# 逆势重生 · 电脑版测试步骤（照着点就行）','', '## 先打开软件','', '1. 把ZIP全部解压，例如放到桌面上的一个新文件夹里，不要直接在压缩包里运行。','2. 双击“开始测试.cmd”。出现的黑色窗口先别关。','3. 浏览器会打开测试表。点“打开网站，开始试用”，网站会在另一个标签页打开；这份测试表留着填写。','', '不用另外安装软件，也不用交钱。里面有甲、乙两家练习店，店名中的“合成”就是假数据、用来练习的意思。','', '## 怎么记录问题','', '下面每项都写明了点哪里。照着做，30秒找不到按钮，就写“我在××页，找不到××按钮”。不用替软件猜，也不用反复试到成功才算完。','', '每项选一个结果：顺利完成／找不到按钮／没看懂说明／点了没反应或保存失败／操作很麻烦／先跳过。愿意计时可以填秒数，不计时也可以。','', '全部约30分钟。时间有限先测T01—T07。','']
    for t in scenarios:
        lines += [f"## {t['id']} {t['title']}", '', t['goal'], '']
        lines += [str(i)+'. '+step for i,step in enumerate(t['steps'],1)]
        lines += ['', '**说明：** '+t['sample'], '', '**补充说明：** '+t['hint'], '', '**做完应该看到：** '+t['expected'], '', '记录：结果____；耗时（可不填）____秒；哪一步不好用________________。', '']
    lines += ['## 最后发回什么','', '回到测试表，写下最难操作的地方，再点“导出反馈 TXT”。截图另外保存，例如“T03-找不到按钮.png”。把反馈文件和截图一起发给项目负责人。','', '黑色窗口关掉后，网页会暂时不能保存。普通启动会继续刚才那份记录；“新一轮测试”才会另外开一份练习资料，之前的记录仍保留。','', '这次只测电脑操作。手机版、上线访问和付费AI以后再测。']
    (destination/'测试脚本-电脑版.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def build(destination, runtime):
    destination=Path(destination).resolve()
    if destination.exists():raise RuntimeError('目标已存在，请使用一个新的交付目录，避免覆盖试用记录')
    destination.mkdir(parents=True)
    app=destination/'app';app.mkdir()
    for folder,patterns in [('rebirth',['*.py']),('dist',['*.js','*.css','*.html','*.svg']),('examples',['*.json']),('knowledge',['*.json']),('agentarts/prompts',['*.md'])]:
        target=app/folder;target.mkdir(parents=True,exist_ok=True)
        for pattern in patterns:
            for p in (PROJECT/folder).glob(pattern):copy2(p,target/p.name)
    config=app/'config';config.mkdir()
    copy2(PROJECT/'config/contracts.json',config/'contracts.json')
    (config/'test-no-cloud.json').write_text(json.dumps({'agents':{},'allowed_hosts':[],'notice':'Synthetic usability kit. Real cloud disabled at server.'}),encoding='utf-8')
    preview=app/'design-preview/dist';(preview/'assets').mkdir(parents=True)
    for name in ['index.html','homepage.js','homepage.css','desk-theme.js','desk-theme.css']:
        copy2(PROJECT/'design-preview/dist'/name,preview/name)
    for name in ['summer-street.png','summer-street-mobile.png','shop-interior-v1.png','tree-shadow.svg','wordmark.svg']:
        copy2(PROJECT/'design-preview/dist/assets'/name,preview/'assets'/name)
    test=app/'testing';test.mkdir()
    for name in ['runner.py','seed.py','guide.html','guide.js','kit.js','kit.css','scenarios.json']:
        copy2(PROJECT/'testing'/name,test/name)
    copytree(runtime,destination/'runtime',ignore=lambda _,names:[n for n in names if n=='__pycache__'])
    for name,option in [('开始测试.cmd',''),('打不开时运行自检.cmd','--selfcheck'),('新一轮测试（保留旧记录）.cmd','--new-round')]:
        command='@echo off\r\nchcp 65001 >nul\r\nsetlocal\r\ncd /d "%~dp0"\r\n"runtime\\python.exe" -X utf8 "app\\testing\\runner.py" '+option+' %*\r\nif errorlevel 1 echo 启动失败，请运行“打不开时运行自检.cmd”，把结果发回。\r\npause\r\n'
        (destination/name).write_bytes(command.encode('utf-8'))
    scenarios=json.loads((test/'scenarios.json').read_text(encoding='utf-8'))
    write_script(destination,scenarios)
    readme='''逆势重生 · 电脑版试用包

1. 必须先把整个ZIP解压，再运行；不要直接在压缩包里双击程序。
2. Windows 10/11 64位电脑，双击“开始测试.cmd”。无需安装Python或Node，不用管理员权限。
3. 浏览器打开测试指南，点击“打开网站，开始试用”。保留测试指南标签页。
4. 保持后台窗口运行。端口自动选择，不会抢占你其他网站的端口。
5. 结束后在指南导出反馈TXT，截图单独附上。反馈同时保存在本包data文件夹里。
6. 关闭后台后再次启动继续原轮次。需要干净资料时，先关闭旧后台，再运行“新一轮测试（保留旧记录）.cmd”。

打不开：运行“打不开时运行自检.cmd”，把显示结果或data里的“自动自检结果.json”发回。
浏览器没自动打开：把后台窗口显示的“测试指南”地址复制到浏览器；或打开data里的“打开测试指南.html”。
程序被系统/单位设备管理拦截：保留提示并联系项目负责人，不要自行关闭安全保护。

里面的两家店和数字都是编来练习的，不是真实商户。
只在本机运行，不使用付费模型，不发布公网，不自动联系任何人。
手机版和线上部署本轮暂缓。本机127.0.0.1地址不能给队员手机独立访问。
这不是安装包上架版本；使用其他系统的队员请先反馈系统类型。
'''
    (destination/'先看这里.txt').write_text(readme,encoding='utf-8-sig')
    (destination/'运行环境来源.txt').write_text('本包使用Python官方Windows 64位嵌入运行环境3.13.7，未修改解释器。\n来源：https://www.python.org/downloads/release/python-3137/\n原始下载：https://www.python.org/ftp/python/3.13.7/python-3.13.7-embed-amd64.zip\n已核对官方MD5：77f294ec267596827a2ab06e8fa3f18c\n许可证见runtime/LICENSE.txt；本包无需pip或安装系统Python。\n',encoding='utf-8-sig')
    (destination/'data').mkdir()
    (destination/'data/数据说明.txt').write_text('首次启动会生成独立合成测试库与试用反馈，不含开发者原数据库。普通启动保留本轮；新一轮另建文件夹，旧数据不删除。\n',encoding='utf-8-sig')
    manifest={str(p.relative_to(destination)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file()}
    (destination/'文件清单SHA256.json').write_text(json.dumps({'version':'desktop-20261101-v3','files':manifest},ensure_ascii=False,indent=2),encoding='utf-8')
    return destination


def archive(destination,output):
    root=Path(destination);output=Path(output)
    if output.exists():raise RuntimeError('ZIP已存在，请使用新文件名')
    with ZipFile(output,'w',ZIP_DEFLATED,compresslevel=6) as z:
        for p in root.rglob('*'):
            if not p.is_file():continue
            rel=p.relative_to(root)
            # No generated databases, run logs, private feedback, caches or machine state.
            if rel.parts[0]=='data' and rel.name!='数据说明.txt':continue
            if '__pycache__' in rel.parts or p.suffix in ('.pyc','.sqlite3','.db','.log'):continue
            z.write(p,str(Path(root.name)/rel))
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('destination');parser.add_argument('runtime');args=parser.parse_args()
    folder=build(args.destination,args.runtime)
    print(folder)
