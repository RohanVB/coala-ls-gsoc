import sys
from os import chdir
from json import dumps

from coalib import coala_main
from coalib.output.JSONEncoder import create_json_encoder
from .concurrency import TrackedProcessPool
from .utils.log import configure_logger, reset_logger
from .utils.cache import coalaLsProxyMapFileCache

import logging
logger = logging.getLogger(__name__)


class coalaWrapper:
    """
    Provide an abstract interaction layer to coala
    to perform the actual analysis.
    """

    def __init__(self, max_jobs=1, max_workers=1, fileproxy_map=None):
        """
        coalaWrapper uses a tracked process pool to run
        concurrent cycles of code analysis.

        :param max_jobs:
            The maximum number of concurrent jobs to permit.
        :param max_workers:
            The number of threads to maintain in process pool.
        :param fileproxy_map:
            The FileProxyMap to use while building a Cache Map.
        """
        self._fileproxy_map = fileproxy_map
        self._tracked_pool = TrackedProcessPool(
            max_jobs=max_jobs, max_workers=max_workers)

    @staticmethod
    def _run_coala(arg_list=None, cache=None):
        results, retval, _ = coala_main.run_coala(
                                arg_list=arg_list,
                                cache=cache)

        return results, retval

    @staticmethod
    def _process_coala_op(results, retval):
        logger.debug('Return value {}'.format(retval))

        encoder = create_json_encoder()
        results = {'results': results, }

        return dumps(results,
                     cls=encoder,
                     sort_keys=True,
                     indent=2,
                     separators=(',', ': '))

    @staticmethod
    def analyse_file(file_proxy, cache_map=None, tags=None):
        """
        Invoke and performs the actual coala analysis.

        :param file_proxy:
            The proxy of the file coala analysis is to be
            performed on.
        :return:
            A valid json string containing results.
        """
        cache = None
        arg_list = ['--json',
                    '--find-config',
                    '--limit-files',
                    file_proxy.filename, ]

        if tags is not None:
            if type(tags) not in (list, tuple):
                tags = [tags,]

            arg_list += ['--filter-by', 'section_tags'] + list(tags)

        if cache_map is not None:
            cache = cache_map
            arg_list += ['--flush-cache']

        workspace = file_proxy.workspace
        if workspace is None:
            workspace = '.'
        chdir(workspace)

        results, retval = coalaWrapper._run_coala(arg_list, cache)
        return coalaWrapper._process_coala_op(results, retval), retval

    def p_analyse_file(self, file_proxy, force=False, tags=None, **kargs):
        """
        It is a concurrent version of coalaWrapper.analyse_file().
        force indicates whether the request should pre-empt running
        cycles.

        :param file_proxy:
            The proxy of the file coala analysis is to be
            performed on.
        :param force:
            The force flag to use while preparing a slot using
            JobTracker.
        """
        cache_map = None
        if self._fileproxy_map is not None:
            # Enable flushing of cache
            cache_map = coalaLsProxyMapFileCache(
                None, file_proxy.workspace or '.', flush_cache=True)
            cache_map.set_proxymap(self._fileproxy_map)

        result = self._tracked_pool.exec_func(
            coalaWrapper.analyse_file, (file_proxy, cache_map, tags),
            kargs, force=force)

        if result is False:
            logging.debug('Failed p_analysis_file() on %s', file_proxy)

        return result

    def close(self):
        """
        Perform resource clean up.
        """
        self._tracked_pool.shutdown(True)

    @staticmethod
    def retval_to_message(retval):
        """
        Returns a presentable UI message from corresponding
        return value of coala.

        :param retval:
            Integer value to find a corresponding message.
        :return:
            Message as a String describing a given return value.
        """
        if retval == 0:
            return 'No issue found on analysis.'
        elif retval == 1:
            return 'Some issues found on analysis.'
        elif retval == 2:
            return ('Empty configuration, Please enable some sections '
                    'for analysis using open, save, change section tags.')
        else:
            return ('Unknown issue occurred while performing coala '
                    'analysis on file. Please report this behavior.')
