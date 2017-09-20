#!/usr/bin/env python3

import argparse
import logging
import multiprocessing
import os
import select
import socket
import struct


log_level = os.environ.get('PYMITM_LOG_LEVEL', 'INFO')
if log_level == 'DEBUG':
    LOG_LEVEL = logging.DEBUG
elif log_level == 'INFO':
    LOG_LEVEL = logging.INFO
elif log_level == 'WARNING':
    LOG_LEVEL = logging.INFO
elif log_level == 'ERROR':
    LOG_LEVEL = logging.INFO
elif log_level == 'CRITICAL':
    LOG_LEVEL = logging.INFO
else:
    raise Exception('Invalid log level: %s' % log_level)

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

SO_ORIGINAL_DST = 80


def parse_arguments():
    parser = argparse.ArgumentParser(description='A MITM tool')
    parser.add_argument(
        '--port', '-p', type=int, default=9999,
        help='The port to listen on for packets',
    )
    parser.add_argument(
        '--interface', '-i', default='127.0.0.1',
        help='The interface IP to listen on. Use 0.0.0.0 for all interfaces',
    )
    parser.add_argument(
        '--server', '-s',
        help=(
            'Force the destination server to be this address. The format for ' +
            'argument is "server:port", where "server" can be either an IP ' +
            'address or a domain. This option is used for testing'
        ),
    )
    return parser.parse_args()


def main():
    args = parse_arguments()
    logger.debug(args)

    # TODO: Validate interface and port
    logger.info('Starting proxy socket on %s:%d', args.interface, args.port)
    proxy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    proxy_sock.bind((args.interface, args.port))
    proxy_sock.listen(1)
    logger.info('Successfully started proxy socket')

    logger.info('Starting connection handler thread')
    q = multiprocessing.Queue()
    p = multiprocessing.Process(target=handle_connections, args=(q,))
    p.start()

    while True:
        client_sock, addr = proxy_sock.accept()
        logger.info('Accepted connection from client %s:%d', addr[0], addr[1])

        if args.server:
            dst_addr, dst_port = args.server.split(':')
            dst_port = int(dst_port)
        else:
            sockaddr_in = client_sock.getsockopt(socket.SOL_IP, SO_ORIGINAL_DST, 16)
            _, dst_port = struct.unpack('!HH', sockaddr_in[:4])
            dst_addr = socket.inet_ntoa(sockaddr_in[4:8])

        logger.info('Connecting to original destination server %s:%d', dst_addr, dst_port)
        server_sock = socket.create_connection((dst_addr, dst_port))
        logger.info('Successfully connected to server')
        local_ip, local_port = server_sock.getsockname()
        logger.debug('Local address: %s:%s', local_ip, local_port)

        q.put([client_sock, server_sock])


def handle_connections(q):
    logger.info('Successfully started connection handler thread')
    sockets = []
    c2s = {}
    s2c = {}
    while True:
        socks = None if q.empty() else q.get()
        if socks:
            if len(socks) != 2:
                logger.error('Expected two sockets')
            else:
                sockets.extend(socks)
                client_sock, server_sock = socks
                c2s[client_sock] = server_sock
                s2c[server_sock] = client_sock
                logger.info('One new connection was added')

        readable, _, _ = select.select(sockets, [], [], 3)
        logger.debug('Readable sockets: %s', str(readable))
        for s in readable:
            if s in c2s:
                client_sock = s
                server_sock = c2s[client_sock]
                data = s.recv(1024)
                if data == b'':
                    logger.info('Client disconnected')
                    # TODO: Handle server data after disconnect
                    client_sock.close()
                    del c2s[client_sock]
                    sockets.remove(client_sock)
                else:
                    logger.info('C -> S: %s', repr(data))
                    server_sock.send(data)
            else:
                assert s in s2c
                server_sock = s
                client_sock = s2c[server_sock]
                data = s.recv(1024)
                if data == b'':
                    logger.info('Server disconnected')
                    # TODO: Handle client data after disconnect
                    server_sock.close()
                    del s2c[server_sock]
                    sockets.remove(server_sock)
                else:
                    logger.info('S -> C: %s', repr(data))
                    client_sock.send(data)


if __name__ == '__main__':
    main()
