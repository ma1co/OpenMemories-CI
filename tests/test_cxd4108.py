import os
import textwrap
import time

from . import TestCase
from runner import archive, onenand, qemu, zimage

class TestCXD4108(TestCase):
 MACHINE = 'cxd4108'
 NAND_SIZE = 0x4000000

 MODEL = 'DSC-W90'
 FIRMWARE_DIR = 'firmware/DSC-W90'

 def readFirmwareFile(self, name):
  with open(os.path.join(self.FIRMWARE_DIR, name), 'rb') as f:
   return f.read()

 def prepareBootPartition(self, patchInitPower=False):
  boot = self.readFirmwareFile('boot')
  if patchInitPower:
   boot = boot[:0x40020] + b'\0\0\0\0' + boot[0x40024:]
  return boot

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

 def prepareFlash1(self, kernel=None, initrd=None):
  nflasha1 = archive.readFat(self.readFirmwareFile('nflasha1'))
  if kernel:
   nflasha1.write('/boot/vmlinux', kernel)
  if initrd:
   nflasha1.write('/boot/initrd.img', initrd)
  return archive.writeFat(nflasha1, 0x200000)

 def prepareFlash2(self, updaterMode=False):
  nflasha2 = archive.Archive()
  if updaterMode:
   nflasha2.write('/updater/mode', b'')
  return archive.writeFat(nflasha2, 0x200000)

 def prepareNand(self, boot=b'', partitions=[]):
  return onenand.writeNand(boot, archive.writeFlash(partitions), self.NAND_SIZE)

 def prepareQemuArgs(self, kernel=None, initrd=None, nand=None):
  args = ['-icount', 'shift=4']
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
    boot=self.prepareBootPartition(patchInitPower=True),
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
