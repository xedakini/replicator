#! /usr/bin/python
#
#  This module contains the main code for the replicator proxy server.
#  The server can be run either manually or as a daemon started by this <init.html> init script.
#  In the manual case the program does not use a configuration file but can be controlled entirely from the command line.
#  User feedback is sent to stdout and files are cached in the current directory.
#  In the daemon case the settings are read from the configuration_file <http-replicator.conf.html> and feedback is written to a log.
#  This feedback can still be monitored in real time via a telnet connection.
#
#  The server uses the medusa <http://www.nightmare.com/medusa> framework, which (as of version 1.5.2) is part of python as module asyncore <http://www.python.org/doc/current/lib/module-asyncore.html>.
#  Because of this the server runs as a single process, multiplexing I/O with its various client and server connections within a single process/thread.
#  According to the readme <http://www.nightmare.com/medusa/README.html> this means it is capable of smoother and higher performance than most other servers, while placing a dramatically reduced load on the server machine.

import asyncore, socket, os, time, calendar, sys, re, optparse

#  constants
#
#  Only three constants can't be changed from the command line.
#  The [CHUNK] constant sets the maximum amount of bytes that are sent or received in a single chunk.
#  The default 64k value will probably never be met during real downloads; its main purpose is to define the chunk size for files that are read from cache.
#  For that situation the default seems optimal.
#  The [TIMEFMT] constant is the format in which http servers send the time (and in which they expect it back).
#  It is meant for use with the [strptime] and [strftime] functions from the time <http://www.python.org/doc/current/lib/module-time.html> module.
#  The [INDENT] constant defines the indentation of http header and traceback blocks in user feedback.

CHUNK = 65536 # maximum number of bytes to read and write in one chunk
TIMEFMT = '%a, %d %b %Y %H:%M:%S GMT' # http time format
INDENT = ' ' # header and traceback indentation

#  class Listener
#
#  Class [Listener] is a subclass of [asyncore.dispatcher].
#  Its purpose is to monitor incoming requests at the specified [port] and create an instance of [object] for each one.
#  Class [object] should be a subclass of [asyncore.dispatcher] and should only take a socket parameter, just like the original [asyncore.dispatcher] class.
#  It suffices to create the instance: being a subclass of [asyncore.dispatcher] it will add itself to the [asyncore.socket_map] so it won't get garbage-collected.
#  The main [asyncore.loop] takes care of the rest.
#
#  For security reasons the ip addresses for which incoming requests are accepted must be explicitly listed in the [iplist].
#  The addresses may contain the ? and * wildcards for single and multiple digits.
#  They are transformed into a single regular expression to create the [ipcheck] function.
#  Whenever the [asyncore.loop] notices an incoming request the [handle_accept] member function is called.
#  Here the caller address is checked against [ipcheck] and an instance of [object] is created if permission is granted.

class Listener (asyncore.dispatcher):

	def __init__ (self, object, port, iplist):

		asyncore.dispatcher.__init__(self) # original constructor

		self.create_socket(socket.AF_INET, socket.SOCK_STREAM) # create socket
		self.set_reuse_addr() # make sure the port can be reopened
		self.bind(('', port)) # listen on localhost:port
		self.listen(5) # handle max 5 simultaneous connections

		ipstring = '^'+'|'.join([ip.replace('?','\d').replace('*','\d+').replace('.','[.]') for ip in iplist])+'$'
		self.ipcheck = re.compile(ipstring).match # compile regular expression
		self.object = object # save object class

	def handle_accept (self):

		sock, address = self.accept() # get information about the caller
		if self.ipcheck(address[0]): # check caller's permission
			self.object(sock) # create object instance
		else: # no permission for caller
			print 'Listener', 'Blocked request from %s:%i' % address

