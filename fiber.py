import sys, os, select, time, socket, traceback


class SEND:

  def __init__( self, sock ):

    assert hasattr( sock, 'fileno' ), 'invalid SEND argument %r' % sock
    self.sock = sock


class RECV:

  def __init__( self, sock ):

    assert hasattr( sock, 'fileno' ), 'invalid RECV argument %r' % sock
    self.sock = sock


class WAIT:

  def __init__( self, timeout = None ):

    assert timeout is None or timeout.__class__ in ( int, float, NoneType ), 'invalid WAIT argument %r' % timeout
    self.timeout = timeout


class Fiber:

  write = sys.stdout.write
  writelines = sys.stdout.writelines
  softspace = 0

  def __init__( self, generator, timeout ):

    self.__generator = generator
    self.__timeout = timeout

    self.state = WAIT
    self.expire = None
    self.fileno = None

  def step( self ):

    try:
      stdout = sys.stdout
      sys.stdout = self
      state = self.__generator.next()
      self.state = state.__class__
      assert self.state in ( SEND, RECV, WAIT ), 'invalid command %r' % cmd
    finally:
      sys.stdout = stdout

    if self.state is WAIT:
      if state.timeout is None:
        self.expire = None
      else:
        self.expire = time.time() + state.timeout
      self.fileno = None
    else:
      self.expire = time.time() + self.__timeout
      self.fileno = state.sock.fileno()

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
      self.state = None
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

  def __init__( self, generator, timeout ):

    Fiber.__init__( self, generator, timeout )

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
      self.state = None
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

    fibers = []

    while True:

      tryrecv = { listener.fileno(): None }
      trysend = {}
      expire = None

      for i in range( len( fibers ) -1, -1, -1 ):

        if fibers[ i ].state is None:
          del fibers[ i ]
          continue

        if fibers[ i ].expire < time.time():
          if fibers[ i ].state is WAIT:
            fibers[ i ].step()
          else:
            print >> fibers[ i ], 'Timed out'
            del fibers[ i ]
            continue

        if fibers[ i ].state is RECV:
          tryrecv[ fibers[ i ].fileno ] = fibers[ i ]
        elif fibers[ i ].state is SEND:
          trysend[ fibers[ i ].fileno ] = fibers[ i ]
        
        if not expire:
          expire = fibers[ i ].expire
        elif fibers[ i ].expire:
          expire = min( expire, fibers[ i ].expire )

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
          fibers.append( myFiber( generator( *listener.accept() ), timeout ) )
        else:
          tryrecv[ fileno ].step()
      for fileno in cansend:
        trysend[ fileno ].step()

  except KeyboardInterrupt:
    print time.strftime( '%D' ), 'HTTP Replicator terminated'
  except:
    print time.strftime( '%D' ), 'HTTP Replicator crashed'
    raise
