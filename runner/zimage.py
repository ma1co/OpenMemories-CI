import zlib

def _unpack(data):
 offset = data.find(b'\x1f\x8b\x08\x00')
 decomp = zlib.decompressobj(-zlib.MAX_WBITS)
 kernel = decomp.decompress(data[offset+10:])
 size = len(data) - offset - len(decomp.unused_data) + 8
 return offset, size, kernel

def unpackZimage(data):
 offset, size, kernel = _unpack(data)
 return kernel
