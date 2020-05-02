import Params, os, hashlib, logging


class File:

  size = -1
  mtime = -1

  def __init__(self, origpath):
    path = os.path.normpath(origpath)
    sep = path.find('?')
    if sep != -1:
      path = path[:sep] + path[sep:].replace('/', '%2F')

    if Params.MAXFILELEN > -1:
      newpath = os.sep.join( item if len(item) <= Params.MAXFILELEN else
        item[:Params.MAXFILELEN-34] + '..' + hashlib.md5( item[Params.MAXFILELEN-34:] ).hexdigest()
          for item in path.split( os.sep ) )
      if newpath != path:
        logging.info('Shortened path to %s characters', '/'.join( str(len(w)) for w in newpath.split(os.sep) ))
        path = newpath

    if Params.FLAT:
      path = os.path.basename( path )
    if path[0] == os.sep or path[:3] == '..'+os.sep:
        raise AssertionError(f'requested cache path outside of cache root: {origpath}')
    logging.debug(f'Cache position: {path}')

    self.__path = path
    self.__temppath = path + Params.SUFFIX
    self.__file = None

  def partial( self ):

    return os.path.isfile(self.__temppath) and os.stat(self.__temppath)

  def full( self ):

    return os.path.isfile( self.__path ) and os.stat( self.__path )

  def open_new( self ):

    logging.info('Preparing new file in cache')
    try:
      dir = os.path.dirname(self.__path)
      if dir != '' and not os.path.exists(dir):
          os.makedirs(dir)
      self.__file = open(self.__temppath, 'wb+')
    except Exception as e:
      logging.info(f'Failed to open file {self.__path} for writing: {e}')
      self.__file = os.tmpfile()

  def open_partial( self, offset=-1 ):

    self.mtime = os.stat(self.__temppath).st_mtime
    self.__file = open(self.__temppath, 'ab+')
    if offset >= 0:
      assert offset <= self.tell(), 'range does not match file in cache'
      self.__file.seek( offset )
      self.__file.truncate()
    logging.info(f'Resuming partial file in cache at byte {self.tell()}')

  def open_full( self ):

    self.mtime = os.stat( self.__path ).st_mtime
    self.__file = open( self.__path, 'rb' )
    self.size = self.tell()
    logging.info('Reading complete file from cache')

  def remove_full( self ):

    os.remove( self.__path )
    logging.info('Removed complete file from cache')

  def remove_partial( self ):

    logging.info('Removed partial file from cache')
    os.remove(self.__temppath)

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
      os.utime(self.__temppath, (self.mtime, self.mtime))
    if self.size == size:
      os.rename(self.__temppath, self.__path)
      logging.info(f'Finalized {self.__path}')

  def __del__( self ):

    try:
      self.close()
    except:
      pass
