#!/usr/bin/env python3

import argparse
import logging
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
        '--server', '-s',
        help=(
            'Force the destination server to be this address. The format for ' +
            'argument is "server:port", where "server" can be either an IP ' +
            'address or a domain. This option is used for testing'),
    )
    return parser.parse_args()


def main():
    args = parse_arguments()
    logger.debug(args)

    logger.info('Starting proxy socket on localhost:%d' % args.port)
    proxy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    proxy_sock.bind(('localhost', args.port))
    proxy_sock.listen(1)
    logger.info('Successfully started proxy socket')

    while True:
        client_sock, addr = proxy_sock.accept()
        logger.info('Accepted connection from client %s:%d' % (addr[0], addr[1]))

        if args.server:
            dst_addr, dst_port = args.server.split(':')
            dst_port = int(dst_port)
        else:
            sockaddr_in = client_sock.getsockopt(socket.SOL_IP, SO_ORIGINAL_DST, 16)
            _, dst_port = struct.unpack('!HH', sockaddr_in[:4])
            dst_addr = socket.inet_ntoa(sockaddr_in[4:8])

        logger.info('Connecting to original destination server %s:%d' % (dst_addr, dst_port))
        server_sock = socket.create_connection((dst_addr, dst_port))
        logger.info('Successfully connected to server')
        logger.debug('Local address: %s:%s' % server_sock.getsockname())

        open_socks = [client_sock, server_sock]
        while len(open_socks) != 0:
            readable, _, _ = select.select(open_socks, [], [], 3)
            logger.debug('Readable sockets: ' + str(readable))
            for s in readable:
                if s is client_sock:
                    data = s.recv(1024)
                    if data == b'':
                        logger.info('Client disconnected')
                        open_socks.remove(client_sock)
                        server_sock.close()
                    else:
                        logger.info('C -> S: ' + repr(data))
                        server_sock.send(data)
                else:
                    assert s is server_sock
                    data = s.recv(1024)
                    if data == b'':
                        logger.info('Server disconnected')
                        open_socks.remove(server_sock)
                    else:
                        logger.info('S -> C: ' + repr(data))
                        client_sock.send(data)

if __name__ == '__main__':
    main()