#  class Telnet
#
#  Class [Telnet] is a subclass of [asyncore.dispatcher], just as [Listener].
#  This class does not handle incoming requests itself but gets created by a [Listener] instance whenever a request is made at its port.
#  The constructor is not modified so the socket parameter is handled automatically.
#  This class is not used when the replicator is run manually.
#  It is here for when replicator is run as a daemon and [sys.stdout] is redirected to a file object or similar.
#  Note: this is mandatory as [sys.stdout] must seekable.
#  When a [Listener] instance for this class is created, it is possible to view replicator's output through a telnet connection.
#
#  Operation is as follows.
#  When the [asyncore.loop] signals incoming data (someone's typing in the telnet session), [handle_read] reads and looses it.
#  In the other direction [writable] compares the pointer position of [sys.stdout] with its own [pointer].
#  In case of a non match, asyncore calls [handle_write] to send the unsent in chunks of size [CHUNK] and update the [pointer].
#  After each call the [sys.stdout] file pointer is moved to the end of the file to make sure that future print calls are appended.

class Telnet (asyncore.dispatcher):

	pointer = 0 # number of written bytes

	def writable (self):

		return sys.stdout.tell() > self.pointer # compare pointers

	def handle_write (self):

		sys.stdout.seek(self.pointer) # sys.stdout must be seekable!
		self.pointer += self.send(sys.stdout.read(CHUNK)) # self.send returns number of sent bytes
		sys.stdout.seek(0,2) # move to end of file

	def handle_read (self):

		self.recv(CHUNK) # read max CHUNK bytes at a time

	def handle_close (self):

		self.close() # close socket and remove from asyncore map

#  class Http
#
#  Class [Http] is yet another subclass of [asyncore.dispatcher].
#  It is not meant for standalone use but should be subclassed to provide two additional handling functions: [handle_header] and [handle_data], which are respectivily called after the http [header] and [data] are received.
#  The [HttpClient] and [HttpServer] classes do this, and together handle communication between the calling http client and the called http server.
#  Each instance refers to its counterpart via the [other] variable.
#  The three constants [static], [flat] and [debug] can be set from the command line to change the server's operating mode.
#
#  This class handles everything that the http request from the client and the response from the server have in common:
#  * The first line consists of three fields.
#  * This is followed by a series of key: value lines.
#  * All lines are terminated by CRLF, the last line of the header by a double CRLF.
#  * This is followed by an optional message body.
#
#  The top header line is split in a three element list and the rest of the header transformed into a dictionary.
#  Then [handle_header] is called.
#  This function prepares the second part of the transmission and the main (only) purpose of this proxy: caching.
#  When the connection is closed [handle_data] is called to finish this task.
#
#  Procedure is quite different from that of the [Telnet] class.
#  Function [writable] does not only return true when there is unwritten data but also when the connection can be closed.
#  This is the case when counterpart [other] is closed and all its data has been sent.
#  The connection is closed next time [handle_write] is called in response to this positive return value.
#  The counterpart is considered closed when its backreference [other] is deleted.
#  This reference is explicitly deleted on the [HttpServer] side because cyclic references make the garbage collector fail, which means the instance would never be deleted.
#  What exactly happens in that case is shown here <http://www.nightmare.com/medusa/memory-leaks.html>.
#
#  Incoming and outgoing data is divided in a [header] and [data], which reflects the structure of an http transmission.
#  This division is made in [handle_read].
#  The data is read in blocks of [CHUNK] bytes max and stored in the [header] string as long as the http header is not completed.
#  Once the complete header is received it is parsed in a list [head] and dictionary [body] and [handle_header] is called.
#  Here [body] and [head] (mutable) can be altered.
#  A file object [data] should be prepared for the second part of the transmission.
#  Upon return [head] and [body] are changed back into the [header] string.
#  All following data is read directly into the [data] file.
#  A function that reads from this [data] should always return its pointer to the end of the file.
#
#  The code is not as fail safe as one might think necessary.
#  For example the top header line is split in a three element list without first checking if it actually contains three elements.
#  This is because asyncore has its own mechanism for catching errors.
#  Of course, when all clients and servers work by the book these errors don't occur.
#  If one doesn't then asyncore catches the exception and calls the [handle_error] member function, which then closes the socket.
#  The function is rewritten to crash in [debug] mode or otherwise print a traceback message that is a bit clearer than the default.

