import asyncio, calendar, logging, re, time
from .Params import OPTS


class FtpProtocol:
    def __init__(self, request):
        self.path, self.cacheid = request.path, request.cacheid
        self.host, self.port = request.host, request.port
        self.reader = self.writer = None

    async def _get_result(self):
        #read a response from server, allowing for line continuations
        line = (await self.reader.readline()).decode()
        assert line, 'FTP connection closed prematurely'
        code, result = line[:3], line[4:]
        assert code.isdigit(), f'Expected response with numeric code, got {line}'
        assert line[3] == ' ' or line[3] == '-', f'Malformed response: {line}'
        while line:
            if 4 <= len(line) and line[3] == ' ' and line[:3] == code:
                break
            line = (await self.reader.readline()).decode()
            if len(result) < 8000:
                #bound memory consumption; should not be needed with non-malicious servers
                result += line
        return int(code), result.rstrip('\r\n')

    async def _send_cmd(self, cmd, expect, etext, accept=None):
        if cmd is not None:
            self.writer.write((cmd + '\r\n').encode())
        code, message = await self._get_result()
        if expect is None:  #caller wants to handle result checking itself
            return code, message
        if code == accept:
            return None
        assert code == expect, f'server sends {code}; expected {expect} ({etext})'
        return message

    async def fetch(self, cached_size, cached_time):
        #connect to FTP server:
        logging.info('Making FTP connection to %s port %d', self.host, self.port)
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        await self._send_cmd(None, 220, 'service ready')
        #login:
        await self._send_cmd(f'USER anonymous', 331, 'need password')
        await self._send_cmd(f'PASS anonymous@', 230, 'user logged in', 550)
        #request binary mode transfers:
        await self._send_cmd(f'TYPE I', 200, 'binary mode ok')
        #get mtime:
        message = await self._send_cmd(f'MDTM {self.path}', 213, 'file status', 550)
        try:
            mtime = calendar.timegm(time.strptime(message, '%Y%m%d%H%M%S'))
        except:
            raise AssertionError('Modification time on FTP server is invalid (does file exist?)')
        logging.debug('FTP server modification time: %s', message)
        #get size:
        message = await self._send_cmd(f'SIZE {self.path}', 213, 'file status', 550)
        assert message and message.isdigit(), f'File size on FTP server is unknown'
        size = int(message)
        logging.debug('FTP server file size: %d', size)
        #sanity check:
        if (cached_time is not None and cached_time < mtime) or size < cached_size:
            logging.debug('Resetting cache file for full data replacement')
            cached_size = 0
        if size == cached_size:
            #nothing to do
            await self._send_cmd('QUIT', None, None)
            yield cached_size, size, mtime, None
            return
        #open data channel:
        # [prefer EPSV (modern, IPv6 friendly), fall-back to PASV (legacy, IPv4 only)]
        code, message = await self._send_cmd(f'EPSV', None, None)
        if code == 229:
            match = re.search(r'\((.)\1\1(\d+)\1\)', message)
            assert match, f'could not parse port from EPSV response ({message})'
            peer_port = int(match.group(2))
            peer_addr = self.host
        else:
            await self._send_cmd(f'PASV', 227, 'passive mode')
            match = re.search(r'(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)', message)
            assert match, f'could not parse address from PASV response ({message})'
            ip1, ip2, ip3, ip4, p_hi, p_lo = match.groups()
            peer_port = int(p_lo) + 256 * int(p_hi)
            peer_addr = f'{ip1}.{ip2}.{ip3}.{ip4}'
        logging.debug('Making FTP data channel connection to %s port %d', peer_addr, peer_port)
        data_reader, data_writer = await asyncio.open_connection(peer_addr, peer_port)
        data_writer.write_eof()
        #prepare to retreive data from the data channel:
        if size:
            await self._send_cmd(f'REST {cached_size}', 350, 'pending further information')
        await self._send_cmd(f'RETR {self.path}', 150, 'file ok', 550)
        #transfer control back to caller:
        yield cached_size, size, mtime, data_reader
        #clean-up:
        data_writer.close()
        await data_writer.wait_closed()
        await self._send_cmd(None, 226, 'transfer complete')
        await self._send_cmd('QUIT', None, None)
        self.writer.close()
        await self.writer.wait_closed()
