import socket
from sys import argv
from time import time
from pathlib import Path
from os.path import relpath
from json import loads, dump
from argparse import ArgumentParser

from jsonrpc.streams import JsonRpcStreamWriter, JsonRpcStreamReader


class UriUtils:

    @staticmethod
    def path_from_uri(uri):
        if not uri.startswith('file://'):
            return uri

        _, path = uri.split('file://', 1)
        return path

    @staticmethod
    def file_to_uri(filename):
        return Path(filename).as_uri()


class Closed:
    closed = True


class DupeRpcJsonStreamReader(JsonRpcStreamReader):

    def pseudo_close(self):
        self._dupe_rfile = self._rfile
        self._rfile = Closed()
        self.duped = True

    def undo_close(self):
        self._rfile = self._dupe_rfile
        self._dupe_rfile = None
        self.duped = False


def initialize(root):
    return {
        'method': 'initialize',
        'params': {
            'rootPath': root,
            'capabilities': {
                'textDocumentSync': 1,
            },
        },
        'id': 1,
        'jsonrpc': '2.0',
    }


def didOpen(name):
    with open(name) as code:
        return {
            'method': 'textDocument/didOpen',
            'params': {
                'textDocument': {
                    'uri': UriUtils.file_to_uri(name),
                    'languageId': 'python',
                    'version': 1,
                    'text': code.read(),
                },
            },
            'jsonrpc': '2.0',
        }


def didChange(name, new_code=''):
    return {
        'method': 'textDocument/didChange',
        'params': {
            'textDocument': {
                'uri': UriUtils.file_to_uri(name),
                'version': 1,
            },
            'contentChanges': [
                {
                    'text': new_code,
                }
            ],
        },
        'jsonrpc': '2.0',
    }


def didSave(name):
    return {
        'method': 'textDocument/didSave',
        'params': {
            'textDocument': {
                'uri': UriUtils.file_to_uri(name),
            },
        },
        'jsonrpc': '2.0',
    }


def didClose(name):
    return {
        'method': 'textDocument/didClose',
        'params': {
            'textDocument': {
                'uri': UriUtils.file_to_uri(name),
            },
        },
        'jsonrpc': '2.0',
    }


def connect_socket(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    return sock


def make_sock_to_file(sock):
    return sock.makefile('rwb')


def get_streams(file_like):
    return (DupeRpcJsonStreamReader(file_like),
            JsonRpcStreamWriter(file_like))


def send_message(json, writer):
    writer.write(json)


def init_metric():
    return {
        'start': time(),
        'end': -1
    }


def get_event_and_file(event):
    if event.isalpha():
        return (event, -1)
    else:
        return (event[:1], int(event[1:]))


def unpack_scenario(el):
    if el.startswith('['):
        return (el[1:-1]).split(',')

    return [el]


def perform_sampling(rx, tx, max_jobs, root, files, schedule):
    performances = []

    for scenario in schedule:
        scenario = unpack_scenario(scenario)

        if isinstance(scenario, list):
            if len(scenario) > max_jobs:
                raise ValueError('max_jobs >= schedule lengths')
            if len(scenario) > len(files):
                raise ValueError('len(files) < schedule lengths')

        perf_record = {}
        responses = {'total': len(scenario), 'current': 0}

        def wait_until_message(response):
            if 'result' in response:
                file_rel = 'init'
            elif response['method'] == 'textDocument/publishDiagnostics':
                uri = response['params']['uri']
                file = UriUtils.path_from_uri(uri)
                file_rel = relpath(file, root)

            responses['current'] += 1
            perf_record[file_rel]['times']['end'] = time()

            if responses['current'] >= responses['total']:
                rx.pseudo_close()

        for event in scenario:
            event_type, file_no = get_event_and_file(event)
            if file_no is not None:
                file = files[file_no]
                file_rel = relpath(file, root)

            if event_type == 'i':
                perf_record['init'] = {
                    'type': 'initialize',
                    'times': init_metric()
                }
                send_message(initialize(root), tx)
            elif event_type == 'o':
                perf_record[file_rel] = {
                    'type': 'didOpen',
                    'times': init_metric()
                }
                send_message(didOpen(file), tx)
            elif event_type == 's':
                perf_record[file_rel] = {
                    'type': 'didSave',
                    'times': init_metric()
                }
                send_message(didSave(file), tx)

        rx.listen(wait_until_message)
        rx.undo_close()

        performances.append(perf_record)

    rx.close()
    return performances


def get_args():
    arg = ArgumentParser()

    arg.add_argument('--host',
                     default='127.0.0.1',
                     help='Host of running language server')
    arg.add_argument('--port',
                     default=2087,
                     help='Serving port of language server')
    arg.add_argument('--max-jobs',
                     type=int,
                     required=True,
                     help='Number of jobs language server was'
                          'was configured to work on')
    arg.add_argument('--schedule',
                     nargs='+',
                     required=True,
                     help='The schedule of requests to test '
                          'language server with. Schedule can '
                          'be represented using i for initialize '
                          'request, o for didOpen, s for didSave '
                          'and c for didChange. All the requests '
                          'other than i require a file to work with, '
                          'this can be configured using an index with '
                          'respect to the --files list starting with 0. '
                          'For example o1 implies send open request '
                          'for file 1 in the files list. Enclosing '
                          'a comma separated list of schedules in [] '
                          'makes them run concurrently and the test '
                          'runner only moves to next event once all the '
                          'events return. An example schedule can be '
                          'as --schedule i o0 [s0,o1].')
    arg.add_argument('--workspace',
                     required=True,
                     help='Absolute root folder of the project')
    arg.add_argument('--files',
                     nargs='+',
                     required=True,
                     help='A list of files to work with during testing')
    arg.add_argument('--dest',
                     required=True,
                     help='Destination to dump the sample record')
    arg.add_argument('--meta',
                     help='Meta information to add to the sample dump')

    return arg.parse_args(argv[1:])


if __name__ == '__main__':
    args = get_args()

    sock = connect_socket(args.host, args.port)
    like = make_sock_to_file(sock)
    rx, tx = get_streams(like)

    performances = perform_sampling(rx,
                                    tx,
                                    args.max_jobs,
                                    args.workspace,
                                    args.files,
                                    args.schedule)

    sample_report = {}
    sample_report['meta'] = args.meta
    sample_report['files'] = args.files
    sample_report['metrics'] = performances
    sample_report['max-jobs'] = args.max_jobs
    sample_report['schedule'] = args.schedule
    sample_report['workspace'] = args.workspace

    print(sample_report)
    with open(args.dest, 'w') as like:
        dump(sample_report, like)
