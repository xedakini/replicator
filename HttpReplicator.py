#! /usr/bin/python
#
#  This module contains the main code of the replicator proxy server.
#  The server can be used in two ways: either run by hand as an executable or as a daemon, controlled by an <a href=init.html>init script</a>.
#  In the first case the program requires only one parameter, namely the port on which the proxy server will act.
#  User information is sent to the standard output and files are cached in the current directory.
#  In the second case proxy settings are read from a <a href=http-replicator.conf.html>configuration file</a> and user information is written to a log file.
#  This info can also be viewed (remotely) via telnet in real time.

import asyncore, socket, os, time, sys, re

CHUNK = 1024 # read and write CHUNK bytes at a time

#  class Listener
#
#  Class [Listener] is a subclass of [asyncore.dispatcher].
#  Its purpose is to monitor incoming requests at [port] and create an instance of [object] for each one.
#  Class [object] should be a subclass of [asyncore.dispatcher] and should accept the caller socket as parameter, just like an unmodified [asyncore.dispatcher] instance.
#  It suffices to create the instance: as it is a subclass of [asyncore.dispatcher] it will add itself to the [asyncore.socket_map] so it won't get garbage-collected.
#  The [asyncore.loop] takes care of the rest.
#
#  Class [object] is stored implicitly in memberfunction [handle_accept].
#  This function is called whenever the [asyncore.loop] notices an incoming request at [port].
#  Alternatively, [object] could have been stored for use by a fixed [handle_accept] function; this is shorter.

class Listener (asyncore.dispatcher):

	def __init__ (self, object, port):

		asyncore.dispatcher.__init__(self)

		self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
		self.set_reuse_addr()
		self.bind(('', port)) # listen on localhost:port
		self.listen(5) # handle max 5 simultaneous connections
		self.handle_accept = lambda: object(self.accept()[0]) # self.accept returns (socket, address)

#  class Telnet
#
#  Class [Telnet] too is a subclass of [asyncore.dispatcher].
#  Contrary to [Listener] this class does not handle incoming requests itself but gets created by [Listener] whenever a request is made at its port.
#  The [__init__] function as not modified so the caller socket parameter is handled automatically.
#
#  This class is not used when the replicator is run by hand.
#  It is here for when replicator is run as a daemon and [sys.stdout] is redirected to a file object or similar.
#  Note: this is mandatory as [sys.stdout] must seekable.
#  When a [Listener] instance of this class is created, it is possible to view the replicator output through a telnet connection.
#
#  Operation is as follows.
#  When the [asyncore.loop] signals incoming data (someone's typing in the telnet session), [handle_read] reads and looses it.
#  In the other direction [writable] compares the pointer position of [sys.stdout] with its own [pointer].
#  In case of a non match, [asyncore.loop] calls [handle_write] to send the unsent in chunks of size [CHUNK] and update the pointer.

class Telnet (asyncore.dispatcher):

	pointer = 0

	def writable (self):

		return sys.stdout.tell() > self.pointer # compare pointers

	def handle_write (self):

		sys.stdout.seek(self.pointer) # sys.stdout must be seekable!
		self.pointer += self.send(sys.stdout.read(CHUNK)) # self.send returns number of bytes sent
		sys.stdout.seek(0,2) # move to end of file so future print calls will be appended

	def handle_read (self):

		self.recv(CHUNK) # read max CHUNK bytes at a time

	def handle_close (self):

		self.close()

#  class Http
#
#  Class [Http] is yet another subclass of [asyncore.dispatcher].
#  It is meant for use with [Listener] and therefore accepts the caller socket parameter, just like the [Telnet] class.
#  The [Http] class is not meant for standalone use but should be subclassed to provide an additional handling function [handle_header].
#  The [HttpClient] and [HttpServer] classes do this, and together handle communication between the calling http client and the called http server.
#  Each instance refers to its counterpart via the [other] variable.
#
#  This class handles everything that the http request from the client and the response from the server have in common:
#  * In both cases the first line consists of three fields.
#  * This is followed by a series of key: value lines.
#  * All lines are terminated by CRLF, the last line of the header by a double CRLF.
#  * This is followed by the message body (which is empty on the client side as posting is not supported).
#  This class puts the top header line in a three element list and the rest of the header in a dictionary and calls [handle_header].
#  This function prepares the second part of the transmission and handles the main (only) purpose of this proxy: caching.
#
#  Sending of data is roughly the same as for the [Telnet] class: [writable] compares [pointer] with the data available and [handle_write] sends the unsent bytes.
#  Only this time this data is divided in a [header] and [data], which reflects the structure of an http transmission.
#  Reading is a bit more complex as the incoming data is parsed.
#  The [handle_read] function reads data in blocks of [CHUNK] bytes max and stores it in the [header] string as long as the http header is not complete.
#  Once the header is received completely it is parsed in a list [head] and dictionary [body] and [handle_header] is called.
#  Here [body] and [head] (mutable) can be altered.
#  Upon return [head] and [body] are changed back into the [header] string.
#  Data doesn't get sent until after this function call.
#
#  In [handle_close] the instance's reference to its counterpart [other] is explicitly deleted.
#  This is necessairy because cyclic references make the garbage collector fail, which means all(!) downloaded data would otherwise remain in memory.
#  <a href=http://www.nightmare.com/medusa/memory-leaks.html>This</a> is what happens when [other] is not explicitly deleted.

