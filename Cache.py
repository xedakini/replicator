from __future__ import absolute_import, division, print_function, unicode_literals
import six
import Params, os, hashlib


class File:

  size = -1
  mtime = -1

  def __init__( self, path ):

    if Params.MAXFILELEN > -1:
      newpath = os.sep.join( item if len(item) <= Params.MAXFILELEN else 
        item[:Params.MAXFILELEN-34] + '..' + hashlib.md5( item[Params.MAXFILELEN-34:] ).hexdigest()
          for item in path.split( os.sep ) )
      if newpath != path:
        print('Shortened path to %s characters' % '/'.join( str(len(w)) for w in newpath.split(os.sep) ))
        path = newpath

    sep = path.find( '?' )
    if sep != -1:
      path = path[ :sep ] + path[ sep: ].replace( '/', '%2F' )
    if Params.FLAT:
      path = os.path.basename( path )
    if Params.VERBOSE:
      print('Cache position:', path)

    self.__path = Params.ROOT + path
    self.__file = None

  def partial( self ):

    return os.path.isfile( self.__path + Params.SUFFIX ) and os.stat( self.__path + Params.SUFFIX )

  def full( self ):

    return os.path.isfile( self.__path ) and os.stat( self.__path )

  def open_new( self ):

    print('Preparing new file in cache')
    try:
      dir = os.path.dirname(self.__path)
      if not os.path.exists(dir):
          os.makedirs(dir)
      self.__file = open( self.__path + Params.SUFFIX, 'w+' )
    except Exception as e:
      print('Failed to open file:', e)
      self.__file = os.tmpfile()

  def open_partial( self, offset=-1 ):

    self.mtime = os.stat( self.__path + Params.SUFFIX ).st_mtime
    self.__file = open( self.__path + Params.SUFFIX, 'a+' )
    if offset >= 0:
      assert offset <= self.tell(), 'range does not match file in cache'
      self.__file.seek( offset )
      self.__file.truncate()
    print('Resuming partial file in cache at byte', self.tell())

  def open_full( self ):

    self.mtime = os.stat( self.__path ).st_mtime
    self.__file = open( self.__path, 'r' )
    self.size = self.tell()
    print('Reading complete file from cache')

  def remove_full( self ):

    os.remove( self.__path )
    print('Removed complete file from cache')

  def remove_partial( self ):

    print('Removed partial file from cache')
    os.remove( self.__path + Params.SUFFIX )

  def read( self, pos, size ):

    self.__file.seek( pos )
    return self.__file.read( size )

  def write( self, chunk ):

    self.__file.seek( 0, 2 )
    return self.__file.write( chunk )

  def tell( self ):

    self.__file.seek( 0, 2 )
    return self.__file.tell()

  def close( self ):

    size = self.tell()
    self.__file.close()
    if self.mtime >= 0:
      os.utime( self.__path + Params.SUFFIX, ( self.mtime, self.mtime ) )
    if self.size == size:
      os.rename( self.__path + Params.SUFFIX, self.__path )
      print('Finalized', self.__path)

  def __del__( self ):

    try:
      self.close()
    except:
      pass
