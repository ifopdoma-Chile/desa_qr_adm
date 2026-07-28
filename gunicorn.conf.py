import multiprocessing

bind = '127.0.0.1:8100'
workers = min(multiprocessing.cpu_count() * 2 + 1, 8)
worker_class = 'gevent'
worker_connections = 1000
timeout = 120
keepalive = 5
max_requests = 2000
max_requests_jitter = 200
accesslog = '/var/log/qr_adm/access.log'
errorlog = '/var/log/qr_adm/error.log'
loglevel = 'info'