class Http (asyncore.dispatcher):

	pointer = 0
	header = ''
	data = None

	other = None # counterpart Http instance
	id = 0 # instances are numbered

	timefmt = '%a, %d %b %Y %H:%M:%S GMT' # http date format

	def __str__ (self):

		return '%s %i' % (self.__class__.__name__, self.id) # string representation for info on stdout

	def writable (self):

		if not self.other or not self.other.data:
			return False # no data to write

		self.other.data.seek(0,2) # move to end of file
		if len(self.other.header) + self.other.data.tell() > self.pointer: # compare pointers
			return True # there is data to send

		if not self.other.connected and self.__class__ is HttpClient: # always finish download (server side)
			self.handle_close() # counterpart is closed so there will not be anymore data

		return False # nothing to send

	def handle_write (self):

		if self.pointer < len(self.other.header):
			self.pointer += self.send(self.other.header[self.pointer:]) # send header
		else:
			self.other.data.seek(self.pointer - len(self.other.header)) # move to pointer position
			self.pointer += self.send(self.other.data.read(CHUNK)) # send data

	def handle_read (self):

		if self.data:
			self.data.seek(0,2)
			self.data.write(self.recv(CHUNK)) # append to data
		else:
			self.header += self.recv(CHUNK) # append to header
			if '\r\n\r\n' in self.header: # complete header is received
				lines, data = self.header.split('\r\n\r\n', 1) # split header from already received data
				lines = lines.split('\r\n') # split header lines
				head = lines[0].split(' ', 2) # split top header line in a three element list
				body = {}
				for line in lines[1:]:
					key, value = line.split(': ', 1)
					body[key.lower()] = value # build dictionary
				if self.other: # counterpart present
					self.id = self.other.id # use same id
				else:
					self.id = Http.id = Http.id + 1 # use next available id
				self.handle_header(head, body, data) # call subclass function: handle_header
				lines = [' '.join(head)] + map(': '.join, body.items())
				print self, 'Received:', '\n  '.join(['',''] + lines + [''])
				self.header = '\r\n'.join(lines + ['','']) # rebuild header

	def handle_close (self):

		self.close() # close connection
		self.connected = 0
		print self, 'Closed'
		del self.other

#  class HttpClient
#
#  Class [HttpClient] is one of the two subclasses of [Http].
#  Instances are created by [Listener] for each http request that is made through the proxy server.
#  Once the http header is received [handle_header] is called.
#  Here the header is altered and the connection to the requested http server is made.
#
#  The main change made to the http header is the switch to HTTP/1.0.
#  There are two reasons for this.
#  The first is that the http transmission must be closed when the body is sent in order to keep things simple.
#  This is normal procedure for HTTP/1.0, but HTTP/1.1 offeres the possibility to keep the connection open for a next transfer.
#  The old behaviour can however still be forced with a 'connection: close' headerline.
#  The other reason is the possibility of chunked transfer.
#  HTTP/1.1 can transfer files in parts, all started by a header.
#  This would require some post processing before storing the file, which means the data can't be written to the file directly.
#  All in all no real reasons, it's just a choice.
#
#  Another important header change involves the replicators main purpose: caching.
#  Whenever the client sends a GET request the replicator cache is checked for presence of the requested file.
#  If the file is present the cache date is sent in an 'if-modified-since: date' header line to check its up-to-dateness.
#  The server ([HttpServer] side) will respond with a normal 200 OK if it is modified or a 304 Not Modified if it's not.
#  Before a new connection is created the [asyncore.socket_map] is searched for existing [HttpServer] instances: the requested file could already be in download (quite usual when doing simultaneous debian upgrades).

