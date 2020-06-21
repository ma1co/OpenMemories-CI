import io

BOOT_SIZE = 0x40000

def writeEmmc(boot, data, size):
 f = io.BytesIO()
 f.write(boot)
 f.write(b'\0' * (BOOT_SIZE - f.tell()))
 f.write(b'\0' * BOOT_SIZE)
 f.write(data)
 f.write(b'\xff' * (BOOT_SIZE + size - f.tell()))
 return f.getvalue()
