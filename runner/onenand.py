import io

from .util import *

SECTOR_SIZE = 0x200
SPARE_SIZE = 0x10
SECTORS_PER_BLOCK = 0x100

def writeNand(data, size):
 numBlocks = size // SECTOR_SIZE // SECTORS_PER_BLOCK

 f = io.BytesIO()
 f.write(data)
 f.write(b'\xff' * (numBlocks * SECTORS_PER_BLOCK * SECTOR_SIZE - f.tell()))

 for i in range(numBlocks):
  for j in range(SECTORS_PER_BLOCK):
   marker = {0: 0, 1: 0, 2: i}.get(j, 0xffff)
   f.write((b'\xff\xff' + dump16le(marker)).ljust(SPARE_SIZE, b'\xff'))

 return f.getvalue()
