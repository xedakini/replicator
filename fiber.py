import sys, os, select, time, socket, traceback


class InfType:

  def __gt__( self, other ):

    return True

  def __lt__( self, other ):

    return False

  def __radd__( self, other ):

    return self


Inf = InfType()


class SEND:

  def __init__( self, sock ):

    assert hasattr( sock, 'fileno' ), 'invalid SEND argument %r' % sock
    self.sock = sock


class RECV:

  def __init__( self, sock ):

    assert hasattr( sock, 'fileno' ), 'invalid RECV argument %r' % sock
    self.sock = sock


class WAIT:

  def __init__( self, timeout = Inf ):

    assert timeout.__class__ in ( int, float, InfType ), 'invalid WAIT argument %r' % timeout
    self.timeout = timeout


class Fiber:

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
      state = self.__generator.next()
    finally:
      sys.stdout = stdout

    if state.__class__ == WAIT:
      self.expire = time.time() + state.timeout
      waitqueue.append( self )
    elif state.__class__ == SEND:
      self.expire = time.time() + self.__timeout
      self.fileno = state.sock.fileno
      sendqueue.append( self )
    elif state.__class__ == RECV:
      self.expire = time.time() + self.__timeout
      self.fileno = state.sock.fileno
      recvqueue.append( self )
    else:
      raise AssertionError, 'invalid command %r' % cmd

  def __del__( self ):

    try:
      stdout = sys.stdout
      sys.stdout = self
      del self.__generator # call destructors for output
    finally:
      sys.stdout = stdout


class GatherFiber( Fiber ):

  def __init__( self, generator, timeout ):

    Fiber.__init__( self, generator, timeout )

    self.__lines = []
    self.__buffer = ''

  def write( self, string ):

    self.__buffer += string
    if self.softspace:
      self.__lines.append( time.strftime( '%H:%M:%S ' ) + self.__buffer )
      self.__buffer = ''

  def step( self, *args ):

    try:
      Fiber.step( self, *args )
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
      Fiber.__del__( self )
    except:
      print >> self, ''.join( traceback.format_exception( sys.exc_type, sys.exc_value, sys.exc_traceback ) ).rstrip()

    for line in self.__lines:
      Fiber.write( line )
    Fiber.write( '\n' )


class DebugFiber( Fiber ):

  def __init__( self, generator, timeout ):

    Fiber.__init__( self, generator, timeout )

    self.__id = '%s : ' % id( generator )
    self.__frame = generator.gi_frame
    self.__newline = True

    print >> self, 'New fiber'

  def write( self, string ):

    if self.__newline:
      Fiber.write( self.__id )

    Fiber.write( string )
    self.__newline = self.softspace

  def step( self, *args ):

    try:
      enter = self.__frame.f_lineno
      Fiber.step( self, *args )
      leave = self.__frame.f_lineno
    except StopIteration:
      print >> self, 'Done'
    else:
      print >> self, '%i -> %i' % ( enter, leave )

  def __repr__( self ):

    return 'fiber %s waiting at :%i' % ( self.__id, self.__frame.f_lineno )


def spawn( generator, port, timeout, debug ):

  listener = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
  listener.setblocking( 0 )
  listener.setsockopt( socket.SOL_SOCKET, socket.SO_REUSEADDR, listener.getsockopt( socket.SOL_SOCKET, socket.SO_REUSEADDR ) | 1 )
  listener.bind( ( '', port ) )
  listener.listen( 5 )

  if debug:
    myFiber = DebugFiber
  else:
    myFiber = GatherFiber

  print time.strftime( '%D' ), 'HTTP Replicator started'

  try:

    waitqueue = []
    recvqueue = [ listener ]
    sendqueue = []

    while True:

      expire = Inf

      for i in range( len( waitqueue ) -1, -1, -1 ):
        if waitqueue[ i ].expire is Inf or waitqueue[ i ].expire < time.time():
          waitqueue[ i ].step( waitqueue, recvqueue, sendqueue )
          del waitqueue[ i ]
        else:
          expire = min( expire, waitqueue[ i ].expire )

      while len( recvqueue ) > 1:
        if recvqueue[ 1 ].expire < time.time():
          print >> recvqueue[ 1 ], 'Timed out'
          del recvqueue[ 1 ]
        else:
          expire = min( expire, recvqueue[ 1 ].expire )
          break

      while len( sendqueue ) > 0:
        if sendqueue[ 0 ].expire < time.time():
          print >> sendqueue[ 0 ], 'Timed out'
          del sendqueue[ 0 ]
        else:
          expire = min( expire, sendqueue[ 0 ].expire )
          break

      if expire is Inf:
        print time.strftime( '%D' ), 'Idle'
        sys.stdout.flush()
        canrecv, cansend, dummy = select.select( recvqueue, sendqueue, [] )
        print time.strftime( '%D' ), 'Busy'
        sys.stdout.flush()
        print
      else:
        canrecv, cansend, dummy = select.select( recvqueue, sendqueue, [], expire - time.time() )

      for fiber in canrecv:
        if fiber is listener:
          waitqueue.append( myFiber( generator( *listener.accept() ), timeout ) )
        else:
          recvqueue.remove( fiber )
          fiber.step( waitqueue, recvqueue, sendqueue )
          del fiber

      for fiber in cansend:
        sendqueue.remove( fiber )
        fiber.step( waitqueue, recvqueue, sendqueue )
        del fiber

      del canrecv, cansend, dummy

  except KeyboardInterrupt:
    print time.strftime( '%D' ), 'HTTP Replicator terminated'
  except:
    print time.strftime( '%D' ), 'HTTP Replicator crashed'
    raise
