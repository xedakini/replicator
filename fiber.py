import sys, os, select, time, socket, traceback


class SEND:

  def __init__( self, sock, timeout ):

    self.fileno = sock.fileno()
    self.expire = time.time() + timeout


class RECV:

  def __init__( self, sock, timeout ):

    self.fileno = sock.fileno()
    self.expire = time.time() + timeout


class WAIT:

  def __init__( self, timeout = None ):

    self.expire = timeout and time.time() + timeout or None


class Fiber:

  write = sys.stdout.write
  writelines = sys.stdout.writelines

  def __init__( self, generator ):

    self.__generator = generator
    self.state = WAIT()

  def __newstate( self ):

    sys.stdout = self
    state = self.__generator.next()
    assert isinstance( state, (SEND, RECV, WAIT) ), 'invalid waiting state %r' % state
    return state

  def step( self ):

    self.state = None
    try:
      stdout = sys.stdout
      self.state = self.__newstate()
    finally:
      sys.stdout = stdout

  def throw( self, msg ):

    self.state = None
    if hasattr( self.__generator, 'throw' ):
      try:
        stdout = sys.stdout
        self.__generator.throw( AssertionError, msg )
        self.state = self.__newstate()
      finally:
        sys.stdout = stdout
    else:
      print >> self, 'Terminating fiber:', msg

  def __repr__( self ):

    return '%s:%i' % ( self.state.__class__.__name__, self.__generator.gi_frame.f_lineno )


class GatherFiber( Fiber ):

  def __init__( self, generator ):

    Fiber.__init__( self, generator )
    self.__chunks = [ time.ctime() + '\n' ]
    self.__newline = True
    self.__start = time.time()

  def write( self, string ):

    if self.__newline:
      self.__chunks.append( '%6.2f  ' % ( time.time() - self.__start ) )
    self.__chunks.append( string )
    self.__newline = string.endswith( '\n' )

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
      traceback.print_exc( file=self )

  def __del__( self ):

    Fiber.writelines( self.__chunks )
    if not self.__newline:
      Fiber.write( '\n' )


class DebugFiber( Fiber ):

  id = 0

  def __init__( self, generator ):

    Fiber.__init__( self, generator )
    self.__id = '[ %04X ] ' % ( DebugFiber.id % 65535 )
    self.__newline = True
    DebugFiber.id += 1

    print >> self, 'New fiber'

  def write( self, string ):

    if self.__newline:
      Fiber.write( self.__id )
    Fiber.write( string )
    self.__newline = string.endswith( '\n' )

  def step( self ):

    try:
      Fiber.step( self )
    except StopIteration:
      print >> self, 'End of fiber.'
    except:
      traceback.print_exc( file=self )
    else:
      print >> self, 'Waiting at', self


def fork( output ):

  try:
    log = open( output, 'w' )
    nul = open( '/dev/null', 'r' )
    pid = os.fork()
  except IOError, e:
    print 'error: failed to open', e.filename
    sys.exit( 1 )
  except OSError, e:
    print 'error: failed to fork process:', e.strerror
    sys.exit( 1 )
  except Exception, e:
    print 'error:', e
    sys.exit( 1 )

  if pid:
    cpid, status = os.wait()
    sys.exit( status >> 8 )

  try: 
    os.chdir( os.sep )
    os.setsid() 
    os.umask( 0 )
    pid = os.fork()
  except Exception, e: 
    print 'error:', e
    sys.exit( 1 )

  if pid:
    print pid
    sys.exit( 0 )

  os.dup2( log.fileno(), sys.stdout.fileno() )
  os.dup2( log.fileno(), sys.stderr.fileno() )
  os.dup2( nul.fileno(), sys.stdin.fileno()  )


def spawn( generator, port, debug, log ):

  try:
    listener = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
    listener.setblocking( 0 )
    listener.setsockopt( socket.SOL_SOCKET, socket.SO_REUSEADDR, listener.getsockopt( socket.SOL_SOCKET, socket.SO_REUSEADDR ) | 1 )
    listener.bind( ( '', port ) )
    listener.listen( 5 )
  except Exception, e:
    print 'error: failed to create socket:', e
    sys.exit( 1 )

  if log:
    fork( log )

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
      timeout = None

      for i in range( len( fibers ) -1, -1, -1 ):
        state = fibers[ i ].state

        if state and time.time() > state.expire:
          if isinstance( state, WAIT ):
            fibers[ i ].step()
          else:
            fibers[ i ].throw( 'Connection timed out' )
          state = fibers[ i ].state

        if not state:
          del fibers[ i ]
          continue

        if isinstance( state, RECV ):
          tryrecv[ state.fileno ] = fibers[ i ]
        elif isinstance( state, SEND ):
          trysend[ state.fileno ] = fibers[ i ]
        elif state.expire is None:
          continue

        mytimeout = max( time.time() - state.expire, 0 )
        if mytimeout < timeout or timeout is None:
          timeout = mytimeout

      if timeout is None:
        print '[ IDLE ]'
        sys.stdout.flush()
        canrecv, cansend, dummy = select.select( tryrecv, trysend, [] )
        print '[ BUSY ]'
        sys.stdout.flush()
      else:
        canrecv, cansend, dummy = select.select( tryrecv, trysend, [], timeout )

      for fileno in canrecv:
        if fileno is listener.fileno():
          fibers.append( myFiber( generator( *listener.accept() ) ) )
        else:
          tryrecv[ fileno ].step()
      for fileno in cansend:
        trysend[ fileno ].step()

  except KeyboardInterrupt:
    print time.strftime( '%D' ), 'HTTP Replicator terminated'
    sys.exit( 0 )
  except:
    print time.strftime( '%D' ), 'HTTP Replicator crashed'
    traceback.print_exc( file=sys.stdout )
    sys.exit( 1 )
