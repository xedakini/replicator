import asyncio, logging, os, time
from .Params import OPTS
from .Utils import header_summary, transfer_streams


class _CacheWriter:
    def __init__(self, cacheobj, write_stream):
        self.cache = cacheobj
        self.write_stream = write_stream

    async def write(self, chunk):
        #we're not actually 'async', but transfer_streams() demands that we claim to be
        self.write_stream.write(chunk)
        self.write_stream.flush()  #readers have dup of underlying fd, but do not share the buffer
        self.cache.cur_size += len(chunk)
        self.cache.write_event.set()


class Cache:
    def __init__(self, path):
        self.filepath = path
        self.temppath = None
        self.is_valid = False
        self.is_writable = False
        self.wrier_done = False
        self.cur_size = 0
        self.target_mtime = None
        self.target_size = None
        self.writer_fd = None
        self.have_params = asyncio.Event()  #let readers know they have enough valid info to start
        self.write_event = asyncio.Event()  #allow any readers waiting on cur_size growth to retry
        self.write_done = asyncio.Event()  #XXX hack to work-around a mystery "cancel"laton
        logging.debug('Instantiated cache position %s', self.filepath)

    def __del__(self):
        if self.writer_fd is not None:
            os.close(self.writer_fd)

    def _tryopen(self, path, mode):
        try:
            return os.open(path, mode)
        except:
            return None

    def _tryremove(self, path):
        try:
            os.remove(path)
            return True
        except:
            return None

    def _open_cachefile(self):
        logging.debug('Preparing cache file %s', self.filepath)
        if OPTS.static or OPTS.offline:
            fd = self._tryopen(self.filepath, os.O_RDONLY)
            if fd is not None:
                logging.info('Serving static file directly from cache')
                return fd
        assert not OPTS.offline, f'operating in off-line mode'
        self.is_writable = True
        temppath = self.filepath + OPTS.suffix
        dir_path = os.path.dirname(temppath)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        fd = self._tryopen(temppath, os.O_RDWR)
        if fd is not None:
            logging.debug('Requesting resume of partial file in cache')
            self.temppath = temppath
            return fd
        fd = self._tryopen(self.filepath, os.O_RDWR)
        if fd is not None:
            logging.debug('Reading complete file from cache')
            return fd
        logging.debug('Preparing new file in cache')
        self.temppath = temppath
        return os.open(temppath, os.O_RDWR | os.O_CREAT, mode=0o666)

    async def writer(self, proto):
        try:
            assert self.writer_fd is None, 'invalid second call to .writer within an instance of Cache'
            self.writer_fd = self._open_cachefile()
            stat = os.stat(self.writer_fd)
            self.cur_size = self.target_size = stat.st_size
            self.target_mtime = stat.st_mtime if self.temppath is None else None
            if not self.is_writable:
                self.is_valid = True
                return  #read-only cache - do not make an inquiry against the upstream server
            proto_generator = proto.fetch(self.cur_size, self.target_mtime)
            proto_tuple = await proto_generator.__anext__()
            if proto_tuple is None:
                #revoke any cached file, and bail out
                if self._tryremove(self.filepath):
                    logging.debug('Removed revoked file "%s" from cache', self.filepath)
                if self.temppath:
                    self._tryremove(self.temppath)
                return
            cur_pos, self.target_size, mtime, read_stream = proto_tuple
            if cur_pos is not None:
                self.cur_size = min(cur_pos, self.cur_size)
            if mtime is not None:
                self.target_mtime = mtime
            if self.cur_size == 0:
                logging.debug('Preparing new file in cache')
            with open(self.writer_fd, 'r+b', closefd=False) as write_stream:
                write_stream.seek(self.cur_size)
                write_stream.truncate()
                self.is_valid = True
                self.have_params.set()  #release reader tasks to start tracking data updates
                if read_stream:
                    await transfer_streams(read_stream, _CacheWriter(self, write_stream))
            if self.target_mtime is not None:
                os.utime(self.writer_fd, (self.target_mtime, self.target_mtime))
            if self.cur_size == self.target_size or self.target_size is None:
                if self.temppath:
                    os.rename(self.temppath, self.filepath)
                logging.info('Cached complete file: %s', self.filepath)
            else:
                logging.info('Incomplete download for %s', self.filepath)
            async for _ in proto_generator:
                #give proto the  ability to clean-up after data transfer
                pass
        finally:
            #notify any reader tasks that any further blocking on data will be futile
            self.wrier_done = True
            self.have_params.set()  #failsafe, in case not otherwise called
            self.write_event.set()
            self.write_done.set()  #XXX hack

    async def reader(self, responder, downstream, start_offset=0, end_offset=None):
        await self.have_params.wait()  #wait for writer to report-out the available upstream range
        if not self.is_valid:
            return  #writer does not indicate this entry as valid
        stream = open(os.dup(self.writer_fd), 'rb')
        end = end_offset
        if end is None and self.target_size:
            end = self.target_size
        start = min((start_offset or 0), (end or 0))
        while self.cur_size < start and not self.wrier_done:
            self.write_event.clear()  #wait for writer to get us closer to the starting offset
            await self.write_event.wait()
        if self.target_mtime is not None:
            mtime_str = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(self.target_mtime))
            responder.headers.update({'Last-Modified': mtime_str})
        responder.headers.update({'Server': OPTS.version})
        if end is not None and end <= start:
            responder.headers.update({'Content-Range': f'*/{self.target_size or end}'})
            status = 304 if end == start else 416
            responder.set_status(status)
        elif (start, end) == (0, self.target_size):
            if self.target_size is not None:
                responder.headers.update({'Content-Length': str(self.target_size)})
            responder.set_status(200)
            logging.debug('Replicator responds 200 OK')
        else:
            if self.target_size is not None:
                tsz = self.target_size
                if end:
                    responder.headers.update({'Content-Range': f'{start}-{end-1}/{tsz}'})
                else:
                    responder.headers.update({'Content-Range': f'{start}-/{tsz}'})
            if end:
                responder.headers.update({'Content-Length': str(end - start)})
            responder.set_status(206)
            logging.debug('Replicator responds 206 Partial Content')
        if OPTS.verbose > 1:
            logging.debug('%s', header_summary(responder.headers, heading='Response headers:'))
        #note that we are ignoring any GET content body that the client was odd enough to send...
        await responder.prepare(downstream)
        cursor = start
        while end is None or cursor < end:
            while self.cur_size <= cursor:
                #we've outrun the writer; wait for more data to show up
                if self.wrier_done:
                    break
                self.write_event.clear()
                await self.write_event.wait()
            while True:
                stream.seek(cursor)  #re-synchronize buffer with its underlying file
                n = OPTS.maxchunk if end is None else min(OPTS.maxchunk, end - cursor)
                chunk = stream.read(n) if n > 0 else None
                if not chunk:
                    break
                cursor += len(chunk)
                if end is not None and cursor >= end:  #XXX hack
                    await self.write_done.wait()  #XXX  hack
                await responder.write(chunk)
            if self.wrier_done:
                break  #no more data will be forthcoming
        logging.debug('Successfully transferred %s', self.filepath)
