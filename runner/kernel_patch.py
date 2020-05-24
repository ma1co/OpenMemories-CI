from capstone import *
from capstone.arm import *

from .util import *

def getKernelBase(kernel):
 md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
 md.detail = True

 # Analyze kernel startup entry point
 prev = None
 for i in md.disasm(kernel, 0):
  if i.id == ARM_INS_MOV and i.operands[0].reg == ARM_REG_R10 and i.operands[1].reg == ARM_REG_R5:
   if prev.id != ARM_INS_BL:
    raise Exception('Cannot find branch to __lookup_processor_type')
   off_lookup_processor_type = prev.operands[0].imm
   break
  prev = i

 # Analyze __lookup_processor_type
 i = next(md.disasm(kernel[off_lookup_processor_type:], 0))
 if i.id != ARM_INS_ADD or i.operands[1].reg != ARM_REG_PC:
  raise Exception('Cannot find add instruction in __lookup_processor_type')
 off_lookup_processor_type_data = off_lookup_processor_type + i.operands[2].imm + 8

 # Analyze __lookup_processor_type_data
 off = parse32le(kernel[off_lookup_processor_type_data:off_lookup_processor_type_data+4])
 if (off & 0xfff) != (off_lookup_processor_type_data & 0xfff):
  raise Exception('Invalid __lookup_processor_type_data')
 return off - off_lookup_processor_type_data


def patchConsoleEnable(kernel):
 md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
 md.detail = True

 kernel_base = getKernelBase(kernel)

 # Find struct console amba_console:
 for i in findall(b'ttyAM\0', kernel):
  i += 8
  while kernel[i:i+4] == 4*b'\0':
   i += 4
  off_pl011_console_write = parse32le(kernel[i:i+4])
  off_uart_console_device = parse32le(kernel[i+8:i+12])
  off_pl011_console_unblank = parse32le(kernel[i+12:i+16])
  off_pl011_console_setup = parse32le(kernel[i+16:i+20])
  if (i % 4 == 0 and
      off_pl011_console_write > kernel_base and off_pl011_console_write % 4 == 0 and
      off_uart_console_device > kernel_base and off_uart_console_device % 4 == 0 and
      off_pl011_console_setup > kernel_base and off_pl011_console_setup % 4 == 0 and
      off_pl011_console_unblank == 0):
   break
 else:
  raise Exception('Cannot find struct console amba_console')

 # Analyze pl011_console_setup
 bblock = 0
 stores = []
 for i in md.disasm(kernel[off_pl011_console_setup-kernel_base:], off_pl011_console_setup):
  if i.id in [ARM_INS_B, ARM_INS_BL]:
   bblock += 1
   if bblock > 1:
    break
  elif bblock == 1 and i.id == ARM_INS_STR:
   stores.append(i)
 if len(stores) not in [1, 2]:
  raise Exception('Cannot analyze pl011_console_setup')
 store_txrx_enable = stores[1] if len(stores) == 2 else None

 # Patch txrx_enable
 if store_txrx_enable:
  off = store_txrx_enable.address - kernel_base
  size = store_txrx_enable.size
  kernel = kernel[:off] + b'\0' * size + kernel[off+size:]
 return kernel
