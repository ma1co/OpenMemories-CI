import logging
import queue
import subprocess
import sys
import threading

class SubprocessRunner:
 def __init__(self, name, args, cwd=None, timeout=10):
  self.p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=cwd, universal_newlines=True)
  self.q = queue.Queue()
  self.log = logging.getLogger(name)
  self.timeout = timeout
  threading.Thread(target=self._asyncRead, daemon=True).start()

 def _asyncRead(self):
  while True:
   l = self.p.stdout.readline()
   self.q.put(l)
   if l == '':
    break
   self.log.debug(l.rstrip('\n'))

 def readLine(self):
  try:
   l = self.q.get(timeout=self.timeout)
  except queue.Empty:
   raise TimeoutError()
  if l == '':
   raise EOFError()
  return l.rstrip('\n')

 def expectLine(self, f):
  return next(l for l in iter(self.readLine, None) if f(l))

 def writeLine(self, data):
  self.p.stdin.write(data + '\n')
  self.p.stdin.flush()

 def finish(self):
  self.p.terminate()
  self.p.wait(self.timeout)
  self.p.stdin.close()
  self.p.stdout.close()

 def __enter__(self):
  return self

 def __exit__(self, type, value, traceback):
  self.finish()


class PythonRunner(SubprocessRunner):
 def __init__(self, script, args=[], timeout=10):
  super().__init__(name=script, args=[sys.executable, '-u', '-m', script]+args, timeout=timeout)
