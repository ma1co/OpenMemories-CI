import textwrap
import time

from . import TestCase
from runner import archive, onenand, qemu, usb, zimage

class TestCXD4132(TestCase):
 MACHINE = 'cxd4132'
 NAND_SIZE = 0x10000000

 MODEL = 'DSC-QX10'
 FIRMWARE_DIR = 'firmware/DSC-QX10'

 def readUpdaterPartition(self):
  with open(self.FIRMWARE_DIR+'/nflasha1', 'rb') as f:
   return f.read()

 def unpackUpdaterPartition(self):
  nflasha1 = archive.readFat(self.readUpdaterPartition())
  kernel = zimage.unpackZimage(nflasha1.read('/boot/vmlinux'))
  initrd = archive.readCramfs(nflasha1.read('/boot/initrd.img'))
  return kernel, initrd


 def testUpdaterKernel(self):
  kernel, initrd = self.unpackUpdaterPartition()

  kernel = kernel.replace(b'amba2.console=0', b'amba2.console=1')

  initrd.write('/sbin/init', b'#!/bin/sh\nmount -t proc proc /proc\nwhile true; do sh; done\n')
  initrd = archive.writeCramfs(initrd)

  files = {'vmlinux.bin': kernel, 'initrd.img': initrd}
  args = ['-kernel', 'vmlinux.bin', '-initrd', 'initrd.img']

  with qemu.QemuRunner(self.MACHINE, args, files) as q:
   q.expectLine(lambda l: l.startswith('BusyBox'))
   time.sleep(.5)

   cpuinfo = q.execShellCommand('cat /proc/cpuinfo')
   self.log.info('/proc/cpuinfo:\n%s', textwrap.indent(cpuinfo, '  '))
   if 'Hardware\t: ARM-CXD4132\n' not in cpuinfo:
    raise Exception('Invalid cpuinfo')

   version = q.execShellCommand('cat /proc/version')
   self.log.info('/proc/version:\n%s', textwrap.indent(version, '  '))
   if not version.startswith('Linux version 2.6'):
    raise Exception('Invalid version')


 def testUpdaterUsb(self):
  kernel, initrd = self.unpackUpdaterPartition()

  kernel = kernel.replace(b'amba2.console=0', b'amba2.console=1')

  initrd.patch('/sbin/init', lambda d: d.replace(b' | tee -a $OUTPUT_LOG', b''))
  initrd.patch('/root/insmod.sh', lambda d: d.replace(b'Backup_save=0', b'Backup_load=1 Backup_save=0'))
  initrd.write('/root/is_valid_boot.sh', b'#!/bin/sh\nexit 0\n')

  nflasha1 = self.readUpdaterPartition()

  nflasha2 = archive.Archive()
  nflasha2.write('/Backup.bin', initrd.read('/root/Backup.bin'))
  nflasha2.write('/DmmConfig.bin', initrd.read('/root/DmmConfig.bin'))
  nflasha2.write('/ulogio.bin', initrd.read('/root/ulogio.bin'))
  nflasha2.write('/updater/dat4', b'\x00\x01')
  nflasha2 = archive.writeFat(nflasha2, 0x400000)

  initrd = archive.writeCramfs(initrd)
  nflasha = archive.writeFlash([nflasha1, nflasha2])
  nand = onenand.writeNand(nflasha, self.NAND_SIZE)

  files = {'vmlinux.bin': kernel, 'initrd.img': initrd, 'nand.dat': nand}
  args = ['-kernel', 'vmlinux.bin', '-initrd', 'initrd.img', '-drive', 'file=nand.dat,if=mtd,format=raw']

  with qemu.QemuRunner(self.MACHINE, args, files) as q:
   q.expectLine(lambda l: l.endswith('"DONE onEvent(COMP_START or COMP_STOP)"'))

   with usb.PmcaRunner('updatershell', ['-d', 'qemu', '-m', self.MODEL]) as pmca:
    pmca.expectLine(lambda l: l == 'Welcome to the USB debug shell.')

    cpuinfo = pmca.execUpdaterShellCommand('shell cat /proc/cpuinfo')
    self.log.info('/proc/cpuinfo:\n%s', textwrap.indent(cpuinfo, '  '))
    if 'Hardware\t: ARM-CXD4132\n' not in cpuinfo:
     raise Exception('Invalid cpuinfo')

    version = pmca.execUpdaterShellCommand('shell cat /proc/version')
    self.log.info('/proc/version:\n%s', textwrap.indent(version, '  '))
    if not version.startswith('Linux version 2.6'):
     raise Exception('Invalid version')

    pmca.writeLine('exit')
    pmca.expectLine(lambda l: l == '>Done')

   q.expectLine(lambda l: l == 'updaterufp OK')
