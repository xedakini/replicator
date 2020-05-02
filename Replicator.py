import Request, Response, fiber, weakref, logging
from Params import OPTS

DOWNLOADS = weakref.WeakValueDictionary()

def Replicator( client, address ):
  logging.info(f'Accepted request from [{address[0]}]:{address[1]}')
  request = Request.HttpRequest( client )
  for state in request:
    yield state

  try:
    for request in DOWNLOADS:
      protocol = DOWNLOADS[ request ]
      if protocol.Response:
        if issubclass( protocol.Response, Response.DataResponse ):
          logging.info('Joined running download')
          break
        del DOWNLOADS[ request ]
      else:
        yield fiber.WAIT()
    else:
      logging.debug(f'Switching to {request.Protocol.__name__}')
      protocol = DOWNLOADS[ request ] = request.Protocol( request )
      server = protocol.socket()
      while not protocol.Response:
        if protocol.hasdata():
          yield fiber.SEND(server, OPTS.timeout)
          protocol.send( server )
        else:
          yield fiber.RECV(server, OPTS.timeout)
          protocol.recv( server )
    logging.debug(f'Switching to {protocol.Response.__name__}')
    response = protocol.Response( protocol, request )
    server = protocol.socket()
  except Exception:
    logging.debug('Switching to ExceptionResponse')
    response = Response.ExceptionResponse( request )

  while not response.Done:
    if response.hasdata():
      yield fiber.SEND(client, OPTS.timeout)
      response.send( client )
    elif response.needwait():
      yield fiber.WAIT( response.needwait() )
    else:
      yield fiber.RECV(server, OPTS.timeout)
      response.recv( server )

  logging.info('Transaction successfully completed')


def run_event_loop(listener):
  fiber.spawn(Replicator, listener, OPTS.debug)
