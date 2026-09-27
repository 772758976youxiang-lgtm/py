import asyncio
import codecs
import os
import signal
import sys
import tempfile
import time
import uuid
from pathlib import Path
from fastapi import HTTPException

OUTPUT_LIMIT = 128 * 1024


class Runner:
    def __init__(self):
        self.jobs = {}
        self.lock = asyncio.Lock()

    async def start(self, code, timeout, note_id=None):
        async with self.lock:
            if any(not j['task'].done() for j in self.jobs.values()):
                raise HTTPException(409, '已有代码正在运行，请先停止它。')
            while len(self.jobs) >= 30:
                self.jobs.pop(next(iter(self.jobs)))
            job = dict(id=uuid.uuid4().hex, status='running', stdout='', stderr='',
                       exit_code=None, started=time.monotonic(), duration=0, bytes=0,
                       process=None, stdin_closed=False, code=code, note_id=note_id)
            self.jobs[job['id']] = job
            job['task'] = asyncio.create_task(self.execute(job, code, timeout))
            return self.public(job)

    @staticmethod
    def kill(job):
        proc = job['process']
        if proc:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    async def execute(self, job, code, timeout):
        try:
            with tempfile.TemporaryDirectory(prefix='python-lab-') as directory:
                path = Path(directory) / 'main.py'
                path.write_text(code, encoding='utf-8')
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, '-I', '-u', str(Path(__file__).with_name('worker.py')), str(path),
                    cwd=directory, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE, start_new_session=True,
                    env={'PATH': '/usr/bin:/bin', 'LANG': 'en_US.UTF-8', 'HOME': directory})
                job['process'] = proc
                if job['status'] != 'running':
                    self.kill(job)

                async def read(stream, name):
                    decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
                    while True:
                        data = await stream.read(4096)
                        if not data:
                            job[name] += decoder.decode(b'', final=True)
                            break
                        remaining = max(0, OUTPUT_LIMIT - job['bytes'])
                        job[name] += decoder.decode(data[:remaining])
                        job['bytes'] += len(data)
                        if job['bytes'] > OUTPUT_LIMIT and job['status'] == 'running':
                            job['status'] = 'output_limit'
                            self.kill(job)

                readers = [asyncio.create_task(read(proc.stdout, 'stdout')),
                           asyncio.create_task(read(proc.stderr, 'stderr'))]
                try:
                    await asyncio.wait_for(proc.wait(), timeout)
                except asyncio.TimeoutError:
                    if job['status'] == 'running':
                        job['status'] = 'timeout'
                    self.kill(job)
                    await proc.wait()
                finally:
                    # Kill descendants even when the original script already exited.
                    self.kill(job)
                    await asyncio.gather(*readers)
                job['exit_code'] = proc.returncode
                if job['status'] == 'running':
                    job['status'] = 'completed' if proc.returncode == 0 else 'error'
        except asyncio.CancelledError:
            job['status'] = 'stopped'
            self.kill(job)
            if job['process']:
                await job['process'].wait()
            raise
        except Exception:
            job['status'] = 'error'
            job['stderr'] += '\n无法启动 Python 进程。请检查后端运行环境。'
        finally:
            job['duration'] = round(time.monotonic() - job['started'], 3)
            job['stdin_closed'] = True

    def get(self, job_id):
        if job_id not in self.jobs:
            raise HTTPException(404, '运行记录不存在或后端已重启。')
        return self.jobs[job_id]

    @staticmethod
    def public(job):
        result = {k: job[k] for k in ('id', 'status', 'stdout', 'stderr', 'exit_code', 'duration', 'stdin_closed')}
        # A terminal state is published only after both output pipes have drained.
        if not job['task'].done():
            result['status'] = 'running'
            result['duration'] = round(time.monotonic() - job['started'], 3)
        return result

    async def stop(self, job_id):
        job = self.get(job_id)
        if job['status'] == 'running':
            job['status'] = 'stopped'
            self.kill(job)
        await job['task']
        return self.public(job)

    async def write(self, job_id, text, eof):
        job = self.get(job_id)
        proc = job['process']
        if job['status'] != 'running' or not proc or job['stdin_closed']:
            raise HTTPException(409, '当前进程不能接收输入。')
        try:
            if text:
                proc.stdin.write(text.encode('utf-8'))
                await proc.stdin.drain()
            if eof:
                proc.stdin.close()
                job['stdin_closed'] = True
        except (BrokenPipeError, ConnectionResetError):
            raise HTTPException(409, '进程已结束。')
        return self.public(job)

    async def close(self):
        for job in self.jobs.values():
            if not job['task'].done():
                job['status'] = 'stopped'
                self.kill(job)
        await asyncio.gather(*(j['task'] for j in self.jobs.values()), return_exceptions=True)
