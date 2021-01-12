import io
import stat

from fwtool import mbr
from fwtool.archive import cramfs, fat, UnixFile
from fwtool.sony import flash

class Archive:
 def __init__(self, files={}):
  self.files = {f.path: f for f in files}

 def read(self, path):
  c = self.files[path].contents
  c.seek(0)
  return c.read()

 def write(self, path, data):
  f = self.files.get(path, UnixFile(path=path, size=-1, mtime=0, mode=stat.S_IFREG | 0o775, uid=0, gid=0, contents=None))
  self.files[path] = f._replace(contents=io.BytesIO(data))

 def patch(self, path, func):
  self.write(path, func(self.read(path)))

def readFat(data):
 return Archive(fat.readFat(io.BytesIO(data)))

def writeFat(archive, size):
 f = io.BytesIO()
 fat.writeFat(archive.files.values(), size, f)
 return f.getvalue()

def readCramfs(data):
 return Archive(cramfs.readCramfs(io.BytesIO(data)))

def writeCramfs(archive):
 f = io.BytesIO()
 cramfs.writeCramfs(archive.files.values(), f)
 return f.getvalue()

def writeFlash(partitions):
 f = io.BytesIO()
 flash.writePartitions([io.BytesIO(p) for p in partitions], f)
 return f.getvalue()

def writeMbr(partitions):
 f = io.BytesIO()
 mbr.writeMbr([io.BytesIO(p) for p in partitions], f)
 return f.getvalue()
