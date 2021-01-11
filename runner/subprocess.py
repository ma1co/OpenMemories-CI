import logging
import queue
import subprocess
import sys
import threading

class SubprocessRunner:
 def __init__(self, name, args, cwd=None, timeout=10, log=True):
  self.p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=cwd, universal_newlines=True)
  self.stdio = Pipe(self.p.stdout, self.p.stdin, logging.getLogger(name + '.stdio') if log else None, timeout)
  self.defaultPipe = self.stdio

 def running(self):
  return self.p.poll() is None

 def close(self):
  self.stdio.close()

 def wait(self):
  self.p.wait()
  self.close()

 def finish(self):
  self.p.terminate()
  self.wait()

 def __enter__(self):
  return self

 def __exit__(self, type, value, traceback):
  self.finish()

 def readLine(self):
  return self.defaultPipe.readLine()

 def expectLine(self, f):
  return self.defaultPipe.expectLine(f)

 def writeLine(self, data):
  self.defaultPipe.writeLine(data)


class PythonRunner(SubprocessRunner):
 def __init__(self, script, args=[], timeout=10, log=True):
  super().__init__(name=script, args=[sys.executable, '-u', '-m', script]+args, timeout=timeout, log=log)


class Pipe:
 def __init__(self, readFile, writeFile, log=None, timeout=10):
  self.readFile = readFile
  self.writeFile = writeFile
  self.log = log
  self.timeout = timeout
  self.q = queue.Queue()
  threading.Thread(target=self._asyncRead, daemon=True).start()

 def close(self):
  self.readFile.close()
  self.writeFile.close()

 def _asyncRead(self):
  while True:
   l = self.readFile.readline()
   self.q.put(l)
   if l == '':
    break
   if self.log:
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
  self.writeFile.write(data + '\n')
  self.writeFile.flush()
