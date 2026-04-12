# Must be imported before any brother_ql module.
# brother_ql.devicedependent calls logger.warn() (deprecated in Python 3.14)
# which fires at import time. Suppressing via the logging level is the only
# reliable fix — warnings.filterwarnings doesn't catch it.
import logging
logging.getLogger("brother_ql.devicedependent").setLevel(logging.CRITICAL)
