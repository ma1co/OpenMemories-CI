import os
import textwrap
import time
import unittest

from . import TestCase
from runner import archive, kernel_patch, onenand, qemu, zimage

class TestCXD4108(TestCase):
 MACHINE = 'cxd4108'
 NAND_SIZE = 0x4000000

 MODEL = 'DSC-W90'
 FIRMWARE_DIR = 'firmware/DSC-W90'

 def readFirmwareFile(self, name):
  with open(os.path.join(self.FIRMWARE_DIR, name), 'rb') as f:
   return f.read()

 def prepareBootRom(self):
  return self.readFirmwareFile('bootrom')

 def prepareBootPartition(self):
  return self.readFirmwareFile('boot')

 def prepareUpdaterKernel(self, unpackZimage=False):
  kernel = archive.readFat(self.readFirmwareFile('nflasha1')).read('/boot/vmlinux')
  if unpackZimage:
   kernel = zimage.unpackZimage(kernel)
  return kernel

 def prepareUpdaterInitrd(self, shellOnly=False):
  initrd = archive.readCramfs(archive.readFat(self.readFirmwareFile('nflasha1')).read('/boot/initrd.img'))
  if shellOnly:
   initrd.write('/sbin/init', b'#!/bin/sh\nmount -t proc proc /proc\nwhile true; do sh; done\n')
  return archive.writeCramfs(initrd)

 def prepareMainKernel(self, patchConsoleEnable=False):
  kernel = archive.readFat(self.readFirmwareFile('nflasha3')).read('/boot/vmlinux')
  if patchConsoleEnable:
   kernel = kernel_patch.patchConsoleEnable(kernel)
  return kernel

 def prepareFlash1(self, kernel=None, initrd=None):
  nflasha1 = archive.readFat(self.readFirmwareFile('nflasha1'))
  if kernel:
   nflasha1.write('/boot/vmlinux', kernel)
  if initrd:
   nflasha1.write('/boot/initrd.img', initrd)
  return archive.writeFat(nflasha1, 0x200000)

 def prepareFlash2(self, readSettings=False, updaterMode=False, playbackMode=False):
  nflasha2 = archive.Archive()
  if readSettings:
   settings = archive.readFat(self.readFirmwareFile('nflasha2'))
   for fn in settings.files:
    if fn.startswith('/backup/') or fn.startswith('/factory/'):
     nflasha2.write(fn, settings.read(fn))
  if updaterMode:
   nflasha2.write('/updater/mode', b'')
  if playbackMode:
   nflasha2.patch('/factory/Areg.bin', lambda d: d[:0x100] + b'\x84' + d[0x101:])
  return archive.writeFat(nflasha2, 0x180000)

 def prepareFlash3(self, kernel=None, rootfs=None):
  nflasha3 = archive.readFat(self.readFirmwareFile('nflasha3'))
  if kernel:
   nflasha3.write('/boot/vmlinux', kernel)
  if rootfs:
   nflasha3.write('/boot/rootfs.img', rootfs)
  return archive.writeFat(nflasha3, 0x400000)

 def prepareFlash5(self):
  return self.readFirmwareFile('nflasha5')

 def prepareFlash6(self):
  return self.readFirmwareFile('nflasha6')

 def prepareFlash11(self):
  return archive.writeMbr([archive.writeFat(archive.Archive(), 0x100000)])

 def prepareNand(self, boot=b'', partitions=[]):
  return onenand.writeNand(boot, archive.writeFlash(partitions), self.NAND_SIZE, 0x100000)

 def prepareQemuArgs(self, bootRom=None, kernel=None, initrd=None, nand=None):
  args = ['-icount', 'shift=4']

  # Power IC
  args += ['-device', 'bionz_mb89083,id=mb89083,bus=/sio0', '-connect-gpio', 'odev=gpio1,onum=1,idev=mb89083,iname=ssi-gpio-cs']

  # Battery auth
  args += ['-device', 'bionz_upd79f,id=upd79f,bus=/sio1', '-connect-gpio', 'odev=gpios,onum=4,idev=upd79f,iname=ssi-gpio-cs']

  if bootRom:
   args += ['-bios', bootRom]
  if kernel:
   args += ['-kernel', kernel]
  if initrd:
   args += ['-initrd', initrd]
  if nand:
   args += ['-drive', 'file=%s,if=mtd,format=raw' % nand]
  return args

 def checkShell(self, func, checkCpuinfo=True, checkVersion=True):
  if checkCpuinfo:
   cpuinfo = func('cat /proc/cpuinfo')
   self.log.info('/proc/cpuinfo:\n%s', textwrap.indent(cpuinfo, '  '))
   if 'Hardware\t: ARM-CXD4108\n' not in cpuinfo:
    raise Exception('Invalid cpuinfo')

  if checkVersion:
   version = func('cat /proc/version')
   self.log.info('/proc/version:\n%s', textwrap.indent(version, '  '))
   if not version.startswith('Linux version 2.6'):
    raise Exception('Invalid version')


 def testUpdaterKernel(self):
  files = {
   'vmlinux.bin': self.prepareUpdaterKernel(unpackZimage=True),
   'initrd.img': self.prepareUpdaterInitrd(shellOnly=True),
  }
  args = self.prepareQemuArgs(kernel='vmlinux.bin', initrd='initrd.img')

  with qemu.QemuRunner(self.MACHINE, args, files) as q:
   q.expectLine(lambda l: l.startswith('BusyBox'))
   time.sleep(.5)
   self.checkShell(q.execShellCommand)


 def testLoader2Updater(self):
  files = {
   'nand.dat': self.prepareNand(
    boot=self.prepareBootPartition(),
    partitions=[
     self.prepareFlash1(
      kernel=self.prepareUpdaterKernel(),
      initrd=self.prepareUpdaterInitrd(),
     ),
     self.prepareFlash2(updaterMode=True),
    ],
   ),
  }
  args = self.prepareQemuArgs(nand='nand.dat')

  with qemu.QemuRunner(self.MACHINE, args, files) as q:
   q.expectLine(lambda l: l.startswith('BusyBox'))
   time.sleep(.5)
   self.checkShell(q.execShellCommand)


 def testLoader1Updater(self):
  files = {
   'rom.dat': self.prepareBootRom(),
   'nand.dat': self.prepareNand(
    boot=self.prepareBootPartition(),
    partitions=[
     self.prepareFlash1(
      kernel=self.prepareUpdaterKernel(),
      initrd=self.prepareUpdaterInitrd(),
     ),
     self.prepareFlash2(updaterMode=True),
    ],
   ),
  }
  args = self.prepareQemuArgs(bootRom='rom.dat', nand='nand.dat')

  with qemu.QemuRunner(self.MACHINE, args, files) as q:
   q.expectLine(lambda l: l.startswith('BusyBox'))
   time.sleep(.5)
   self.checkShell(q.execShellCommand)


 @unittest.skip
 def testLoader1Main(self):
  files = {
   'rom.dat': self.prepareBootRom(),
   'nand.dat': self.prepareNand(
    boot=self.prepareBootPartition(),
    partitions=[
     b'',
     self.prepareFlash2(readSettings=True, playbackMode=True),
     self.prepareFlash3(kernel=self.prepareMainKernel(patchConsoleEnable=True)),
     b'',
     self.prepareFlash5(),
     self.prepareFlash6(),
     b'',
     b'',
     b'',
     b'',
     self.prepareFlash11(),
    ],
   ),
  }
  args = self.prepareQemuArgs(bootRom='rom.dat', nand='nand.dat')

  with qemu.QemuRunner(self.MACHINE, args, files) as q:
   q.expectLine(lambda l: l.startswith('BusyBox'))
   time.sleep(.5)
   self.checkShell(q.execShellCommand)
