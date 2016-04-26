# This file is copied from https://bitbucket.org/alexappsnet/short
from errno import EWOULDBLOCK, EAGAIN
import logging
import os
import socket

from tornado.ioloop import IOLoop
from tornado.netutil import set_close_exec

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class UDPServer(object):
    def __init__(self, name, port, on_receive, address=None, family=socket.AF_INET, io_loop=None):
        self.io_loop = io_loop or IOLoop.instance()
        self._on_receive = on_receive
        self._log = logging.getLogger(name)
        self._sockets = []

        flags = socket.AI_PASSIVE

        if hasattr(socket, "AI_ADDRCONFIG"):
            flags |= socket.AI_ADDRCONFIG

        # find all addresses to bind, bind and register the "READ" callback
        for res in set(socket.getaddrinfo(address, port, family, socket.SOCK_DGRAM, 0, flags)):
            af, sock_type, proto, canon_name, sock_addr = res
            self._open_and_register(af, sock_type, proto, sock_addr)

        self._log.debug('Started')

    def _open_and_register(self, af, sock_type, proto, sock_addr):
        sock = socket.socket(af, sock_type, proto)
        set_close_exec(sock.fileno())
        if os.name != 'nt':
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(0)

        self._log.debug('Binding to %s...', repr(sock_addr))
        sock.bind(sock_addr)

        def read_handler(fd, events):
            while True:
                try:
                    data, address = sock.recvfrom(65536)
                except socket.error as e:
                    if e.args[0] in (EWOULDBLOCK, EAGAIN):
                        return
                    raise
                self._on_receive(data, address)

        self.io_loop.add_handler(sock.fileno(), read_handler, IOLoop.READ)
        self._sockets.append(sock)

    def stop(self):
        self._log.debug('Closing %d socket(s)...', len(self._sockets))
        for sock in self._sockets:
            self.io_loop.remove_handler(sock.fileno())
            sock.close()

