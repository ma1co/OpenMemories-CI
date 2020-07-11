import io

from .util import *

SECTOR_SIZE = 0x200
SPARE_SIZE = 0x10
SECTORS_PER_BLOCK = 0x100

def writeNand(boot, data, size):
 numBlocks = size // SECTOR_SIZE // SECTORS_PER_BLOCK
 bootBlocks = (len(boot) + SECTORS_PER_BLOCK * SECTOR_SIZE - 1) // SECTOR_SIZE // SECTORS_PER_BLOCK
 dataBlocks = (len(data) + SECTORS_PER_BLOCK * SECTOR_SIZE - 1) // SECTOR_SIZE // SECTORS_PER_BLOCK

 f = io.BytesIO()
 f.write(boot)
 f.write(b'\xff' * (bootBlocks * SECTORS_PER_BLOCK * SECTOR_SIZE - f.tell()))
 f.write(data)
 f.write(b'\xff' * (numBlocks * SECTORS_PER_BLOCK * SECTOR_SIZE - f.tell()))

 for i in range(numBlocks):
  for j in range(SECTORS_PER_BLOCK):
   marker = 0xffff
   bootMarker = 0xffff
   if i < bootBlocks:
    if i == 0 and j == 0:
     bootMarker = 0x5555
   elif i < bootBlocks + dataBlocks:
    if j == 0 or j == 1:
     marker = 0
    elif j == 2:
     marker = i - bootBlocks
   f.write(b'\xff\xff' + dump16le(marker) + b'\xff' * (SPARE_SIZE - 6) + dump16le(bootMarker))

 return f.getvalue()
