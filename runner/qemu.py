import os
import tempfile
from .subprocess import *

class QemuRunner(SubprocessRunner):
 def __init__(self, machine, args=[], files=[], timeout=10):
  self.tempdir = tempfile.TemporaryDirectory()
  for fn, data in files.items():
   with open(os.path.join(self.tempdir.name, fn), 'wb') as f:
    f.write(data)
  super().__init__(name='qemu-system-arm', args=['qemu-system-arm', '-nographic', '-machine', machine]+args, cwd=self.tempdir.name, timeout=timeout)

 def finish(self):
  super().finish()
  self.tempdir.cleanup()

 def execShellCommand(self, cmd):
  self.writeLine('\n%s\n' % cmd)
  self.expectLine(lambda l: l == '/ # %s' % cmd)
  return '\n'.join(iter(self.readLine, '/ # '))
