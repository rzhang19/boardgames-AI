import os

from django.db import connections
from django.test.runner import DiscoverRunner


class ParallelDiscoverRunner(DiscoverRunner):

    def __init__(self, **kwargs):
        if kwargs.get('parallel', 0) == 0:
            kwargs['parallel'] = os.cpu_count() or 1
        super().__init__(**kwargs)

    def teardown_databases(self, old_config, **kwargs):
        for connection, old_name, should_create in old_config:
            if should_create:
                try:
                    connection.creation.destroy_test_db(
                        old_name, self.verbosity, keepdb=self.keepdb,
                    )
                except FileNotFoundError:
                    pass
            connection.close()