class Http (asyncore.dispatcher):

	pointer = 0 # number of sent bytes
	header = '' # http header string
	data = None # http data file object
	other = None # counterpart Http instance
	id = 0 # instance identification number

	static = False # static mode: never check for modifications
	flat = False # flat mode: save files in a single directory
	debug = False # debug mode: crash on exceptions

	def __str__ (self):

		return '%s %i' % (self.__class__.__name__, self.id) # string representation for stdout feedback

	def writable (self):

		return self.other and self.other.data and (len(self.other.header) + self.other.data.tell() > self.pointer or not self.other.other)

	def handle_write (self):

		offset = self.pointer - len(self.other.header) # sent bytes counting from data

		if offset < 0: # header not completely sent
			self.pointer += self.send(self.other.header[self.pointer:]) # send header
		elif offset < self.other.data.tell(): # data not completely sent
			self.other.data.seek(offset) # move to pointer position
			self.pointer += self.send(self.other.data.read(CHUNK)) # send data
			self.other.data.seek(0,2) # move back to end of file
		else: # nothing to write
			self.handle_close() # close instance

	def handle_read (self):

		if self.data: # header is complete
			self.data.write(self.recv(CHUNK)) # read directly into data file
			return

		self.header += self.recv(CHUNK) # append data to header string
		crlf = self.header.find('\r\n\r\n') # first occurence of a double CRLF
		lf = self.header.find('\n\n') # first occurence of a double LF
		if crlf > -1 and not -1 < lf < crlf: # this is the official format
			lines = self.header[:crlf].splitlines() # split head..
			data = self.header[crlf+4:] # ..from data
		elif lf > -1: # sometimes servers use a double linefeed instead
			lines = self.header[:lf].splitlines() # split head..
			data = self.header[lf+2:] # ..from data
		else: # header is not yet complete
			return

		if self.other: # counterpart is present
			self.id = self.other.id # use same id
		else:
			self.id = Http.id = Http.id + 1 # use next available id

		print self, 'Received header from %s:%i' % self.addr
		print
		headstr = lines.pop(0) # pop top header line from list
		print INDENT, headstr
		head = headstr.split(' ', 2) # split in a three element list
		body = {} # start a new dictionary
		for line in lines: # iterate over the other header lines
			print INDENT, line
			key, value = line.split(':', 1) # split line at the colon
			body[key.lower()] = value.strip() # build dictionary with lowercase keys
		print
		self.handle_header(head, body, data) # call subclass function: handle_header
		self.header = '\r\n'.join([' '.join(head)]+map(': '.join, body.items())+['','']) # rebuild header

	def handle_error (self):

		type, value, traceback = sys.exc_info() # get exception info
		if self.debug or type is KeyboardInterrupt: # server is in debug mode or manually killed
			raise # crash!

		print self, 'Error:', value
		print
		print INDENT, 'TRACEBACK'
		while traceback: # iterate over traceback objects
			code = traceback.tb_frame.f_code
			print INDENT, '%s (file %s, line %i)' % (code.co_name, code.co_filename, traceback.tb_lineno)
			traceback = traceback.tb_next
		print
		self.close() # close socket and remove from asyncore map

	def handle_close (self):

		self.handle_data() # call subclass function: handle_data
		self.close() # close socket and remove from asyncore map
		print self, 'Closed'

