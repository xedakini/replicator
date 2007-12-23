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

  def __del__( self ):

    try:
      stdout = sys.stdout
      sys.stdout = self
      del self.__generator
    finally:
      sys.stdout = stdout


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
    except AssertionError, msg:
      print >> self, 'Error:', msg
    except:
      print >> self, ''.join( traceback.format_exception( sys.exc_type, sys.exc_value, sys.exc_traceback ) ).rstrip()

  def __del__( self ):

    try:
      Fiber.__del__( self )
    except:
      print >> self, ''.join( traceback.format_exception( sys.exc_type, sys.exc_value, sys.exc_traceback ) ).rstrip()

    Fiber.writelines( self.__lines )


class DebugFiber( Fiber ):

  def __init__( self, generator ):

    Fiber.__init__( self, generator )

    self.__id = ' %s  ' % id( generator )
    self.__frame = generator.gi_frame
    self.__newline = True

    print >> self, 'New fiber'

  def write( self, string ):

    if self.__newline:
      Fiber.write( self.__id )

    Fiber.write( string )
    self.__newline = self.softspace

  def step( self ):

    try:
      enter = self.__frame.f_lineno
      Fiber.step( self )
      leave = self.__frame.f_lineno
    except StopIteration:
      print >> self, 'Done'
    else:
      print >> self, '%i -> %i' % ( enter, leave )

  def __repr__( self ):

    return 'fiber %s waiting at :%i' % ( self.__id, self.__frame.f_lineno )


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
          if isinstance( state, WAIT ):
            fibers[ i ].step()
            state = fibers[ i ].state
          else:
            print >> fibers[ i ], 'Timed out'
            state = None

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
          client, address = listener.accept()
          fibers.append( myFiber( generator( client, address ) ) )
        else:
          tryrecv[ fileno ].step()
      for fileno in cansend:
        trysend[ fileno ].step()

  except KeyboardInterrupt:
    print time.strftime( '%D' ), 'HTTP Replicator terminated'
  except:
    print time.strftime( '%D' ), 'HTTP Replicator crashed'
    raise
