import os

bind = '0.0.0.0:' + os.environ.get('PORT', '10000')
workers = 1
threads = 2
timeout = 120
graceful_timeout = 120
accesslog = '-'
errorlog = '-'
capture_output = True