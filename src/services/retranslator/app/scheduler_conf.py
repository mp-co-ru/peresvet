from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor

executors = {
    'default': ProcessPoolExecutor(5)
}

job_defaults = {
    'coalesce': False,
    'max_instances': 3
}