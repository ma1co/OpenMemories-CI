import logging
import unittest

class TestCase(unittest.TestCase):
 def __init__(self, methodName):
  super().__init__(methodName)
  self.log = logging.getLogger(self.__class__.__name__)
  logging.basicConfig(format='%(name)s: %(message)s', level=logging.DEBUG)

 def setUp(self):
  self.log.info('Starting test\n\n%s\n#\n# %s.%s\n#\n%s\n', '#'*80, self.__class__.__name__, self._testMethodName, '#'*80)
