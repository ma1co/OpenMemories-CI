import io
import math

from .util import *

PAGE_SIZE = 0x1000
SAFE_PAGE_SIZE = 0x600
PAGES_PER_BLOCK = 0x40
EXTRA_SIZE = 8

def writeNandBlock0(size):
 numBlocks = (size + PAGES_PER_BLOCK * PAGE_SIZE - 1) // PAGE_SIZE // PAGES_PER_BLOCK
 startBlock = 0
 loader2Block = 1
 block0Base = 0xc0000600
 numDies = 1
 numPlanes = 1
 maxBadBlocks = 0x2e

 bootRomParams = [0xffffffff] * 4
 bootRomParams[2] = int(math.log2(PAGES_PER_BLOCK))
 bootRomParams[3] = loader2Block

 muminInitParams = [0xffffffff] * 55
 muminInitParams[0] = startBlock
 muminInitParams[4] = block0Base + 0xf14
 muminInitParams[23] = numPlanes - 1
 muminInitParams[24] = PAGES_PER_BLOCK
 muminInitParams[26] = PAGE_SIZE
 muminInitParams[50] = numDies
 muminInitParams[51] = numBlocks
 muminInitParams[52] = maxBadBlocks

 f = io.BytesIO()
 f.write(b'\xff' * (0xc00 - f.tell()))
 f.write(b''.join(dump32le(i) for i in bootRomParams))
 f.write(b'\xff' * (0xf00 - f.tell()))
 f.write(b''.join(dump32le(i) for i in muminInitParams))
 f.write(b'\xff' * (PAGES_PER_BLOCK * SAFE_PAGE_SIZE - f.tell()))
 return f.getvalue()

def writeNand(safeBoot, normalBoot, data, size):
 numBlocks = (size + PAGES_PER_BLOCK * PAGE_SIZE - 1) // PAGE_SIZE // PAGES_PER_BLOCK
 safeBootBlocks = (len(safeBoot) + PAGES_PER_BLOCK * SAFE_PAGE_SIZE - 1) // SAFE_PAGE_SIZE // PAGES_PER_BLOCK
 normalBootBlocks = (len(normalBoot) + PAGES_PER_BLOCK * PAGE_SIZE - 1) // PAGE_SIZE // PAGES_PER_BLOCK
 bootBlocks = safeBootBlocks + normalBootBlocks
 dataBlocks = (len(data) + PAGES_PER_BLOCK * PAGE_SIZE - 1) // PAGE_SIZE // PAGES_PER_BLOCK

 f = io.BytesIO()
 f.write(b''.join(safeBoot[i:i+SAFE_PAGE_SIZE].ljust(PAGE_SIZE, b'\xff') for i in range(0, len(safeBoot), SAFE_PAGE_SIZE)))
 f.write(b'\xff' * (safeBootBlocks * PAGES_PER_BLOCK * PAGE_SIZE - f.tell()))
 f.write(normalBoot)
 f.write(b'\xff' * (bootBlocks * PAGES_PER_BLOCK * PAGE_SIZE - f.tell()))
 f.write(data)
 f.write(b'\xff' * (numBlocks * PAGES_PER_BLOCK * PAGE_SIZE - f.tell()))

 for i in range(numBlocks):
  for j in range(PAGES_PER_BLOCK):
   if bootBlocks <= i < bootBlocks + dataBlocks:
    f.write((b'\x46' + dump16be(i - bootBlocks) + dump16be(j)).ljust(EXTRA_SIZE, b'\0'))
   else:
    f.write(b'\xff' * EXTRA_SIZE)

 return f.getvalue()