#  class HttpClient
#
#  Class [HttpClient] is one of the two subclasses of [Http].
#  Instances are created by a [Listener] instance for each http request that is made through the proxy server.
#  Once the http header is received [handle_header] is called.
#  Here the header is altered and the connection to the requested http server is made.
#  In most cases no data follows and even if it does (post request) it is not used so [handle_data] is empty.
#
#  An http client sends a different header to a proxy server than it does to a normal http server.
#  The most important difference is that to a proxy the full url is sent, including http://host.
#  Many servers require a relative path, so it is up to the proxy to make this right.
#  It was a lack of this that made the previous version of replicator fail on a large number of websites.
#  Another important change is to force a connection close after each single transfer.
#  HTTP/1.1 supports leaving the connection open for following requests but this is not supported by replicator.
#  Content encodings and range requests are also not supported.
#
#  The majority of the code involves replicator's main purpose: caching.
#  When a client sends a GET request it is first checked if the requested file can be cached.
#  In [flat] mode all files are cached directly in the working directory so unknown filenames (urls ending with a slash) are ignored.
#  When not in [flat] mode the unknown filenames are replaced by index.html, just like wget <http://www.gnu.org/software/wget/wget.html> does.
#  This has the great advantage that recursive wget downloads can be easily merged with the replicator cache.
#  If the requested file can be cached the [asyncore.socket_map] is first searched for identical transfers.
#  If these are not found the cache is searched for presence of the requested [file].
#  The [static] constant determines if the server should be contacted to check for modification or if the file should be served from cache directly.
#
#  Returning a file or a message without contacting a server first cannot be fit into asyncore very naturally.
#  It is done by creating a class [LocalResponse] that emulates a socket.
#  This fake socket produces a standard http response and ignores everything that is sent to it.
#  For example, when a file in cache should be served directly, [LocalResponse(304)] fakes a 'not modified' reponse, to which the [HttpServer] counterpart responds by serving the file.

class HttpClient (Http):

	spliturl = re.compile(r'^http://([^/:]+):*([^/]*)/*(.*?)([^/]*)$').match # split url in http://(host):(port)/(dirs)(file)
	null = open('/dev/null','r+') # garbage file

	def handle_header (self, head, body, data):

		host, port, dirs, file = self.spliturl(head[1]).groups() # parse url
		port = port and int(port) or 80 # use port 80 if it is not specified
		head[1] = '/'+dirs+file # transform absolute url to a relative one
		if not self.flat: # not in flat mode
			file = os.path.join(host, dirs, file or 'index.html') # use full path

		body['connection'] = 'close' # close connection after transfer
		body['host'] = host # make sure the host is sent
		body.pop('keep-alive', None)
		body.pop('proxy-connection', None)
		body.pop('range', None) # always fetch entire file
		body.pop('accept-encoding', None) # no support for content encodings

		if head[0] == 'GET' and file: # a download request for a known file

			self.data = self.null # no data should follow

			for object in asyncore.socket_map.values(): # search for identical transfers
				if object.__class__ is HttpServer and object.file == file:
					print self, 'Joined', object
					self.other = object # make this the counterpart
					return

			in_cache = os.path.isfile(file) # check if file exists

			if self.static and (in_cache or 'if-modified-since' in body): # static mode and file is in some cache
				other = HttpServer(LocalResponse(304)) # fake 'not modified' response
			elif in_cache: # dynamic mode and file is in replicator cache
				other = HttpServer(self.getsocket(host, port)) # connect to server
				mtime = os.path.getmtime(file) # get cache date
				value = body.get('if-modified-since') # get optional private cache date
				if not value or mtime > calendar.timegm(time.strptime(value, TIMEFMT)): # check the most recent
					print self, 'Checking for modification since', time.ctime(mtime)
					body['if-modified-since'] = time.strftime(TIMEFMT, time.gmtime(mtime))
			else: # file is new
				other = HttpServer(self.getsocket(host, port)) # connect to server

			other.file = file
			other.in_cache = in_cache

		elif head[0] == 'POST': # an upload request

			if 'content-length' in body:
				self.data = os.tmpfile() # this is the only case where data should follow
				self.data.write(data) # write already received data
				other = HttpServer(self.getsocket(host, port)) # connect to server
			else:
				print self, 'Error: unspecified content length in post request'
				self.data = self.null
				other = HttpServer(LocalResponse(503))

		else: # any other request

			self.data = self.null # no data should follow
			other = HttpServer(self.getsocket(host, port)) # connect to server

		self.other = other # HttpClient references HttpServer..
		other.other = self # ..and vice versa

	def handle_data (self):

		pass

	def getsocket (self, host, port):

		print self, 'Connecting to', host
		try:
			assert port == 80 or port > 1024, 'illegal attempt to connect to port %i' % port # security
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # create socket
			sock.settimeout(30.) # give up after 30 seconds; only affects connect
			sock.connect((host, port)) # connect to server
		except: # connection failed
			print self, 'Failed:', sys.exc_info()[1]
			return LocalResponse(503) # fake 'service unavailable' response
		else: # connection succeeded
			return sock