class HttpClient (Http):

	spliturl = re.compile(r'http://([^/:]+)(?:[:]([^/]+))?/+(.*)').match # split url in http://(host):(port)/(path)
	null = open('/dev/null','r+') # garbage file

	def handle_header (self, head, body, data):

		print self, 'Connected by %s:%i' % self.addr

		head[2] = 'HTTP/1.0' # switch to HTTP/1.0
	
		body.pop('keep-alive', None) # close connection after transfer
		body.pop('proxy-connection', None) # idem
		body.pop('connection', None) # idem
		body.pop('range', None) # always fetch entire file

		host, port, path = self.spliturl(head[1]).groups() # parse url
		subdir, file = os.path.split(path)
		directory = os.path.normpath(os.path.join(host, subdir))
		target = os.path.join(directory, file or 'index.html') # target cache location

		dict = {'other':self} # dict contains all information that will be transferred to the HttpServer counterpart

		if head[0] == 'GET': # request for download

			dict['target'] = target
			if os.path.isfile(target): # file in cache
				for object in asyncore.socket_map.values(): # search for identical transfers
					if object.__class__ is HttpServer and object.target == target:
						print self, 'Joined', object
						self.other = object # make this the counterpart
						break
				else: # no identical transfer
					oldtime = time.localtime(os.path.getmtime(target)) # cache date
					if not 'if-modified-since' in body or oldtime > time.strptime(body['if-modified-since'], self.timefmt):
						dict['oldtime'] = oldtime
						body['if-modified-since'] = time.strftime(self.timefmt, oldtime)
			elif not os.path.isdir(directory):
				os.makedirs(directory) # create subdirectories

		if not self.other: # no running transfer found

			try:
				sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
				sock.connect((host, port and int(port) or 80)) # connect to server
			except: # connection failed
				sock = None
				dict['header'] = 'HTTP/1.0 503 Service Unavailable\r\n\r\n' # return error
				dict['data'] = self.null

			self.other = HttpServer(sock)
			self.other.__dict__.update(dict) # supply HttpServer with collected information

		self.data = self.null # there shouldn't follow anymore data

#  class HttpServer
#
#  Class [HttpServer] is the other subclass of [Http], the counterpart of [HttpClient].
#  Instances of [HttpServer] are created by [HttpClient].
#  The main purpose of this class is to interpret the http server's response to the client's request and act accordingly.
#
#  The top line of a http response header is different from a http request but still consists of three fields; the middle one is a status integer.
#  A value of 200 denotes a successful download.
#  If [target] is set then this is the response to a GET request and the cache file is opened for writing in [data].
#  The current date and target size, both received from the server, are saved for after the file is downloaded.
#
#  A return value of 304 is a response to an if-modified-since headerline and signifies that the file in cache is up to date.
#  If [oldtime] is set the http request was altered by the [HttpClient] instance, which means the file is in the replicator cache.
#  The http response header is transformed into a 200 OK response and the cache file is opened for reading in [data].
#  If [oldtime] is not set the response is sent unaltered; in that case the headerline was provided by the client to check a private cache.
#
#  The [HttpServer] instance is automatically deleted by the garbage collector when all clients have closed their connection.
#  In [__del__] the size of the cached file is checked against the anounced [size] that was saved by [handle_header].
#  The file's date is set to [date], so the proxy will not have to rely on the system clock.

class HttpServer (Http):

	target = ''

	oldtime = None
	newtime = None

	def handle_header (self, head, body, data):

		print self, 'Connected to %s:%i' % self.addr

		if head[1] == '200' and self.target: # successful GET request

			print self, self.oldtime and 'Too old (%s):' % time.asctime(self.oldtime) or 'Not in cache:', self.target

			self.newtime = 'last-modified' in body and time.strptime(body['last-modified'], self.timefmt)
			self.size = body.get('content-length')
			self.data = self.newtime and open(self.target, 'w+') or os.tmpfile() # data is written to cache
			self.data.write(data) # already received data

		elif head[1] == '304' and self.oldtime: # file in cache is up to date

			print self, 'In cache (%s):' % time.asctime(self.oldtime), self.target

			head[1:3] = ['200', 'OK'] # transform into 200 OK response
			body['content-length'] = str(os.path.getsize(self.target))
			self.data = open(self.target, 'r') # data is read from cache

		else:

			self.data = os.tmpfile() # temporary file
			self.data.write(data)

	def __del__ (self):

		if self.newtime:

			self.data.close()

			if self.size and int(self.size) != os.path.getsize(self.target): # wrong filesize
				print self, 'Incorrect filesize: %i bytes, expected %s\a' % (os.path.getsize(self.target), self.size)
				os.remove(self.target) # delete from cache
			else:
				print self, 'Successfully cached (%s):' % time.asctime(self.newtime), self.target
				os.utime(self.target, (time.mktime(self.newtime),)*2) # set creation time

#  function main
#
#  When the replicator is run by hand a [Listener] instance monitors the port specified on the command line.
#  The [asyncore.loop] runs until it is manually killed (or crashes...).
#  It is important that [asyncore.loop] is called to use poll instead of select because it otherwise crashes when an instance suddenly disappears.
#  This happens when an end-of-transfer is detected in an [HttpClient]'s [writable] call and the instance is consequently deleted.
#  A consequence of this is that replicator in this form will probably not run on MacOS X.

def main ():

	try:
		Listener(HttpClient, int(sys.argv[1])) # create HttpClient instances for requests at specified port
		asyncore.loop(use_poll=1) # main loop
	except IndexError: # no arguments given
		print 'usage: %s [port]' % sys.argv[0]
	except ValueError, error: # no integer argument given
		print 'error:', error
	except socket.error, error: # port not available
		print 'error:', error[1].lower()
	except KeyboardInterrupt: # program killed
		print 'terminated'
		return 0 # succes

	return 1 # error

if __name__ == '__main__':

	sys.exit(main())
