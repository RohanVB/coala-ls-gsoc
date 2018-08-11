import sys
from os import chdir
from json import dumps

from coalib import coala_main
from coalib.output.JSONEncoder import create_json_encoder
from .concurrency import TrackedProcessPool
from .utils.log import configure_logger, reset_logger

import logging
logger = logging.getLogger(__name__)


class coalaWrapper:
    """
    Provide an abstract interaction layer to coala
    to perform the actual analysis.
    """

    def __init__(self, max_jobs=1, max_workers=1):
        """
        coalaWrapper uses a tracked process pool to run
        concurrent cycles of code analysis.

        :param max_jobs:
            The maximum number of concurrent jobs to permit.
        :param max_workers:
            The number of threads to maintain in process pool.
        """
        self._tracked_pool = TrackedProcessPool(
            max_jobs=max_jobs, max_workers=max_workers)

    @staticmethod
    def _run_coala(arg_list=None):
        results, retval, _ = coala_main.run_coala(arg_list=arg_list)
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
    def analyse_file(file_proxy, tags=None):
        """
        Invoke and performs the actual coala analysis.

        :param file_proxy:
            The proxy of the file coala analysis is to be
            performed on.
        :return:
            A valid json string containing results.
        """
        arg_list = ['--json',
                    '--find-config',
                    '--limit-files',
                    file_proxy.filename, ]

        if tags is not None:
            if type(tags) not in (list, tuple):
                tags = [tags, ]

            arg_list += ['--filter-by', 'section_tags'] + list(tags)

        workspace = file_proxy.workspace
        if workspace is None:
            workspace = '.'
        chdir(workspace)

        results, retval = coalaWrapper._run_coala(arg_list)
        return coalaWrapper._process_coala_op(results, retval)

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
        result = self._tracked_pool.exec_func(
            coalaWrapper.analyse_file, (file_proxy, tags),
            kargs, force=force)

        if result is False:
            logging.debug('Failed p_analysis_file() on %s', file_proxy)

        return result

    def close(self):
        """
        Perform resource clean up.
        """
        self._tracked_pool.shutdown(True)
