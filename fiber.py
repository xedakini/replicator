import sys, os, select, time, logging


class SEND:
    def __init__(self, sock, timeout):
        self.fileno = sock.fileno()
        self.expire = time.time() + timeout

    def __str__(self):
        return 'SEND(%i,%s)' % (self.fileno,
                                time.strftime('%H:%M:%S',
                                              time.localtime(self.expire)))


class RECV:
    def __init__(self, sock, timeout):
        self.fileno = sock.fileno()
        self.expire = time.time() + timeout

    def __str__(self):
        return 'RECV(%i,%s)' % (self.fileno,
                                time.strftime('%H:%M:%S',
                                              time.localtime(self.expire)))


class WAIT:
    def __init__(self, timeout=None):
        self.expire = time.time() + timeout if timeout else None

    def __str__(self):
        return 'WAIT(%s)' % (self.expire and time.strftime(
            '%H:%M:%S', time.localtime(self.expire)))


class Fiber:
    def __init__(self, generator):
        self.__generator = generator
        self.state = WAIT()

    def step(self, throw=None):
        self.state = None
        try:
            if throw:
                assert hasattr(self.__generator, 'throw'), throw
                self.__generator.throw(AssertionError, throw)
            state = next(self.__generator)
            assert isinstance(
                state, (SEND, RECV, WAIT)), 'invalid waiting state %r' % state
            self.state = state
        except KeyboardInterrupt:
            raise
        except StopIteration:
            del self.__generator
            pass
        except AssertionError as msg:
            logging.error(f'Error: {msg}')
        except:
            logging.error(f'Error: {msg}', exc_info=1)

    def __repr__(self):
        return '%i: %s' % (self.__generator.gi_frame.f_lineno, self.state)


class GatherFiber(Fiber):
    def __init__(self, generator):
        Fiber.__init__(self, generator)
        self.__chunks = ['[ 0.00 ] %s\n' % time.ctime()]
        self.__start = time.time()
        self.__newline = True

    def step(self, throw=None):
        stdout = sys.stdout
        stderr = sys.stderr
        try:
            sys.stdout = sys.stderr = self
            Fiber.step(self, throw)
        finally:
            sys.stdout = stdout
            sys.stderr = stderr

    def write(self, string):
        if self.__newline:
            self.__chunks.append('%6.2f   ' % (time.time() - self.__start))
        self.__chunks.append(string)
        self.__newline = string.endswith('\n')

    def __del__(self):
        sys.stdout.writelines(self.__chunks)
        if not self.__newline:
            sys.stdout.write('\n')


class DebugFiber(Fiber):
    id = 0

    def __init__(self, generator):
        Fiber.__init__(self, generator)
        self.__id = DebugFiber.id
        sys.stdout.write('[ %04X ] %s\n' % (self.__id, time.ctime()))
        self.__newline = True
        self.__stdout = sys.stdout
        DebugFiber.id = (self.id + 1) % 65535

    def step(self, throw=None):
        stdout = sys.stdout
        stderr = sys.stderr
        try:
            sys.stdout = sys.stderr = self
            Fiber.step(self, throw)
            if self.state:
                logging.info(f'Waiting at {self}')
        finally:
            sys.stdout = stdout
            sys.stderr = stderr

    def write(self, string):
        if self.__newline:
            self.__stdout.write('  %04X   ' % self.__id)
        self.__stdout.write(string)
        self.__stdout.flush()
        self.__newline = string.endswith('\n')


def spawn(generator, listener, debug=False):
    if debug:
        myFiber = DebugFiber
    else:
        myFiber = GatherFiber

    logging.info(f'[ INIT ] {generator.__name__} started at [%s]:%i' %
                 listener.getsockname()[:2])
    try:
        fibers = []
        while True:
            tryrecv = {listener.fileno(): None}
            trysend = {}
            expire = None
            now = time.time()

            i = len(fibers)
            while i:
                i -= 1
                state = fibers[i].state

                if state and (state.expire is None or now > state.expire):
                    if isinstance(state, WAIT):
                        fibers[i].step()
                    else:
                        fibers[i].step(throw='connection timed out')
                    state = fibers[i].state

                if not state:
                    del fibers[i]
                    continue

                if isinstance(state, RECV):
                    tryrecv[state.fileno] = fibers[i]
                elif isinstance(state, SEND):
                    trysend[state.fileno] = fibers[i]
                elif state.expire is None:
                    continue

                if state.expire is None or expire is None or state.expire < expire:
                    expire = state.expire

            if expire is None:
                logging.info(f'[ IDLE ] {time.ctime()}')
                sys.stdout.flush()
                canrecv, cansend, dummy = select.select(tryrecv, trysend, [])
                logging.info(f'[ BUSY ] {time.ctime()}')
                sys.stdout.flush()
            else:
                canrecv, cansend, dummy = select.select(
                    tryrecv, trysend, [], max(expire - now, 0))

            for fileno in canrecv:
                if fileno is listener.fileno():
                    fibers.append(myFiber(generator(*listener.accept())))
                else:
                    tryrecv[fileno].step()
            for fileno in cansend:
                trysend[fileno].step()

    except KeyboardInterrupt:
        logging.info(f'[ DONE ] {generator.__name__} terminated')
        sys.exit(0)
    except:
        logging.exception(f'[ DONE ] {generator.__name__} crashed')
        sys.exit(f'{generator.__name__} crashed')
