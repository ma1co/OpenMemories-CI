import os
import textwrap
import time

from . import TestCase
from runner import archive, emmc, qemu

class TestCXD90045(TestCase):
 MACHINE = 'cxd90045'
 EMMC_SIZE = 0x1000000

 MODEL = 'DSC-HX99'
 FIRMWARE_DIR = 'firmware/DSC-HX99'

 def readFirmwareFile(self, name):
  with open(os.path.join(self.FIRMWARE_DIR, name), 'rb') as f:
   return f.read()

 def prepareBootRom(self):
  return self.readFirmwareFile('bootrom')

 def prepareBootPartition(self, patchInitPower=False):
  boot = self.readFirmwareFile('boot')
  if patchInitPower:
   boot = boot[:0x87c4] + b'\0\0\0\0' + boot[0x87c8:]
  return boot

 def prepareUpdaterKernel(self):
  return archive.readFat(self.readFirmwareFile('nflasha1')).read('/boot/vmlinux.bin')

 def prepareUpdaterInitrd(self, shellOnly=False, patchUpdaterMain=False):
  initrd = archive.readCramfs(archive.readFat(self.readFirmwareFile('nflasha1')).read('/boot/initrd.img'))
  if shellOnly:
   initrd.write('/sbin/init', b'#!/bin/sh\nmount -t proc proc /proc\nwhile true; do sh; done\n')
  else:
   if patchUpdaterMain:
    initrd.write('/usr/bin/UdtrMain.sh', b'#!/bin/sh\n')
  return archive.writeCramfs(initrd)

 def prepareFlash1(self, kernel=None, initrd=None, patchConsoleEnable=False):
  nflasha1 = archive.readFat(self.readFirmwareFile('nflasha1'))
  if kernel:
   nflasha1.write('/boot/vmlinux.bin', kernel)
  if initrd:
   nflasha1.write('/boot/initrd.img', initrd)
  if patchConsoleEnable:
   nflasha1.patch('/boot/kemco.txt', lambda d: d.replace(b'amba2.console=0', b'amba2.console=1'))
  return archive.writeFat(nflasha1, 0x800000)

 def prepareFlash2(self, updaterMode=False):
  nflasha2 = archive.Archive()
  if updaterMode:
   nflasha2.write('/updater/mode', b'')
  return archive.writeFat(nflasha2, 0x400000)

 def prepareEmmc(self, boot=b'', partitions=[]):
  return emmc.writeEmmc(boot, archive.writeFlash(partitions), self.EMMC_SIZE)

 def prepareQemuArgs(self, bootRom=None, kernel=None, initrd=None, emmc=None, patchLoader2LogLevel=False):
  args = ['-icount', 'shift=2']

  # Power IC
  args += ['-device', 'bionz_hibari,id=hibari,bus=/sio3', '-connect-gpio', 'odev=gpio5,onum=14,idev=hibari,iname=ssi-gpio-cs']
  args += ['-device', 'bionz_piroshki,id=piroshki,bus=/sio1', '-connect-gpio', 'odev=gpio5,onum=6,idev=piroshki,iname=ssi-gpio-cs']

  if bootRom:
   args += ['-bios', bootRom]
  if kernel:
   args += ['-kernel', kernel]
  if initrd:
   args += ['-initrd', initrd]
  if emmc:
   args += ['-drive', 'file=%s,if=mtd,format=raw' % emmc]
  if patchLoader2LogLevel:
   args += ['-device', 'rom-loader,name=loader2-loglevel,addr=0xfe188000,data=7,data-len=4']
  return args

 def checkShell(self, func, checkCpuinfo=True, checkVersion=True):
  if checkCpuinfo:
   cpuinfo = func('cat /proc/cpuinfo')
   self.log.info('/proc/cpuinfo:\n%s', textwrap.indent(cpuinfo, '  '))
   if 'Hardware\t: ARM-CXD900X0\n' not in cpuinfo:
    raise Exception('Invalid cpuinfo')

  if checkVersion:
   version = func('cat /proc/version')
   self.log.info('/proc/version:\n%s', textwrap.indent(version, '  '))
   if not version.startswith('Linux version 3.0'):
    raise Exception('Invalid version')


 def testUpdaterKernel(self):
  files = {
   'vmlinux.bin': self.prepareUpdaterKernel(),
   'initrd.img': self.prepareUpdaterInitrd(shellOnly=True),
  }
  args = self.prepareQemuArgs(kernel='vmlinux.bin', initrd='initrd.img')

  with qemu.QemuRunner(self.MACHINE, args, files) as q:
   q.expectLine(lambda l: l.startswith('BusyBox'))
   time.sleep(.5)
   self.checkShell(q.execShellCommand)


 def testLoader2Updater(self):
  files = {
   'emmc.dat': self.prepareEmmc(
    boot=self.prepareBootPartition(patchInitPower=True),
    partitions=[
     self.prepareFlash1(
      kernel=self.prepareUpdaterKernel(),
      initrd=self.prepareUpdaterInitrd(patchUpdaterMain=True),
      patchConsoleEnable=True,
     ),
     self.prepareFlash2(updaterMode=True),
    ],
   ),
  }
  args = self.prepareQemuArgs(emmc='emmc.dat', patchLoader2LogLevel=True)

  with qemu.QemuRunner(self.MACHINE, args, files) as q:
   q.expectLine(lambda l: l.startswith('Loader2'))
   q.expectLine(lambda l: l.startswith('LDR:Jump to kernel'))
   q.expectLine(lambda l: l.startswith('BusyBox'))
   time.sleep(.5)
   self.checkShell(q.execShellCommand)


 def testLoader1(self):
  files = {
   'rom.dat': self.prepareBootRom(),
   'emmc.dat': self.prepareEmmc(
    boot=self.prepareBootPartition(patchInitPower=True),
    partitions=[
     self.prepareFlash1(
      kernel=self.prepareUpdaterKernel(),
      initrd=self.prepareUpdaterInitrd(patchUpdaterMain=True),
      patchConsoleEnable=True,
     ),
     self.prepareFlash2(updaterMode=True),
    ],
   ),
  }
  args = self.prepareQemuArgs(bootRom='rom.dat', emmc='emmc.dat', patchLoader2LogLevel=True)

  with qemu.QemuRunner(self.MACHINE, args, files) as q:
   q.expectLine(lambda l: l.startswith('Astra Loader1'))
   q.expectLine(lambda l: l.startswith('Loader2'))
   q.expectLine(lambda l: l.startswith('LDR:Jump to kernel'))
   q.expectLine(lambda l: l.startswith('BusyBox'))
   time.sleep(.5)
   self.checkShell(q.execShellCommand)
