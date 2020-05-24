import textwrap
import time

from . import TestCase
from runner import archive, qemu, zimage

class TestCXD90014(TestCase):
 MACHINE = 'cxd90014'

 MODEL = 'DSC-RX100M5'
 FIRMWARE_DIR = 'firmware/DSC-RX100M5'

 def readUpdaterPartition(self):
  with open(self.FIRMWARE_DIR+'/nflasha1', 'rb') as f:
   return f.read()

 def unpackUpdaterPartition(self):
  nflasha1 = archive.readFat(self.readUpdaterPartition())
  kernel = zimage.unpackZimage(nflasha1.read('/boot/vmlinux.bin'))
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
   if 'Hardware\t: ARM-CXD90014\n' not in cpuinfo:
    raise Exception('Invalid cpuinfo')

   version = q.execShellCommand('cat /proc/version')
   self.log.info('/proc/version:\n%s', textwrap.indent(version, '  '))
   if not version.startswith('Linux version 3.0'):
    raise Exception('Invalid version')