#  class HttpServer
#
#  Class [HttpServer] is the other subclass of [Http], the counterpart of [HttpClient].
#  Instances of [HttpServer] are created by the [HttpClient.handle_header] function.
#  The purpose of this class is to interpret the http server's response to the client's request and act accordingly, caching everything that can possibly be cached.
#
#  The top line of an http response header is different from a http request but still consists of three fields; the middle one is a status integer.
#  A value of 200 denotes a successful download.
#  If [file] is set then this is the response to a GET request.
#  In that case [to_cache] is set and relevant items from the body dictionary like file size and transfer encoding are saved for later use.
#  Data is written to a temporary file [data] as long as not everyting is received.
#  If [to_cache] is set then [handle_data] copies the file to its final cache position.
#  This prevents the incomplete file from being mistakenly served after a server crash.
#
#  A return value of 304 is a response to an if-modified-since headerline and signifies that a file is up to date.
#  If [in_cache] is set then the requested file is in cache and the http request was altered by the [HttpClient] instance.
#  The http response header is transformed into a 200 OK response and the file is opened for reading in [data].
#  If [in_cache] is not set the response is sent unaltered; in that case the headerline was provided by the client to check a private cache.
#
#  The [handle_close] code that copies the [data] to cache is contained in a large [try..except] block.
#  As soon as something goes wrong during that operation the file is removed and the data is discarded.
#  Examples of possible errors are too long filenames and chunked data that does not comply with the protocol <http://www.w3.org/Protocols/rfc2616/rfc2616-sec3.html#sec3.6.1>.
#  The target directory is prepared by the [prepare] member function.
#  This function is similar to [os.makedirs] except that it deletes files that are blocking the way.
#  These files may have been put in the wrong position when their request lacked a trailing slash.

class HttpServer (Http):

	file = None # filename
	time = None # time as supplied by the server
	size = None # filesize
	chunked = False # transfer encoding

	in_cache = None # file is in cache
	to_cache = None # file goes to cache

	def handle_header (self, head, body, data):

		if head[1] == '200' and self.file: # 200 OK: file is being sent

			print self, self.in_cache and 'Too old:' or 'Not in cache:', self.file

			self.data = os.tmpfile() # open temporary file
			self.data.write(data) # write already received data
			self.to_cache = True # file goes to cache

			value = body.get('date') # current time
			if value:
				self.time = calendar.timegm(time.strptime(value, TIMEFMT))
			value = body.get('content-length') # file size
			if value:
				self.size = int(value)
			value = body.get('transfer-encoding') # transfer encoding
			if value:
				if value.lower() == 'chunked': # chunked transfer encoding
					self.chunked = True
				else: # unknown encoding
					print self, 'Unsupported transfer encoding:', value
					self.to_cache = False # don't cache

		elif head[1] == '304' and self.in_cache: # 304 Not modified: file in cache is up to date

			print self, 'In cache:', self.file

			self.data = open(self.file, 'r') # data is read from cache
			self.data.seek(0,2) # move to end of file

			head[1] = '200' # transform into a 200 OK response
			head[2] = 'OK'
			body['content-length'] = str(self.data.tell()) # supply file size

		else:

			self.data = os.tmpfile() # open temporary file
			self.data.write(data) # write already received data

	def handle_data (self):

		del self.other # remove cross reference
		if not self.to_cache:
			return # nothing else to do

		print self, 'Storing', self.file
		try: # fail-safe approach
			file = None # file is not yet created
			if self.size: # filesize is known
				assert self.size == self.data.tell(), 'size mismatch' # check size

			self.prepare(self.file) # create directories
			file = open(self.file, 'w') # open file for writing

			self.data.seek(0) # move to beginning of file
			chunk = CHUNK # write chunks of CHUNK bytes or..
			if self.chunked: # ..in case of chunked transfer..
				print self, 'Post processing chunked data'
				chunk = int(self.data.readline().split(';')[0], 16) # ..use chunk size from header
			data = self.data.read(chunk) # read first chunk
			while data: # loop until out of data
				if self.chunked:
					assert self.data.read(2) == '\r\n', 'chunked data error' # check if data follows the protocol
					chunk = int(self.data.readline().split(';')[0], 16)
				file.write(data) # write data chunk
				data = self.data.read(chunk) # read next chunk

			if self.time: # current time from server is known
				os.utime(self.file, (self.time, self.time)) # synch creation time with server
		except: # something went wrong
			print self, 'Failed:', sys.exc_info()[1]
			if file: # error occured after file was created
				file.close()
				os.remove(self.file)

		self.data.seek(0,2) # always leave file pointer at end of file

	def prepare (self, name):

		dir = os.path.dirname(name)
		if dir and not os.path.isdir(dir): # directory does not yet exist
			if os.path.isfile(dir): # a directory not ending with a slash may have been cached as a file
				print self, 'Warning: directory %s mistaken for a file' % dir
				os.remove(dir) # delete; it should not have been cached in the first place
			else: # neither a file nor a directory
				self.prepare(dir) # recurse
			os.mkdir(dir) # create missing directory

