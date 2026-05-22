"""Source collectors — pluggable adapters that turn external feeds into
:class:`~app.domain.schemas.RawItem` objects.

Add a new source by subclassing :class:`~app.collectors.base.Collector` and
registering it in :func:`~app.collectors.registry.build_collectors`.
"""
