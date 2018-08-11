from coalib.misc.Caching import ProxyMapFileCache

import logging
logger = logging.getLogger(__name__)


class coalaLsProxyMapFileCache(ProxyMapFileCache):
    """
    coalaLsProxyMapFileCache is a ProxyMap that is used
    to provides an in memory copy of the files to coala
    for analysis.
    """

    def __init__(self, *args, **kargs):
        """
        Directly initializes the associated FileCache.
        """
        super().__init__(*args, **kargs)
        logger.info('Intialized new coalaLsProxyMapFileCache')

    def track_files(self, files):
        """
        ``track_files()`` is used to track the files during
        caching, this provides a mechanism for coala-ls to
        relay back some messages regarding the internals of
        coala.
        """
        result = super().track_files(files)
        logger.info('tracking files: {}'.format(files))
        return result

    def untrack_files(self, files):
        """
        ``untrack_files()`` is used to drop files from coala
        cache interanally. This overridden method provides a
        window to log the coala internals.
        """
        result = super().untrack_files(files)
        logger.info('untracking files: {}'.format(files))
        return result
