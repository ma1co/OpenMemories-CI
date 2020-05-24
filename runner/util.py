import struct

def parse32le(data):
 return struct.unpack('<I', data)[0]

def dump32le(value):
 return struct.pack('<I', value)

def parse16le(data):
 return struct.unpack('<H', data)[0]

def dump16le(value):
 return struct.pack('<H', value)

def parse8(data):
 return ord(data)

def dump8(value):
 return chr(value)

def findall(p, s):
 i = s.find(p)
 while i != -1:
  yield i
  i = s.find(p, i+1)
