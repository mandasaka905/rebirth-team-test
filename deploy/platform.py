"""Container/PaaS entry point with an explicitly configured persistent directory and HTTPS origin."""
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rebirth.hosted import Gateway


def configuration(env):
    origin=env.get('REBIRTH_PUBLIC_ORIGIN') or env.get('RENDER_EXTERNAL_URL')
    if not origin and env.get('RAILWAY_PUBLIC_DOMAIN'):origin='https://'+env['RAILWAY_PUBLIC_DOMAIN']
    if not origin:raise ValueError('请先配置正式HTTPS网址 REBIRTH_PUBLIC_ORIGIN；不会信任访客传入的域名')
    directory=env.get('REBIRTH_DATA_DIR')
    if not directory:raise ValueError('请将持久磁盘挂载后配置 REBIRTH_DATA_DIR，不能使用临时文件系统保存账号')
    if not Path(directory).is_absolute():raise ValueError('数据目录需要使用持久磁盘内的绝对路径')
    port=int(env.get('PORT','8080'))
    if not 1<=port<=65535:raise ValueError('端口应在1至65535之间')
    return dict(data_dir=directory,origin=origin,registration_open=env.get('REBIRTH_REGISTRATION_OPEN','false').lower()=='true',
                demo_only=env.get('REBIRTH_DEMO_ONLY','true').lower()=='true',registration_limit=int(env.get('REBIRTH_REGISTRATION_LIMIT','30'))),port


def main():
    config,port=configuration(os.environ)
    folder=Path(config['data_dir']).resolve()
    volume=Path(os.environ.get('REBIRTH_VOLUME_PATH','/data')).resolve()
    if os.name=='posix' and os.environ.get('REBIRTH_REQUIRE_VOLUME','true').lower()=='true':
        mounts=Path('/proc/self/mountinfo')
        mounted=[]
        if mounts.exists():mounted=[Path(line.split(' - ',1)[0].split()[4].replace('\\040',' ')).resolve() for line in mounts.read_text().splitlines()]
        if volume not in mounted:raise SystemExit('未检测到持久卷挂载，停止启动以避免重启后丢失账号和测试记录')
    if os.name=='posix' and os.getuid()==0:
        if volume==Path('/') or folder==volume or not folder.is_relative_to(volume):
            raise SystemExit('数据目录必须是已配置持久卷内的子目录，例如 /data/state')
        folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chown(folder,10001,10001)
        os.setgroups([]);os.setgid(10001);os.setuid(10001)
    gateway=Gateway(**config)
    from waitress import serve
    print(f'网站服务已启动：{gateway.origin}；账号数据使用独立目录；云调用关闭',flush=True)
    serve(gateway.wsgi(),host='0.0.0.0',port=port,threads=8,connection_limit=100,channel_timeout=30,
          max_request_body_size=1048576,max_request_header_size=16384,expose_tracebacks=False,clear_untrusted_proxy_headers=True)


if __name__=='__main__':main()
