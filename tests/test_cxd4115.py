import os
import textwrap
import time

from . import TestCase
from runner import archive, kernel_patch, onenand, qemu, usb, zimage

class TestCXD4115(TestCase):
 MACHINE = 'cxd4115'
 NAND_SIZE = 0x4000000

 MODEL = 'NEX-3'
 FIRMWARE_DIR = 'firmware/NEX-3'

 def readFirmwareFile(self, name):
  with open(os.path.join(self.FIRMWARE_DIR, name), 'rb') as f:
   return f.read()

 def prepareBootRom(self):
  return self.readFirmwareFile('bootrom')

 def prepareBootPartition(self):
  return self.readFirmwareFile('boot')

 def prepareUpdaterKernel(self, patchConsoleEnable=False):
  kernel = archive.readFat(self.readFirmwareFile('nflasha1')).read('/boot/vmlinux')
  if patchConsoleEnable:
   kernel = zimage.patchZimage(kernel, kernel_patch.patchConsoleEnable)
  return kernel

 def prepareUpdaterInitrd(self, shellOnly=False, patchUpdaterLogLevel=False, patchCasCmd=False):
  initrd = archive.readCramfs(archive.readFat(self.readFirmwareFile('nflasha1')).read('/boot/initrd.img'))
  if shellOnly:
   initrd.write('/sbin/init', b'#!/bin/sh\nmount -t proc proc /proc\nwhile true; do sh; done\n')
  else:
   if patchUpdaterLogLevel:
    initrd.patch('/root/UdtrMain.sh', lambda d: d.replace(b'#!/bin/sh\n', b'#!/bin/sh\ndebugio 5\n'))
   if patchCasCmd:
    initrd.patch('/root/UdtrMain.sh', lambda d: d.replace(b'uc_cascmd -m ca -c continu', b'true'))
  return archive.writeCramfs(initrd)

 def prepareFlash1(self, kernel=None, initrd=None):
  nflasha1 = archive.readFat(self.readFirmwareFile('nflasha1'))
  if kernel:
   nflasha1.write('/boot/vmlinux', kernel)
  if initrd:
   nflasha1.write('/boot/initrd.img', initrd)
  return archive.writeFat(nflasha1, 0x400000)

 def prepareFlash2(self, updaterMode=False):
  nflasha2 = archive.Archive()
  nflasha2.write('/updater/dat4', b'\x00\x01')
  if updaterMode:
   nflasha2.write('/updater/mode', b'')
  return archive.writeFat(nflasha2, 0x400000)

 def prepareNand(self, boot=b'', partitions=[]):
  return onenand.writeNand(boot, archive.writeFlash(partitions), self.NAND_SIZE)

 def prepareQemuArgs(self, bootRom=None, kernel=None, initrd=None, nand=None):
  args = ['-icount', 'shift=4']

  # Power IC
  args += ['-device', 'bionz_ca,id=ca,bus=/sio3', '-connect-gpio', 'odev=ca,oname=req,idev=gpio0,inum=15']

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
   if 'Hardware\t: ARM-CXD4115\n' not in cpuinfo:
    raise Exception('Invalid cpuinfo')

  if checkVersion:
   version = func('cat /proc/version')
   self.log.info('/proc/version:\n%s', textwrap.indent(version, '  '))
   if not version.startswith('Linux version 2.6'):
    raise Exception('Invalid version')


 def testUpdaterKernel(self):
  files = {
   'vmlinux.bin': self.prepareUpdaterKernel(patchConsoleEnable=True),
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
      kernel=self.prepareUpdaterKernel(patchConsoleEnable=True),
      initrd=self.prepareUpdaterInitrd(shellOnly=True),
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


 def testUpdaterUsb(self):
  files = {
   'rom.dat': self.prepareBootRom(),
   'nand.dat': self.prepareNand(
    boot=self.prepareBootPartition(),
    partitions=[
     self.prepareFlash1(
      kernel=self.prepareUpdaterKernel(patchConsoleEnable=True),
      initrd=self.prepareUpdaterInitrd(patchUpdaterLogLevel=True, patchCasCmd=True),
     ),
     self.prepareFlash2(updaterMode=True),
    ],
   ),
  }
  args = self.prepareQemuArgs(bootRom='rom.dat', nand='nand.dat')

  with qemu.QemuRunner(self.MACHINE, args, files) as q:
   q.expectLine(lambda l: l.startswith('BusyBox'))
   q.expectLine(lambda l: '"DONE onEvent(COMP_START or COMP_STOP)"' in l)

   with usb.PmcaRunner('updatershell', ['-d', 'qemu', '-m', self.MODEL]) as pmca:
    pmca.expectLine(lambda l: l == 'Welcome to the USB debug shell.')
    self.checkShell(lambda c: pmca.execUpdaterShellCommand('shell %s' % c))
    pmca.writeLine('exit')
    pmca.expectLine(lambda l: l == 'Done')
