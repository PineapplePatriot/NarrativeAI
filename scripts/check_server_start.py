"""Smoke-check startup/exit signal handling with stand-in executables; no real DB or server."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

source = Path(__file__).resolve().parent / 'start-server.sh'
with tempfile.TemporaryDirectory(prefix='pulse-start-check-') as tmp:
    folder=Path(tmp)
    stub='''#!SHEBANG
import os,signal,sys,time
from pathlib import Path
root=Path(os.environ['STUB_DIR'])
name=Path(sys.argv[0]).name
if name=='python' and 'migrate' in sys.argv:
    sys.exit(9 if os.environ.get('FAIL_MIGRATE') else 0)
if name=='python' and 'pulse_tick' not in sys.argv:
    sys.exit(0)
kind='worker' if name=='python' else 'web'
def stop(*args):
    (root/(kind+'.stopped')).write_text('yes')
    sys.exit(0)
signal.signal(signal.SIGTERM,stop)
(root/(kind+'.pid')).write_text(str(os.getpid()))
if kind=='web' and not os.environ.get('KEEP_WEB'):
    until=time.monotonic()+5
    while not (root/'worker.pid').exists() and time.monotonic()<until:
        time.sleep(.01)
    sys.exit(7)
while True:
    time.sleep(.1)
'''.replace('SHEBANG',sys.executable)
    for name in ['python','gunicorn']:
        path=folder/name;path.write_text(stub);path.chmod(0o700)
    env={**os.environ,'PATH':str(folder)+os.pathsep+os.environ.get('PATH',''),'STUB_DIR':str(folder)}
    result=subprocess.run(['sh',str(source)],env=env,timeout=10)
    assert result.returncode==7,result.returncode
    assert (folder/'worker.stopped').exists(),'Worker was left running after web exit.'
    for path in folder.glob('*.pid'):path.unlink()
    for path in folder.glob('*.stopped'):path.unlink()
    process=subprocess.Popen(['sh',str(source)],env={**env,'KEEP_WEB':'1'})
    try:
        until=time.monotonic()+5
        while not ((folder/'worker.pid').exists() and (folder/'web.pid').exists()) and time.monotonic()<until:
            time.sleep(.01)
        assert (folder/'web.pid').exists()
        process.send_signal(signal.SIGTERM);process.wait(timeout=10)
        assert (folder/'web.stopped').exists(),'Web did not receive shutdown signal.'
        assert (folder/'worker.stopped').exists(),'Worker did not receive shutdown signal.'
    finally:
        if process.poll() is None:process.kill();process.wait()
    for path in folder.glob('*.pid'):path.unlink()
    result=subprocess.run(['sh',str(source)],env={**env,'FAIL_MIGRATE':'1'},timeout=10)
    assert result.returncode==9
    assert not list(folder.glob('*.pid')),'Processes started despite failed migration.'
print('Startup migration guard, web-exit cleanup, and graceful timer/web shutdown passed.')
