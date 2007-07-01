import sys, os, select, time, socket, traceback


class Thread:

  softspace = 0
  expire = None
  fileno = None

  def __init__( self, generator, timeout ):

    self.__generator = generator
    self.__timeout = timeout
    self.__lines = [ '\n', time.strftime( '%D Created new thread\n' ) ]
    self.__buffer = ' '

  def write( self, string ):

    self.__buffer += string
    if self.softspace:
      self.__lines.append( time.strftime( '%H:%M:%S' ) + self.__buffer )
      self.__buffer = ' '

  def step( self, waitqueue, recvqueue, sendqueue ):

    try:

      try:
        stdout = sys.stdout
        sys.stdout = self
        cmd, arg = self.__generator.next()
      finally:
        pass
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

    except KeyboardInterrupt:
      raise
    except StopIteration:
      print >> self, 'Done'
    except AssertionError, msg:
      print >> self, 'Error:', msg
    except:
      print >> self, ''.join( traceback.format_exception( sys.exc_type, sys.exc_value, sys.exc_traceback ) ).rstrip()

  def __repr__( self ):

    return 'thread %i waiting in line %i' % ( id( self.__generator ), self.__generator.gi_frame.f_lineno )

  def __del__( self ):

    try:
      stdout = sys.stdout
      sys.stdout = self
      del self.__generator # call destructors for output
    except:
      print ''.join( traceback.format_exception( sys.exc_type, sys.exc_value, sys.exc_traceback ) ).rstrip()

    sys.stdout = stdout
    sys.stdout.writelines( self.__lines )


def queuerun( waitqueue, recvqueue, sendqueue ):

  firsttimeout = None

  i = 0
  while len( waitqueue ) > i:
    thistimeout = waitqueue[ i ].expire and waitqueue[ i ].expire - time.time()
    if thistimeout < 0:
      waitqueue[ i ].step( waitqueue, recvqueue, sendqueue )
      del waitqueue[ i ]
    else:
      firsttimeout = min( firsttimeout or 1e99, thistimeout )
      i += 1

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
      print >> recvqueue[ 1 ], 'Timed out'
      del recvqueue[ 0 ]
    else:
      firsttimeout = min( firsttimeout or 1e99, thistimeout )
      break

# print
# print 'wait:', waitqueue
# print 'recv:', recvqueue[ 1: ]
# print 'send:', sendqueue

  canrecv, cansend, dummy = select.select( recvqueue, sendqueue, [], firsttimeout )
  accept = False

  for thread in canrecv:
    if thread is recvqueue[ 0 ]:
      accept = True
    else:
      recvqueue.remove( thread )
      thread.step( waitqueue, recvqueue, sendqueue )

  for thread in cansend:
    sendqueue.remove( thread )
    thread.step( waitqueue, recvqueue, sendqueue )

  return accept


def spawn( generator, port, timeout ):

  listener = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
  listener.setblocking( 0 )
  listener.setsockopt( socket.SOL_SOCKET, socket.SO_REUSEADDR, listener.getsockopt( socket.SOL_SOCKET, socket.SO_REUSEADDR ) | 1 )
  listener.bind( ( '', port ) )
  listener.listen( 5 )

  print time.strftime( '%D' ), 'HTTP Replicator started'

  try:

    waitqueue = []
    recvqueue = [ listener ]
    sendqueue = []
    while True:
      if queuerun( waitqueue, recvqueue, sendqueue ):
        waitqueue.append( Thread( generator( *listener.accept() ), timeout ) )

  except KeyboardInterrupt:
    print
    print time.strftime( '%D' ), 'HTTP Replicator terminated'
  except:
    print
    print time.strftime( '%D' ), 'HTTP Replicator crashed'
    raise
