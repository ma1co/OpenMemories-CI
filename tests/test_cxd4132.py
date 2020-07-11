import os
import textwrap
import time

from . import TestCase
from runner import archive, onenand, qemu, usb, zimage

class TestCXD4132(TestCase):
 MACHINE = 'cxd4132'
 NAND_SIZE = 0x4000000

 MODEL = 'DSC-QX10'
 FIRMWARE_DIR = 'firmware/DSC-QX10'

 def readFirmwareFile(self, name):
  with open(os.path.join(self.FIRMWARE_DIR, name), 'rb') as f:
   return f.read()

 def prepareBootRom(self):
  return self.readFirmwareFile('bootrom')

 def prepareBootPartition(self):
  return self.readFirmwareFile('boot')

 def prepareUpdaterKernel(self, unpackZimage=False, patchConsoleEnable=False):
  kernel = archive.readFat(self.readFirmwareFile('nflasha1')).read('/boot/vmlinux')
  if unpackZimage:
   kernel = zimage.unpackZimage(kernel)
   if patchConsoleEnable:
    kernel = kernel.replace(b'amba2.console=0', b'amba2.console=1')
  return kernel

 def prepareUpdaterInitrd(self, shellOnly=False, patchTee=False):
  initrd = archive.readCramfs(archive.readFat(self.readFirmwareFile('nflasha1')).read('/boot/initrd.img'))
  if shellOnly:
   initrd.write('/sbin/init', b'#!/bin/sh\nmount -t proc proc /proc\nwhile true; do sh; done\n')
  else:
   if patchTee:
    initrd.patch('/sbin/init', lambda d: d.replace(b' | tee -a $OUTPUT_LOG', b''))
  return archive.writeCramfs(initrd)

 def prepareFlash1(self, kernel=None, initrd=None, patchKernelLoadaddr=False):
  nflasha1 = archive.readFat(self.readFirmwareFile('nflasha1'))
  if kernel:
   nflasha1.write('/boot/vmlinux', kernel)
  if initrd:
   nflasha1.write('/boot/initrd.img', initrd)
  if patchKernelLoadaddr:
   nflasha1.patch('/boot/loadaddr.txt', lambda d: d.replace(b'0x81808000', b'0x80018000'))
  return archive.writeFat(nflasha1, 0x400000)

 def prepareFlash2(self, updaterMode=False, patchBackupWriteComp=False):
  initrd = archive.readCramfs(archive.readFat(self.readFirmwareFile('nflasha1')).read('/boot/initrd.img'))
  nflasha2 = archive.Archive()
  nflasha2.write('/Backup.bin', initrd.read('/root/Backup.bin'))
  nflasha2.write('/DmmConfig.bin', initrd.read('/root/DmmConfig.bin'))
  nflasha2.write('/ulogio.bin', initrd.read('/root/ulogio.bin'))
  nflasha2.write('/updater/dat4', b'\x00\x01')
  if updaterMode:
   nflasha2.write('/updater/mode', b'')
  if patchBackupWriteComp:
   nflasha2.patch('/Backup.bin', lambda d: d[:8] + b'\x01\0\0\0' + d[12:])
  return archive.writeFat(nflasha2, 0x400000)

 def prepareNand(self, boot=b'', partitions=[]):
  return onenand.writeNand(boot, archive.writeFlash(partitions), self.NAND_SIZE)

 def prepareQemuArgs(self, bootRom=None, kernel=None, initrd=None, nand=None, patchLoader2LogLevel=False):
  args = []
  if bootRom:
   args += ['-bios', bootRom]
  if kernel:
   args += ['-kernel', kernel]
  if initrd:
   args += ['-initrd', initrd]
  if nand:
   args += ['-drive', 'file=%s,if=mtd,format=raw' % nand]
  if patchLoader2LogLevel:
   args += ['-device', 'rom-loader,name=loader2-loglevel,addr=0xa0180000,data=7,data-len=4']
  return args

 def checkShell(self, func, checkCpuinfo=True, checkVersion=True):
  if checkCpuinfo:
   cpuinfo = func('cat /proc/cpuinfo')
   self.log.info('/proc/cpuinfo:\n%s', textwrap.indent(cpuinfo, '  '))
   if 'Hardware\t: ARM-CXD4132\n' not in cpuinfo:
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


 def testLoader2Updater(self):
  files = {
   'nand.dat': self.prepareNand(
    boot=self.prepareBootPartition(),
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
   q.expectLine(lambda l: l.startswith('diadem opal Loader2'))
   q.expectLine(lambda l: l.startswith('LDR: Jump to kernel'))
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
      kernel=self.prepareUpdaterKernel(unpackZimage=True, patchConsoleEnable=True),
      initrd=self.prepareUpdaterInitrd(patchTee=True),
      patchKernelLoadaddr=True,
     ),
     self.prepareFlash2(updaterMode=True, patchBackupWriteComp=True),
    ],
   ),
  }
  args = self.prepareQemuArgs(bootRom='rom.dat', nand='nand.dat', patchLoader2LogLevel=True)

  with qemu.QemuRunner(self.MACHINE, args, files) as q:
   q.expectLine(lambda l: l.startswith('opal Loader1'))
   q.expectLine(lambda l: l.startswith('diadem opal Loader2'))
   q.expectLine(lambda l: l.startswith('LDR: Jump to kernel'))
   q.expectLine(lambda l: l.startswith('BusyBox'))
   q.expectLine(lambda l: l.endswith('"DONE onEvent(COMP_START or COMP_STOP)"'))

   with usb.PmcaRunner('updatershell', ['-d', 'qemu', '-m', self.MODEL]) as pmca:
    pmca.expectLine(lambda l: l == 'Welcome to the USB debug shell.')
    self.checkShell(lambda c: pmca.execUpdaterShellCommand('shell %s' % c))
    pmca.writeLine('exit')
    pmca.expectLine(lambda l: l == '>Done')

   q.expectLine(lambda l: l == 'updaterufp OK')
