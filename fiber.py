import sys, os, select, time, socket, traceback


class SEND:

  def __init__( self, sock, timeout ):

    self.fileno = sock.fileno()
    self.expire = timeout > 0 and time.time() + timeout


class RECV:

  def __init__( self, sock, timeout ):

    self.fileno = sock.fileno()
    self.expire = timeout > 0 and time.time() + timeout


class WAIT:

  def __init__( self, timeout = -1 ):

    self.fileno = None
    self.expire = timeout > 0 and time.time() + timeout


class Fiber:

  write = sys.stdout.write
  writelines = sys.stdout.writelines
  softspace = 0

  def __init__( self, generator ):

    self.__generator = generator
    self.state = WAIT()

  def step( self ):

    self.state = None
    try:
      stdout = sys.stdout
      sys.stdout = self
      state = self.__generator.next()
      assert isinstance( state, (SEND, RECV, WAIT) ), 'invalid waiting state %r' % state
      self.state = state
    finally:
      sys.stdout = stdout

  def throw( self, msg ):

    try:
      stdout = sys.stdout
      sys.stdout = self
      self.__generator.throw( Exception, msg )
    finally:
      sys.stdout = stdout

  def __repr__( self ):

    return '%s:%i' % ( self.state.__class__.__name__, self.__generator.gi_frame.f_lineno )


class GatherFiber( Fiber ):

  def __init__( self, generator ):

    Fiber.__init__( self, generator )
    self.__lines = [ time.ctime() + '\n' ]
    self.__buffer = ''
    self.__start = time.time()

  def write( self, string ):

    self.__buffer += string
    if self.softspace:
      self.__lines.append( '%6.2f  %s' % ( time.time() - self.__start, self.__buffer ) )
      self.__buffer = ''

  def step( self ):

    try:
      Fiber.step( self )
    except KeyboardInterrupt:
      raise
    except StopIteration:
      pass
    except ( AssertionError, socket.error ), msg:
      print >> self, 'Error:', msg
    except:
      print >> self, ''.join( traceback.format_exception( sys.exc_type, sys.exc_value, sys.exc_traceback ) ).rstrip()

  def __del__( self ):

    Fiber.writelines( self.__lines )


class DebugFiber( Fiber ):

  id = 0

  def __init__( self, generator ):

    Fiber.__init__( self, generator )

    self.__id = '[ 0x%02X ] ' % ( DebugFiber.id % 256 )
    self.__newline = True

    DebugFiber.id += 1

    print >> self, 'New fiber'

  def write( self, string ):

    if self.__newline:
      Fiber.write( self.__id )

    Fiber.write( string )
    self.__newline = self.softspace

  def step( self ):

    try:
      Fiber.step( self )
    except StopIteration:
      print >> self, 'End of fiber.'
    except ( AssertionError, socket.error ), msg:
      print >> self, 'Error:', msg
    else:
      print >> self, 'Waiting at', self


def spawn( generator, port, debug ):

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

    fibers = []

    while True:

      tryrecv = { listener.fileno(): None }
      trysend = {}
      expire = None

      for i in range( len( fibers ) -1, -1, -1 ):
        state = fibers[ i ].state

        if state and time.time() > state.expire:
          if not isinstance( state, WAIT ):
            fibers[ i ].throw( 'Connection timed out' )
          fibers[ i ].step()
          state = fibers[ i ].state

        if not state:
          del fibers[ i ]
          continue

        if isinstance( state, RECV ):
          tryrecv[ state.fileno ] = fibers[ i ]
        elif isinstance( state, SEND ):
          trysend[ state.fileno ] = fibers[ i ]
        
        if not expire or state.expire and state.expire < expire:
          expire = state.expire

      if expire is None:
        print '[ IDLE ]'
        sys.stdout.flush()
        canrecv, cansend, dummy = select.select( tryrecv, trysend, [] )
        print '[ BUSY ]'
        sys.stdout.flush()
      else:
        canrecv, cansend, dummy = select.select( tryrecv, trysend, [], expire - time.time() )

      for fileno in canrecv:
        if fileno is listener.fileno():
          fibers.append( myFiber( generator( *listener.accept() ) ) )
        else:
          tryrecv[ fileno ].step()
      for fileno in cansend:
        trysend[ fileno ].step()

  except KeyboardInterrupt:
    print time.strftime( '%D' ), 'HTTP Replicator terminated'
  except:
    print time.strftime( '%D' ), 'HTTP Replicator crashed'
    raise
