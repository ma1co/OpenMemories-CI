import json
import logging
import os
import socket
import tempfile
from .subprocess import *

class QemuRunner(SubprocessRunner):
 SERIAL_PORT_BASE = 4321

 def __init__(self, machine, args=[], files=[], numSerial=1, timeout=10):
  self.tempdir = tempfile.TemporaryDirectory()
  for fn, data in files.items():
   with open(os.path.join(self.tempdir.name, fn), 'wb') as f:
    f.write(data)

  args += ['-machine', machine]
  args += ['-display', 'none']
  args += ['-qmp', 'stdio']
  for i in range(numSerial):
   args += ['-serial', 'tcp::%d,server,mux' % (self.SERIAL_PORT_BASE + i)]

  super().__init__(name='qemu-system-arm', args=['qemu-system-arm']+args, cwd=self.tempdir.name, timeout=timeout, log=False)

  self.serial = []
  for i in range(numSerial):
   s = socket.create_connection(('127.0.0.1', self.SERIAL_PORT_BASE + i))
   f = s.makefile('rw')
   s.close()
   self.serial.append(Pipe(f, f, logging.getLogger('qemu-system-arm.serial%d' % i), timeout))
  if numSerial:
   self.defaultPipe = self.serial[0]

  self.execQmpCommand('qmp_capabilities')

 def close(self):
  super().close()
  for s in self.serial:
   s.close()

 def finish(self):
  if self.running():
   self.stdio.writeLine(json.dumps({'execute': 'quit'}))
  super().wait()
  self.tempdir.cleanup()

 def execQmpCommand(self, cmd, **kwargs):
  self.stdio.writeLine(json.dumps({'execute': cmd, 'arguments': kwargs}))
  l = self.stdio.expectLine(lambda l: 'return' in json.loads(l))
  return json.loads(l)['return']

 def execShellCommand(self, cmd):
  self.writeLine('\n%s\n' % cmd)
  self.expectLine(lambda l: l == '/ # %s' % cmd)
  return '\n'.join(iter(self.readLine, '/ # '))
