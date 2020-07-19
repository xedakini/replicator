import aiohttp, email, calendar, logging, re, time
from .Params import OPTS
from .Utils import header_summary, transfer_streams


class HttpProtocol:
    def __init__(self, request):
        self.url = request.url
        self.cacheid = request.cacheid
        self.headers = request.headers.copy()
        self.content = request.content

    def _parse_content_range(self, crange):
        match = re.search(r'^bytes (\d+)-(\d*)(/\d+)?$', crange)
        assert match, f'invalid content-range: {crange}'
        begin = int(match.group(1))
        if not match.group(2):
            return begin, None
        end = int(match.group(2)) + 1
        size = match.group(3)
        assert begin < end
        assert size is None or size == '/*' or int(size[1:]) == end
        return begin, end

    async def fetch(self, cached_size, cached_time):
        logging.info('Requesting GET of %s from upstream HTTP server', self.url)
        self.headers.pop('Range', None)  #we don't care about the client's requested range here
        if cached_size > 0:
            if cached_time:
                logging.debug('Checking complete file in cache')
                strtime = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(cached_time))
                self.headers.update({'If-Range': strtime})
            self.headers.update({'Range': f'bytes={cached_size}-'})
        if OPTS.verbose > 1:
            logging.debug('%s', header_summary(self.headers, heading='GET headers:'))
        timeout = aiohttp.ClientTimeout(sock_connect=OPTS.timeout, sock_read=OPTS.timeout)
        async with aiohttp.ClientSession(**OPTS.proxy) as session:
            async with session.get(self.url,
                                   timeout=timeout,
                                   headers=self.headers,
                                   data=self.content) as response:
                logging.debug('Server responds %d %s', response.status, response.reason)
                if response.status in (403, 404):
                    yield None  #revoke cache entry
                    return
                if response.status in (304, 416):
                    yield cached_size, cached_size, cached_time, None  #cache is current
                    return
                assert response.status in (200, 206), f'Unhandled response code: {response.status}'
                xfer_enc = response.headers.get('transfer-encoding', 'unknown').lower()
                logging.debug('transfer-encoding: %s', xfer_enc)
                cache_seek, range_end = 0, response.content_length  #default to ignore cache
                if response.status == 206:
                    crange = response.headers.get('content-range', 'none specified')
                    cache_seek, range_end = self._parse_content_range(crange)
                mtime = response.headers.get('last-modified', None)
                if mtime:
                    mtime = calendar.timegm(email.utils.parsedate(mtime))
                if (range_end or 0) <= cache_seek:
                    range_end = None
                yield cache_seek, range_end, mtime, response.content
                return


# we do not cache non-GET requests; pass request through verbatim
# (except for the removal of some proxy-related headers)
async def blind_transfer(request, output, downstream):
    logging.info('Making blind %s request for %s', request.method, request.url)
    assert not OPTS.offline, f'Blind transfers are incompatible with "offline" mode'
    timeout = aiohttp.ClientTimeout(sock_connect=OPTS.timeout, sock_read=OPTS.timeout)
    async with aiohttp.ClientSession(**OPTS.proxy) as session:
        async with session.request(request.method,
                                   request.url,
                                   timeout=timeout,
                                   headers=request.headers,
                                   data=downstream.content) as upresp:
            logging.debug('Upstream server responded %s - %s', upresp.status, upresp.reason)
            output.set_status(upresp.status, upresp.reason)
            output.headers.update(upresp.headers)
            await output.prepare(downstream)
            await transfer_streams(upresp.content, output)
