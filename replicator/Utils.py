import asyncio, os, sys, time
from .Params import OPTS


def daemonize():
    with open('/dev/null', 'r') as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())
    if not OPTS.daemon:
        return

    try:
        # attempt most os activity early, to catch errors before we fork
        os.umask(0o022)  # -rw-r--r-- / 0644 / u=rw,go=r
        pidout = OPTS.pidfile and open(OPTS.pidfile, 'w')
        #first fork: create intermediate child process
        pid = os.fork()
    except IOError as e:
        sys.exit(f'error: failed to open {e.filename}')
    except OSError as e:
        sys.exit(f'error: failed to fork process: {e.strerror}')
    except Exception as e:
        sys.exit(f'error: {e}')

    if pid:
        #parent process waits for its child to {create daemon, then exit}, then exits
        cpid, status = os.waitpid(pid, 0)
        sys.exit(status >> 8)

    try:
        #second fork: create the daemon grandchild
        pid = os.fork()
    except Exception as e:
        sys.exit(f'error: {e}')

    if pid:
        #child successfully spawned grandchild; report grandchild pid and exit child
        if pidout:
            pidout.write(str(pid))
            pidout.close()
        else:
            print(pid)
        sys.exit(0)

    #in new daemon grandchild; attach stdout and stderr to the log file descriptor
    os.dup2(OPTS._logstream.fileno(), sys.stdout.fileno())
    os.dup2(OPTS._logstream.fileno(), sys.stderr.fileno())
    os.setsid()  #make the daemon its own session leader; should not fail, given its fresh pid


def header_summary(headers, *, prefix='  ', maxlinelen=79, heading=None):
    summary = []
    if heading is not None:
        summary.append(heading)
    if prefix is None:
        prefix = ''
    for k, v in headers.items():
        line = f'{prefix}{k}: {v}'
        if maxlinelen is not None and maxlinelen < len(line):
            line = line[:maxlinelen - 3] + '...'
        summary.append(line)
    return '\n'.join(summary)


async def transfer_streams(reader, writer):
    while True:
        start_time = time.time()
        chunk = await reader.read(OPTS.maxchunk)
        if not chunk:
            break
        await writer.write(chunk)
        if OPTS.limit:
            target_time = len(chunk) / OPTS.limit
            elapsed_time = time.time() - start_time
            if elapsed_time < target_time:
                await asyncio.sleep(target_time - elapsed_time)
