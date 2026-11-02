"""Opt-in hosted gateway. Loopback upstream only; HTTPS is terminated by a reverse proxy."""
import argparse
import getpass
import json
import re
from io import BytesIO
from http.cookies import SimpleCookie, CookieError
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit, quote

from .accounts import Accounts
from .server import make_handler, ROOT
from .store import Store


class Gateway:
    def __init__(self, data_dir, origin, *, local_preview=False, registration_open=False, registration_limit=30, demo_only=False):
        parsed = urlsplit(origin)
        if parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('正式网址只能包含协议、域名和可选端口，不带路径')
        if not parsed.hostname or parsed.scheme != ('http' if local_preview else 'https'):
            raise ValueError('正式环境必须填写https网址')
        if local_preview and parsed.hostname != '127.0.0.1':
            raise ValueError('本地预演仅允许127.0.0.1')
        if not re.fullmatch(r'[A-Za-z0-9.:-]+', parsed.netloc):
            raise ValueError('域名格式不正确')
        self.origin, self.host = origin, parsed.netloc
        self.secure = not local_preview
        if not isinstance(registration_limit,int) or not 1<=registration_limit<=200:
            raise ValueError('测试账号名额应在1至200之间')
        self.registration_open=registration_open
        self.registration_limit=registration_limit
        self.demo_only=demo_only
        self.cookie_name = '__Host-rebirth' if self.secure else 'rebirth_preview'
        self.accounts = Accounts(data_dir)
        self.handlers, self.lock = {}, Lock()
        self.config = ROOT/'config/hosted-no-cloud.json'

    def tenant(self, uid):
        with self.lock:
            if uid not in self.handlers:
                # Account IDs are random, server-generated hex. No incoming path is used here.
                assert re.fullmatch('[a-f0-9]{32}', uid)
                if self.demo_only:
                    from .onboarding import PracticeStore,seed_practice
                    store=PracticeStore(self.accounts.folder/'shops'/uid/'business.sqlite3')
                    seed_practice(store,ROOT)
                else:
                    store = Store(self.accounts.folder/'shops'/uid/'business.sqlite3')
                self.handlers[uid] = make_handler(store, self.config, allow_cloud=False)
            return self.handlers[uid]

    def handler(self):
        gateway = self
        base = make_handler(None, self.config, allow_cloud=False)

        class Handler(base):
            def safe_local(self):
                if self.headers.get('Host') != gateway.host:
                    self.reply(403, {'error':'访问地址不正确'})
                    return False
                origin = self.headers.get('Origin')
                if (self.command == 'POST' and origin != gateway.origin) or (origin and origin != gateway.origin):
                    self.reply(403, {'error':'请从本网站页面提交，不接受跨站请求'})
                    return False
                if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                    self.reply(403, {'error':'不接受跨站访问'})
                    return False
                return True

            def token(self):
                try:
                    cookie = SimpleCookie(self.headers.get('Cookie', ''))
                    return cookie[gateway.cookie_name].value if gateway.cookie_name in cookie else ''
                except CookieError:
                    return ''

            def cookie(self, token='', expired=False):
                return f'{gateway.cookie_name}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if expired else 43200}' + ('; Secure' if gateway.secure else '')

            def auth_reply(self, status, value, cookie=None):
                payload=json.dumps(value,ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Length',str(len(payload)))
                if cookie is not None:self.send_header('Set-Cookie',cookie)
                self.end_headers();self.wfile.write(payload)

            def redirect(self, path):
                self.send_response(303);self.send_header('Location',path)
                self.send_header('Cache-Control','no-store');self.send_header('Content-Length','0');self.end_headers()

            def static_bytes(self, payload, mime):
                # Only authored interface assets are adapted. Never rewrite API records or user text.
                if mime.startswith(('text/html','text/javascript')):
                    text=payload.decode('utf-8-sig')
                    for before,after in [
                        ('只用本机程序','只用网站内置规则'),
                        ('仅在本机执行','仅在服务器内执行'),
                        ('当前是本机网页应用，不是已上架的原生App。关闭后台窗口后无法读取或保存；请保持服务运行。','当前是网页登录使用的服务，不需要安装App。资料保存在服务器的本账号下；请保持联网。'),
                        ('多店铺档案不是线上账号认证。','账号内可以建立多家店铺；请保管好账号密码。'),
                        ('请保持本项目的后台窗口运行，再重新读取。','请检查网络后重新读取；仍然失败时联系项目负责人。'),
                        ('只适合在本机试用；关闭后台运行窗口后，页面将无法继续保存或分析。','手机和电脑登录同一账号即可继续使用，请保持联网。'),
                        ('本机','本账号')]:text=text.replace(before,after)
                    payload=text.encode()
                self.send_response(200);self.send_header('Content-Type',mime)
                self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
                self.end_headers();self.wfile.write(payload)

            def asset(self, path):
                assets={'/':('index.html','text/html; charset=utf-8'),'/homepage.js':('homepage.js','text/javascript; charset=utf-8'),'/homepage.css':('homepage.css','text/css; charset=utf-8'),'/desk-theme.js':('desk-theme.js','text/javascript; charset=utf-8'),'/desk-theme.css':('desk-theme.css','text/css; charset=utf-8')}
                if path in assets:
                    name,mime=assets[path];self.static_bytes((ROOT/'design-preview/dist'/name).read_bytes(),mime);return True
                for name in ['summer-street.png','summer-street-mobile.png','shop-interior-v1.png','tree-shadow.svg','wordmark.svg']:
                    if path=='/preview-assets/'+name:
                        self.static_bytes((ROOT/'design-preview/dist/assets'/name).read_bytes(),'image/svg+xml' if name.endswith('.svg') else 'image/png');return True
                if path in ['/login','/register','/account','/auth.js','/auth.css','/auth-client.js']:
                    name={'/login':'login.html','/register':'register.html','/account':'account.html'}.get(path,path[1:])
                    mime='text/javascript; charset=utf-8' if name.endswith('.js') else 'text/css; charset=utf-8' if name.endswith('.css') else 'text/html; charset=utf-8'
                    self.static_bytes((ROOT/'dist'/name).read_bytes(),mime);return True
                if path=='/workbench':
                    user=gateway.accounts.user(self.token())
                    if not user:self.redirect('/login');return True
                    html=(ROOT/'dist/index.html').read_text(encoding='utf-8-sig')
                    html=html.replace('</head>','<link rel="stylesheet" href="/desk-theme.css"><link rel="stylesheet" href="/auth.css"><script src="/desk-theme.js" defer></script></head>')
                    # This script must run before application initialization, including the first API call.
                    html=html.replace('<script src="/core.js"',f'<meta name="rebirth-account-id" content="{user["id"]}"><meta name="rebirth-demo-only" content="{str(gateway.demo_only).lower()}"><script src="/auth-client.js" defer></script><script src="/core.js"')
                    self.static_bytes(html.encode(),'text/html; charset=utf-8');return True
                if path.endswith('.js') and path in {'/'+p.name for p in (ROOT/'dist').glob('*.js')}:
                    self.static_bytes((ROOT/'dist'/path[1:]).read_bytes(),'text/javascript; charset=utf-8');return True
                return super().asset(path)

            def authenticated(self):
                user=gateway.accounts.user(self.token())
                if not user:self.reply(401,{'error':'登录已过期，请重新登录后再试'});return None
                expected=self.headers.get('X-Rebirth-Account')
                if expected != user['id']:
                    self.reply(409,{'error':'账号已改变。为避免把旧页面资料存入另一个账号，请先保存手边文字，再重新打开工作台。','account_changed':True});return None
                return user

            def do_GET(self):
                if not self.safe_local():return
                path=urlsplit(self.path).path
                if path=='/api/public-settings':
                    self.reply(200,{'registration_open':gateway.registration_open,'demo_only':gateway.demo_only});return
                if path=='/api/session':
                    user=gateway.accounts.user(self.token())
                    self.reply(200 if user else 401,{'user':user,'error':None if user else '请先登录'});return
                if path=='/health':self.reply(200,{'status':'ok','cloud_connected':False});return
                if path=='/account' and not gateway.accounts.user(self.token()):self.redirect('/login');return
                if path.startswith('/api/'):
                    user=self.authenticated()
                    if user:gateway.tenant(user['id']).do_GET(self)
                    return
                if not self.asset(path):self.reply(404,{'error':'页面不存在'})

            def do_POST(self):
                if not self.safe_local():return
                path=urlsplit(self.path).path
                if path in ['/api/login','/api/logout','/api/register']:
                    if self.headers.get('Content-Type','').split(';')[0]!='application/json':self.reply(415,{'error':'提交格式不正确'});return
                    try:
                        length=int(self.headers.get('Content-Length','0'))
                        if not 0<length<=4096:raise ValueError()
                        body=json.loads(self.rfile.read(length))
                        if not isinstance(body,dict):raise ValueError()
                    except (ValueError,TypeError):self.reply(400,{'error':'提交内容不正确'});return
                    if path=='/api/logout':
                        gateway.accounts.logout(self.token());self.auth_reply(200,{'ok':True},self.cookie(expired=True));return
                    name,password=body.get('username'),body.get('password')
                    if not isinstance(name,str) or not isinstance(password,str) or len(name)>40 or not 1<=len(password)<=256:
                        self.reply(400,{'error':'请填写账号和密码'});return
                    if path=='/api/register':
                        if not gateway.registration_open:
                            self.reply(403,{'error':'暂未开放注册，请联系项目负责人'});return
                        if body.get('password_confirm')!=password:
                            self.reply(400,{'error':'两次密码不一致，请重新确认'});return
                        if gateway.demo_only and body.get('test_consent') is not True:
                            self.reply(400,{'error':'请确认测试期间只使用虚构资料'});return
                        try:
                            uid=gateway.accounts.register(name,password,self.client_address[0],limit=gateway.registration_limit)
                            gateway.tenant(uid)
                        except ValueError as exc:
                            message=str(exc);self.reply(429 if '尝试较多' in message else 400,{'error':message});return
                    token,error=gateway.accounts.login(name,password,self.client_address[0])
                    if error:self.reply(429 if '次数' in error else 401,{'error':error});return
                    gateway.accounts.logout(self.token())
                    self.auth_reply(200,{'ok':True},self.cookie(token));return
                user=self.authenticated()
                if user:gateway.tenant(user['id']).do_POST(self)
        return Handler

    def wsgi(self):
        """Reuse the tested HTTP route handlers without exposing their development socket server."""
        handler=self.handler()
        class Connection:
            def __init__(self,raw):self.input=BytesIO(raw);self.output=BytesIO()
            def makefile(self,*args,**kwargs):return self.input
            def sendall(self,data):self.output.write(data)
        def application(environ,start_response):
            try:length=int(environ.get('CONTENT_LENGTH') or 0)
            except ValueError:length=-1
            if not 0<=length<=1024*1024:
                payload=b'{"error":"Request too large or invalid"}'
                start_response('413 Payload Too Large',[('Content-Type','application/json'),('Content-Length',str(len(payload)))]);return [payload]
            method=environ.get('REQUEST_METHOD','GET')
            path=quote(environ.get('PATH_INFO','/'),safe='/')
            query=environ.get('QUERY_STRING','')
            if query:path+='?'+query
            headers={key[5:].replace('_','-'):value for key,value in environ.items() if key.startswith('HTTP_')}
            if environ.get('CONTENT_TYPE'):headers['CONTENT-TYPE']=environ['CONTENT_TYPE']
            headers['CONTENT-LENGTH']=str(length)
            # Waitress validates the external HTTP framing. This is one bounded in-memory request.
            raw=(method+' '+path+' HTTP/1.0\r\n'+''.join(k+': '+str(v)+'\r\n' for k,v in headers.items())+'\r\n').encode('latin-1')
            conn=Connection(raw+environ['wsgi.input'].read(length))
            try:
                handler(conn,(environ.get('REMOTE_ADDR','127.0.0.1'),0),None)
                head,body=conn.output.getvalue().split(b'\r\n\r\n',1)
                lines=head.decode('latin-1').split('\r\n');status=lines[0].split(' ',1)[1]
                response_headers=[]
                for line in lines[1:]:
                    key,value=line.split(':',1)
                    if key.lower() not in ('server','date','connection','transfer-encoding'):response_headers.append((key,value.strip()))
                start_response(status,response_headers);return [body]
            except Exception:
                payload=b'{"error":"Service temporarily unavailable"}'
                start_response('500 Internal Server Error',[('Content-Type','application/json'),('Content-Length',str(len(payload)))]);return [payload]
        return application


def main():
    parser=argparse.ArgumentParser(description='逆势重生：独立账号与公网部署入口')
    parser.add_argument('--data-dir',required=True,help='独立存储目录，不能指向现有本地测试资料')
    sub=parser.add_subparsers(dest='command',required=True)
    create=sub.add_parser('create-user');create.add_argument('username')
    reset=sub.add_parser('reset-password');reset.add_argument('username')
    backup=sub.add_parser('backup');backup_target=backup.add_mutually_exclusive_group(required=True);backup_target.add_argument('--output');backup_target.add_argument('--output-root')
    serve=sub.add_parser('serve');serve.add_argument('--origin',required=True);serve.add_argument('--port',type=int,default=8080);serve.add_argument('--local-preview',action='store_true')
    serve.add_argument('--open-registration',action='store_true');serve.add_argument('--registration-limit',type=int,default=30);serve.add_argument('--demo-only',action='store_true')
    args=parser.parse_args()
    if args.command=='backup':
        from .hosted_backup import backup_all
        from datetime import datetime, timezone
        import secrets
        destination=args.output or Path(args.output_root)/('snapshot-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3))
        result=backup_all(args.data_dir,destination)
        print(json.dumps(result,ensure_ascii=False));return
    if args.command in ('create-user','reset-password'):
        password=getpass.getpass('输入密码（至少12字符，不会显示）：')
        if password!=getpass.getpass('再输入一次：'):raise SystemExit('两次密码不同，未修改')
        accounts=Accounts(args.data_dir)
        if args.command=='create-user':accounts.create(args.username,password)
        else:accounts.reset_password(args.username,password)
        print('账号已创建' if args.command=='create-user' else '密码已更新，原登录已失效');return
    gateway=Gateway(args.data_dir,args.origin,local_preview=args.local_preview,registration_open=args.open_registration,registration_limit=args.registration_limit,demo_only=args.demo_only)
    if not args.local_preview:
        try:from waitress import serve
        except ImportError:raise SystemExit('请先安装 requirements-hosted.txt；正式入口不会回退到开发服务器')
        print(f'Waitress上游127.0.0.1:{args.port}；正式网址：{gateway.origin}；云调用关闭',flush=True)
        serve(gateway.wsgi(),host='127.0.0.1',port=args.port,threads=8,connection_limit=100,
              channel_timeout=30,max_request_body_size=1024*1024,max_request_header_size=16384,
              expose_tracebacks=False,clear_untrusted_proxy_headers=True)
        return
    server=ThreadingHTTPServer(('127.0.0.1',args.port),gateway.handler());server.timeout=20
    print(f'上游仅监听127.0.0.1:{server.server_port}；正式网址：{gateway.origin}；云调用关闭',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
