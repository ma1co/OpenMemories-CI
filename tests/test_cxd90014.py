import os
import textwrap
import time

from . import TestCase
from runner import archive, nand, qemu, usb, zimage

class TestCXD90014(TestCase):
 MACHINE = 'cxd90014'
 NAND_SIZE = 0x4000000

 MODEL = 'DSC-RX100M5'
 FIRMWARE_DIR = 'firmware/DSC-RX100M5'

 def readFirmwareFile(self, name):
  with open(os.path.join(self.FIRMWARE_DIR, name), 'rb') as f:
   return f.read()

 def prepareBootRom(self):
  return self.readFirmwareFile('bootrom')

 def prepareSafeBootPartition(self):
  return nand.writeNandBlock0(self.NAND_SIZE) + self.readFirmwareFile('boot1')

 def prepareNormalBootPartition(self, patchInitPower=False):
  b5 = self.readFirmwareFile('boot5')
  if patchInitPower:
   b5 = b5[:0xccf0] + b'\0\0\0\0' + b5[0xccf4:]
   b5 = b5[:0xd1a4] + b'\0\0\0\0' + b5[0xd1a8:]
  return 3 * 0x40 * 0x1000 * b'\xff' + b5

 def prepareUpdaterKernel(self, unpackZimage=False, patchConsoleEnable=False):
  kernel = archive.readFat(self.readFirmwareFile('nflasha1')).read('/boot/vmlinux.bin')
  if unpackZimage:
   kernel = zimage.unpackZimage(kernel)
   if patchConsoleEnable:
    kernel = kernel.replace(b'amba2.console=0', b'amba2.console=1')
  return kernel

 def prepareUpdaterInitrd(self, shellOnly=False):
  initrd = archive.readCramfs(archive.readFat(self.readFirmwareFile('nflasha1')).read('/boot/initrd.img'))
  if shellOnly:
   initrd.write('/sbin/init', b'#!/bin/sh\nmount -t proc proc /proc\nwhile true; do sh; done\n')
  return archive.writeCramfs(initrd)

 def prepareFlash1(self, kernel=None, initrd=None, patchKernelLoadaddr=False):
  nflasha1 = archive.readFat(self.readFirmwareFile('nflasha1'))
  if kernel:
   nflasha1.write('/boot/vmlinux.bin', kernel)
  if initrd:
   nflasha1.write('/boot/initrd.img', initrd)
  if patchKernelLoadaddr:
   nflasha1.patch('/boot/loadaddr.txt', lambda d: d.replace(b'0x81528000', b'0x80038000'))
  return archive.writeFat(nflasha1, 0x800000)

 def prepareFlash2(self, updaterMode=False, patchBackupWriteComp=False):
  nflasha2 = archive.Archive()
  nflasha2.write('/Backup.bin', self.readFirmwareFile('Backup.bin'))
  nflasha2.write('/DmmConfig.bin', self.readFirmwareFile('DmmConfig.bin'))
  nflasha2.write('/ulogio.bin', self.readFirmwareFile('ulogio.bin'))
  nflasha2.write('/updater/dat4', b'\x00\x01')
  if updaterMode:
   nflasha2.write('/updater/mode', b'')
  if patchBackupWriteComp:
   nflasha2.patch('/Backup.bin', lambda d: d[:8] + b'\x01\0\0\0' + d[12:])
  return archive.writeFat(nflasha2, 0x400000)

 def prepareNand(self, safeBoot=b'', normalBoot=b'', partitions=[]):
  return nand.writeNand(safeBoot, normalBoot, archive.writeFlash(partitions), self.NAND_SIZE)

 def prepareQemuArgs(self, bootRom=None, kernel=None, initrd=None, nand=None, patchLoader2LogLevel=False):
  args = ['-icount', 'shift=2']
  if bootRom:
   args += ['-bios', bootRom]
  if kernel:
   args += ['-kernel', kernel]
  if initrd:
   args += ['-initrd', initrd]
  if nand:
   args += ['-drive', 'file=%s,if=mtd,format=raw' % nand]
  if patchLoader2LogLevel:
   args += ['-device', 'rom-loader,name=loader2-loglevel,addr=0xc0060000,data=7,data-len=4']
  return args

 def checkShell(self, func, checkCpuinfo=True, checkVersion=True):
  if checkCpuinfo:
   cpuinfo = func('cat /proc/cpuinfo')
   self.log.info('/proc/cpuinfo:\n%s', textwrap.indent(cpuinfo, '  '))
   if 'Hardware\t: ARM-CXD90014\n' not in cpuinfo:
    raise Exception('Invalid cpuinfo')

  if checkVersion:
   version = func('cat /proc/version')
   self.log.info('/proc/version:\n%s', textwrap.indent(version, '  '))
   if not version.startswith('Linux version 3.0'):
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


 def testLoader2Updater(self):
  files = {
   'nand.dat': self.prepareNand(
    safeBoot=self.prepareSafeBootPartition(),
    normalBoot=self.prepareNormalBootPartition(patchInitPower=True),
    partitions=[
     self.prepareFlash1(
      kernel=self.prepareUpdaterKernel(unpackZimage=True, patchConsoleEnable=True),
      initrd=self.prepareUpdaterInitrd(shellOnly=True),
      patchKernelLoadaddr=True,
     ),
     self.prepareFlash2(updaterMode=True),
    ],
   ),
  }
  args = self.prepareQemuArgs(nand='nand.dat', patchLoader2LogLevel=True)

  with qemu.QemuRunner(self.MACHINE, args, files) as q:
   q.expectLine(lambda l: l.startswith('Loader2'))
   q.expectLine(lambda l: l.startswith('Loader3'))
   q.expectLine(lambda l: l.startswith('LDR:Jump to kernel'))
   q.expectLine(lambda l: l.startswith('BusyBox'))
   time.sleep(.5)
   self.checkShell(q.execShellCommand)


 def testUpdaterUsb(self):
  files = {
   'rom.dat': self.prepareBootRom(),
   'nand.dat': self.prepareNand(
    safeBoot=self.prepareSafeBootPartition(),
    normalBoot=self.prepareNormalBootPartition(patchInitPower=True),
    partitions=[
     self.prepareFlash1(
      kernel=self.prepareUpdaterKernel(unpackZimage=True, patchConsoleEnable=True),
      initrd=self.prepareUpdaterInitrd(),
      patchKernelLoadaddr=True,
     ),
     self.prepareFlash2(updaterMode=True, patchBackupWriteComp=True),
    ],
   ),
  }
  args = self.prepareQemuArgs(bootRom='rom.dat', nand='nand.dat', patchLoader2LogLevel=True)

  with qemu.QemuRunner(self.MACHINE, args, files) as q:
   q.expectLine(lambda l: l.startswith('Musashi Loader1'))
   q.expectLine(lambda l: l.startswith('Loader2'))
   q.expectLine(lambda l: l.startswith('Loader3'))
   q.expectLine(lambda l: l.startswith('LDR:Jump to kernel'))
   q.expectLine(lambda l: l.startswith('BusyBox'))
   q.expectLine(lambda l: l.endswith('"DONE onEvent(COMP_START or COMP_STOP)"'))

   with usb.PmcaRunner('updatershell', ['-d', 'qemu', '-m', self.MODEL]) as pmca:
    pmca.expectLine(lambda l: l == 'Welcome to the USB debug shell.')
    self.checkShell(lambda c: pmca.execUpdaterShellCommand('shell %s' % c))
    pmca.writeLine('exit')
    pmca.expectLine(lambda l: l == '>Done')

   q.expectLine(lambda l: l == 'User Update OK')
