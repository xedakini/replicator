import sys, os, select, time, socket, traceback


class Thread:

  expire = None
  fileno = None
  write = sys.stdout.write
  softspace = 0

  def __init__( self, generator, timeout ):

    self.__generator = generator
    self.__timeout = timeout

  def step( self, waitqueue, recvqueue, sendqueue ):

    try:
      stdout = sys.stdout
      sys.stdout = self
      cmd, arg = self.__generator.next()
    finally:
      sys.stdout = stdout

    if cmd == 'WAIT':
      if arg is None:
        self.expire = None
      else:
        assert isinstance( arg, ( int, float ) ), 'invalid argument %r' % arg
        self.expire = time.time() + arg
      waitqueue.append( self )
    else:
      assert hasattr( arg, 'fileno' ), 'invalid argument %r' % arg
      self.expire = time.time() + self.__timeout
      self.fileno = arg.fileno
      if cmd == 'RECV':
        recvqueue.append( self )
      elif cmd == 'SEND':
        sendqueue.append( self )
      else:
        raise AssertionError, 'invalid command %r' % cmd

  def __del__( self ):

    try:
      stdout = sys.stdout
      sys.stdout = self
      del self.__generator # call destructors for output
    finally:
      sys.stdout = stdout


class GatherThread( Thread ):

  def __init__( self, generator, timeout ):

    Thread.__init__( self, generator, timeout )

    self.__lines = [ time.strftime( '%D\n' ) ]
    self.__buffer = ''

  def write( self, string ):

    self.__buffer += string
    if self.softspace:
      self.__lines.append( time.strftime( '%H:%M:%S ' ) + self.__buffer )
      self.__buffer = ''

  def step( self, *args ):

    try:
      Thread.step( self, *args )
    except KeyboardInterrupt:
      raise
    except StopIteration:
      pass
    except AssertionError, msg:
      print >> self, 'Error:', msg
    except:
      print >> self, ''.join( traceback.format_exception( sys.exc_type, sys.exc_value, sys.exc_traceback ) ).rstrip()

  def __del__( self ):

    try:
      Thread.__del__( self )
    except:
      print >> self, ''.join( traceback.format_exception( sys.exc_type, sys.exc_value, sys.exc_traceback ) ).rstrip()

    for line in self.__lines:
      Thread.write( line )


class DebugThread( Thread ):

  def __init__( self, generator, timeout ):

    Thread.__init__( self, generator, timeout )

    self.__id = ' %s  ' % id( generator )
    self.__frame = generator.gi_frame
    self.__newline = True

    print >> self, 'New thread'

  def write( self, string ):

    if self.__newline:
      Thread.write( self.__id )

    Thread.write( string )
    self.__newline = self.softspace

  def step( self, *args ):

    print >> self, '> :%i' % self.__frame.f_lineno

    try:
      Thread.step( self, *args )
    except StopIteration:
      print >> self, 'Done'
    else:
      print >> self, '< :%i' % self.__frame.f_lineno

  def __repr__( self ):

    return 'thread %s waiting at :%i' % ( self.__id, self.__frame.f_lineno )


def spawn( generator, port, timeout, debug ):

  listener = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
  listener.setblocking( 0 )
  listener.setsockopt( socket.SOL_SOCKET, socket.SO_REUSEADDR, listener.getsockopt( socket.SOL_SOCKET, socket.SO_REUSEADDR ) | 1 )
  listener.bind( ( '', port ) )
  listener.listen( 5 )

  if debug:
    myThread = DebugThread
  else:
    myThread = GatherThread

  print time.strftime( '%D' ), 'HTTP Replicator started'

  try:

    waitqueue = []
    recvqueue = [ listener ]
    sendqueue = []

    while True:

      firsttimeout = None

      for i in range( len( waitqueue ) -1, -1, -1 ):
        thistimeout = waitqueue[ i ].expire and waitqueue[ i ].expire - time.time()
        if thistimeout < 0:
          waitqueue[ i ].step( waitqueue, recvqueue, sendqueue )
          del waitqueue[ i ]
        else:
          firsttimeout = min( firsttimeout or 1e99, thistimeout )

      while len( recvqueue ) > 1:
        thistimeout = recvqueue[ 1 ].expire - time.time()
        if thistimeout < 0:
          print >> recvqueue[ 1 ], 'Timed out'
          del recvqueue[ 1 ]
        else:
          firsttimeout = min( firsttimeout or 1e99, thistimeout )
          break

      while len( sendqueue ) > 0:
        thistimeout = sendqueue[ 0 ].expire - time.time()
        if thistimeout < 0:
          print >> sendqueue[ 0 ], 'Timed out'
          del sendqueue[ 0 ]
        else:
          firsttimeout = min( firsttimeout or 1e99, thistimeout )
          break

      if not firsttimeout:
        print time.strftime( '%D' ), 'Idle'

      canrecv, cansend, dummy = select.select( recvqueue, sendqueue, [], firsttimeout )

      for thread in canrecv:
        if thread is recvqueue[ 0 ]:
          waitqueue.append( myThread( generator( *listener.accept() ), timeout ) )
        else:
          recvqueue.remove( thread )
          thread.step( waitqueue, recvqueue, sendqueue )

      for thread in cansend:
        sendqueue.remove( thread )
        thread.step( waitqueue, recvqueue, sendqueue )

      del canrecv, cansend, dummy, thread

  except KeyboardInterrupt:
    print
    print time.strftime( '%D' ), 'HTTP Replicator terminated'
  except:
    print time.strftime( '%D' ), 'HTTP Replicator crashed'
    raise
