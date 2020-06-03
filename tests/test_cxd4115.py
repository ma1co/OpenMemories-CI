import os
import textwrap
import time

from . import TestCase
from runner import archive, kernel_patch, onenand, qemu, usb, zimage

class TestCXD4115(TestCase):
 MACHINE = 'cxd4115'
 NAND_SIZE = 0x8000000

 MODEL = 'NEX-3'
 FIRMWARE_DIR = 'firmware/NEX-3'

 def readFirmwareFile(self, name):
  with open(os.path.join(self.FIRMWARE_DIR, name), 'rb') as f:
   return f.read()

 def prepareUpdaterKernel(self, unpackZimage=False, patchConsoleEnable=False):
  kernel = archive.readFat(self.readFirmwareFile('nflasha1')).read('/boot/vmlinux')
  if unpackZimage:
   kernel = zimage.unpackZimage(kernel)
   if patchConsoleEnable:
    kernel = kernel_patch.patchConsoleEnable(kernel)
  return kernel

 def prepareUpdaterInitrd(self, shellOnly=False, patchValidBoot=False, patchUpdaterLogLevel=False, patchCasCmd=False):
  initrd = archive.readCramfs(archive.readFat(self.readFirmwareFile('nflasha1')).read('/boot/initrd.img'))
  if shellOnly:
   initrd.write('/sbin/init', b'#!/bin/sh\nmount -t proc proc /proc\nwhile true; do sh; done\n')
  else:
   if patchValidBoot:
    initrd.write('/root/is_valid_boot.sh', b'#!/bin/sh\nexit 0\n')
   if patchUpdaterLogLevel:
    initrd.patch('/root/UdtrMain.sh', lambda d: d.replace(b'#!/bin/sh\n', b'#!/bin/sh\ndebugio 5\n'))
   if patchCasCmd:
    initrd.patch('/root/UdtrMain.sh', lambda d: d.replace(b'uc_cascmd -m ca -c continu', b'true'))
  return archive.writeCramfs(initrd)

 def prepareFlash1(self):
  return self.readFirmwareFile('nflasha1')

 def prepareFlash2(self):
  nflasha2 = archive.Archive()
  nflasha2.write('/updater/dat4', b'\x00\x01')
  return archive.writeFat(nflasha2, 0x400000)

 def prepareNand(self, partitions=[]):
  return onenand.writeNand(b'', archive.writeFlash(partitions), self.NAND_SIZE)

 def prepareQemuArgs(self, kernel=None, initrd=None, nand=None):
  args = []
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
   if 'Hardware\t: ARM-CXD4115\n' not in cpuinfo:
    raise Exception('Invalid cpuinfo')

  if checkVersion:
   version = func('cat /proc/version')
   self.log.info('/proc/version:\n%s', textwrap.indent(version, '  '))
   if not version.startswith('Linux version 2.6'):
    raise Exception('Invalid version')


 def testUpdaterKernel(self):
  files = {
   'vmlinux.bin': self.prepareUpdaterKernel(unpackZimage=True, patchConsoleEnable=True),
   'initrd.img': self.prepareUpdaterInitrd(shellOnly=True),
  }
  args = self.prepareQemuArgs(kernel='vmlinux.bin', initrd='initrd.img')

  with qemu.QemuRunner(self.MACHINE, args, files) as q:
   q.expectLine(lambda l: l.startswith('BusyBox'))
   time.sleep(.5)
   self.checkShell(q.execShellCommand)


 def testUpdaterUsb(self):
  files = {
   'vmlinux.bin': self.prepareUpdaterKernel(unpackZimage=True, patchConsoleEnable=True),
   'initrd.img': self.prepareUpdaterInitrd(patchValidBoot=True, patchUpdaterLogLevel=True, patchCasCmd=True),
   'nand.dat': self.prepareNand(partitions=[self.prepareFlash1(), self.prepareFlash2()]),
  }
  args = self.prepareQemuArgs(kernel='vmlinux.bin', initrd='initrd.img', nand='nand.dat')

  with qemu.QemuRunner(self.MACHINE, args, files) as q:
   q.expectLine(lambda l: '"DONE onEvent(COMP_START or COMP_STOP)"' in l)

   with usb.PmcaRunner('updatershell', ['-d', 'qemu', '-m', self.MODEL]) as pmca:
    pmca.expectLine(lambda l: l == 'Welcome to the USB debug shell.')
    self.checkShell(lambda c: pmca.execUpdaterShellCommand('shell %s' % c))
    pmca.writeLine('exit')
    pmca.expectLine(lambda l: l == 'Done')
