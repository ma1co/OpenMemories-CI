import zlib
import zopfli.gzip

def _unpack(data):
 offset = data.find(b'\x1f\x8b\x08\x00')
 decomp = zlib.decompressobj(wbits=31)
 kernel = decomp.decompress(data[offset:]) + decomp.flush()
 size = len(data) - offset - len(decomp.unused_data)
 return offset, size, kernel

def _pack(data):
 return zopfli.gzip.compress(data, numiterations=1, blocksplitting=False)

def unpackZimage(data):
 offset, size, kernel = _unpack(data)
 return kernel

def patchZimage(data, func):
 offset, size, kernel = _unpack(data)
 compressed = _pack(func(kernel))
 if len(compressed) > size:
  raise Exception('Compressed kernel does not fit')
 return data[:offset] + compressed.ljust(size, b'\0') + data[offset+size:]
