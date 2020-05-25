from .subprocess import *

class PmcaRunner(PythonRunner):
 def __init__(self, cmd, args=[], timeout=10):
  super().__init__(script='pmca-console', args=[cmd]+args, timeout=timeout)

 def execUpdaterShellCommand(self, cmd):
  self.writeLine('shell echo\n%s\nshell echo' % cmd)
  self.expectLine(lambda l: l == '>')
  return '\n'.join(iter(self.readLine, '>')).lstrip('>')
