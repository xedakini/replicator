class Head:

  class ParseError:

    pass

  def __init__( self, string ):

    lines = string.splitlines( True )

    firstline = lines.pop( 0 )

    if firstline[ -1 ] != '\n':
      raise self.ParseError

    self.__size = len( firstline )
    self.__args = firstline.rstrip().split( ' ', 2 )
    self.__kwargs = {}

    assert len( self.__args ) == 3, 'invalid header line %r' % firstline

    for line in lines:

      self.__size += len( line )

      if line == '\n' or line == '\r\n':
        return
      elif ':' in line:
        key, value = line.split( ':', 1 )
        self.__kwargs[ key.title() ] = value.strip()
      else:
        print 'Ignored invalid header line %r' % line

    raise self.ParseError

  def __len__( self ):

    return self.__size

  def __getitem__( self, key ):

    if isinstance( key, str ):
      return self.__kwargs.get( key.title(), None )
    else:
      assert key in ( 0, 1, 2 ), 'invalid key %r' % key
      return self.__args[ key ]

  def __setitem__( self, key, value ):

    if isinstance( key, str ):
      if isinstance( value, str ):
        self.__kwargs[ key.title() ] = value.strip()
      else:
        assert value is None, 'invalid value %r' % value
        self.__kwargs.pop( key.title(), None )
    else:
      assert key in ( 0, 1, 2 ), 'invalid key %r' % key
      assert isinstance( value, str ), 'invalid value %r' % value
      self.__args[ key ] = value.strip()

  def __lines( self ):

    return [ ' '.join( self.__args ) ] + [ '%s: %s' % item for item in self.__kwargs.items() ]

  def __str__( self ):

    return '\r\n'.join( self.__lines() ) + '\r\n\r\n'

  def __repr__( self ):

    return ' > ' + '\n > '.join( self.__lines() )