#  class LocalResponse
#
#  Class [LocalResponse] emulates a socket, enabeling replicator to respond to a client without actually connecting to a server.
#  It expects only one parameter: the desired http [reponse] code.
#  The header is written to a temporary file, making use of the fact the poll and select don't solely work with sockets but with general file descriptors.
#  Everything that is written to the socket is lost.
#  Not all functions that are normally found on a socket are implemented, only those that are used by asyncore.
#  The socket identifies itself through [getpeername] as 'LocalResponse' and the served response code.

class LocalResponse:

	reason = {
		304: 'Not Modified',
		503: 'Service Unavailable' }

	def __init__ (self, response):

		self.file = os.tmpfile() # needed for the file descriptor
		self.write('HTTP/1.1 %i %s\r\n' % (response, self.reason[response]))
		self.write('date: %s\r\n' % time.strftime(TIMEFMT, time.gmtime()))
		self.write('\r\n')
		self.seek(0) # move to beginning of file
		self.response = response # save response code for getpeername

	def __getattr__ (self, attr):

		return getattr(self.file, attr) # fall back on file object for missing attributes

	def setblocking (self, flags):

		pass

	def getpeername (self):

		return 'LocalResponse', self.response

	def recv (self, size):

		return self.read(size)

	def send (self, str):

		return len(str) # pretend everyting is sent

#  function main
#
#  The [main] function handles the command line arguments, creates a [Listener] instance to monitor the proxy port and starts the [asyncore.loop].
#  The command line handling is left over to the optparse <http://www.python.org/doc/current/lib/module-optparse.html> module.
#  For the possible command line options see the description <index.html> page.
#  If all goes well the [asyncore.loop] runs until it is manually interrupted by the user.

def main ():

	parser = optparse.OptionParser()
	parser.add_option('-p', '--port', type='int', default=8080, help='listen on PORT for incoming connections')
	parser.add_option('-i', '--ip', action='append', default=['127.0.0.1'], help='allow connections from certain IP addresses')
	parser.add_option('-s', '--static', action='store_true', help='never check for modifications')
	parser.add_option('-f', '--flat', action='store_true', help='save files in a single directory')
	parser.add_option('-d', '--debug', action='store_true', help='crash on exceptions')
	options, args = parser.parse_args() # parse command line
	try:
		Listener(HttpClient, options.port, options.ip) # setup Listener for specified port
	except socket.error:
		parser.error('port %i is not available' % options.port)
	except re.error:
		parser.error('invalid ip address format')
	Http.static = options.static
	Http.flat = options.flat
	Http.debug = options.debug
	try:
		print 'HttpReplicator', 'Started'
		asyncore.loop() # main asyncore loop
	except KeyboardInterrupt: # manually interrupted
		print 'HttpReplicator', 'Terminated'

if __name__ == '__main__':

	main()
