"""Resource-limited local worker; this is NOT a security sandbox."""
import resource
import sys
import traceback

# Avoid core dumps and accidental giant files. Wall-time/output limits live in runner.py.
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_CPU, (65, 66))
resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
# Linux supports a useful virtual memory cap; macOS does not reliably support RLIMIT_AS.
if sys.platform.startswith('linux'):
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))

path = sys.argv[1]
try:
    with open(path, encoding='utf-8') as f:
        code = compile(f.read(), 'main.py', 'exec')
    exec(code, {'__name__': '__main__', '__file__': 'main.py'})
except SystemExit:
    raise
except BaseException as error:
    traceback.print_exception(type(error), error, error.__traceback__.tb_next)
    sys.exit(1)
