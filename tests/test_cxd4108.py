import os
from PIL import Image, ImageChops
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
 SCREENSHOT_DIR = 'screenshots/DSC-W90'

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

  # Buttons
  args += ['-device', 'bionz_buttons,bus=/adc0,keys0=druls,keys1=wtmh']

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
   def waitScreen():
    q.execShellCommand('cat /dev/blog_fsk > /dev/null; until egrep \'^.{8}038504002b20627265774642446973706f73654269746d617000\' /dev/blog_fsk > /dev/null; do usleep 200000; done')
    time.sleep(1)

   def pressKey(key):
    q.sendKey(key, True)
    q.sendKey(key, False)
    time.sleep(.5)

   def checkScreen(fn):
    im = q.screenshot()
    path = os.path.join(self.SCREENSHOT_DIR, fn)
    if ImageChops.difference(im, Image.open(path)).getbbox():
     raise Exception('%s is different' % fn)

   q.expectLine(lambda l: l.startswith('BusyBox'))
   waitScreen()
   checkScreen('clock.png')

   pressKey('down')
   pressKey('down')
   pressKey('down')
   pressKey('ret') # ok
   waitScreen()
   checkScreen('playback.png')

   pressKey('h')
   time.sleep(2)
   checkScreen('home.png')
   pressKey('h')

   pressKey('m')
   time.sleep(2)
   checkScreen('menu.png')
   pressKey('m')



class TestDscG3(TestCase):
 MACHINE = 'cxd4108'
 NAND_SIZE = 0x4000000

 FIRMWARE_DIR = 'firmware/DSC-G3'
 FIRMWARE_DUMP_DIR = 'firmware/DSC-W90'
 SCREENSHOT_DIR = 'screenshots/DSC-G3'

 def readFirmwareFile(self, name):
  with open(os.path.join(self.FIRMWARE_DIR, name), 'rb') as f:
   return f.read()

 def readFirmwareDumpFile(self, name):
  with open(os.path.join(self.FIRMWARE_DUMP_DIR, name), 'rb') as f:
   return f.read()

 def prepareBootRom(self):
  return self.readFirmwareDumpFile('bootrom')

 def prepareBootPartition(self):
  return self.readFirmwareDumpFile('boot')

 def prepareMainKernel(self, patchConsoleEnable=False):
  kernel = archive.readTar(self.readFirmwareFile('linuxset1.tar')).read('/vmlinux')
  if patchConsoleEnable:
   kernel = kernel_patch.patchConsoleEnable(kernel)
  return kernel

 def prepareFlash2(self, patchTouchscreenEnable=False, patchAregVersion=False, playbackMode=False):
  nflasha2 = archive.Archive()
  for f in ['backup.tar', 'factory.tar']:
   nflasha2.writeAll(archive.readTar(self.readFirmwareFile(f)))
  for f in ['Asys', 'Hsys']:
   nflasha2.write('/factory/%s.bin' % f, self.readFirmwareDumpFile('%s.bin' % f))
   nflasha2.write('/factory/%s2.bak' % f, self.readFirmwareDumpFile('%s.bin' % f))
  if patchTouchscreenEnable:
   nflasha2.patch('/factory/Asys.bin', lambda d: d[:0x2a5] + b'\x01' + d[0x2a6:])
  if patchAregVersion:
   nflasha2.patch('/factory/Areg.bin', lambda d: b'\x04' + d[1:])
  if playbackMode:
   nflasha2.patch('/factory/Areg.bin', lambda d: d[:0x100] + b'\x84' + d[0x101:])
  return archive.writeFat(nflasha2, 0x180000)

 def prepareFlash3(self, kernel=None, rootfs=None):
  nflasha3 = archive.Archive()
  nflasha3.writeAll(archive.readTar(self.readFirmwareFile('linuxset1.tar')), '/boot')
  if kernel:
   nflasha3.write('/boot/vmlinux', kernel)
  if rootfs:
   nflasha3.write('/boot/rootfs.img', rootfs)
  return archive.writeFat(nflasha3, 0x400000)

 def prepareFlash5(self):
  nflasha5 = archive.Archive()
  for f in ['av.bin', 'sa.bin']:
   nflasha5.write('/%s' % f, self.readFirmwareFile(f))
  return archive.writeFat(nflasha5, 0x380000)

 def prepareFlash6(self):
  nflasha6 = archive.Archive()
  for f in ['bin.tar', 'fskapp1.tar', 'fskfnt.tar', 'fskrel1.tar', 'fskrel2.tar', 'lib.tar']:
   nflasha6.writeAll(archive.readTar(self.readFirmwareFile(f)))
  return archive.writeFat(nflasha6, 0x1de0000)

 def prepareMmc(self):
  return archive.writeMbr([archive.writeFat(archive.Archive(), 0x7ffe00)])

 def prepareNand(self, boot=b'', partitions=[]):
  return onenand.writeNand(boot, archive.writeFlash(partitions), self.NAND_SIZE, 0x100000)

 def prepareQemuArgs(self, bootRom=None, nand=None, mmc=None):
  args = ['-icount', 'shift=4']

  # Power IC
  args += ['-device', 'bionz_mb89083,id=mb89083,bus=/sio0', '-connect-gpio', 'odev=gpio1,onum=1,idev=mb89083,iname=ssi-gpio-cs']

  # Battery auth
  args += ['-device', 'bionz_upd79f,id=upd79f,bus=/sio1', '-connect-gpio', 'odev=gpios,onum=4,idev=upd79f,iname=ssi-gpio-cs']
  args += ['-device', 'analog_voltage,id=batt_sens,bus=/adc0,channel=5,value=128']

  # Buttons
  args += ['-device', 'bionz_buttons,bus=/adc0,keys0=twh']

  # Touch panel
  args += ['-device', 'bionz_touch_panel,id=touch_panel,bus=/adc0', '-connect-gpio', 'odev=gpio3,onum=5,idev=touch_panel,inum=0', '-connect-gpio', 'odev=gpio3,onum=6,idev=touch_panel,inum=1']

  if bootRom:
   args += ['-bios', bootRom]
  if nand:
   args += ['-drive', 'file=%s,if=mtd,format=raw' % nand]
   if mmc:
    args += ['-drive', 'file=%s,if=mtd,format=raw' % mmc]
  return args


 def testLoader1Main(self):
  files = {
   'rom.dat': self.prepareBootRom(),
   'nand.dat': self.prepareNand(
    boot=self.prepareBootPartition(),
    partitions=[
     b'',
     self.prepareFlash2(patchTouchscreenEnable=True, patchAregVersion=True, playbackMode=True),
     self.prepareFlash3(kernel=self.prepareMainKernel(patchConsoleEnable=True)),
     b'',
     self.prepareFlash5(),
     self.prepareFlash6(),
    ],
   ),
   'mmc.dat': self.prepareMmc(),
  }
  args = self.prepareQemuArgs(bootRom='rom.dat', nand='nand.dat', mmc='mmc.dat')

  with qemu.QemuRunner(self.MACHINE, args, files, timeout=20) as q:
   def waitScreen():
    q.execShellCommand('cat /dev/blog_fsk > /dev/null; until egrep \'^.{16}0485040000000003\' /dev/blog_fsk > /dev/null; do usleep 200000; done')
    time.sleep(1)

   def click(x, y):
    q.sendMousePos(x, y)
    q.sendMouseButton(True)
    q.sendMouseButton(False)
    time.sleep(1)

   def checkScreen(fn):
    im = q.screenshot()
    path = os.path.join(self.SCREENSHOT_DIR, fn)
    if ImageChops.difference(im, Image.open(path)).getbbox():
     raise Exception('%s is different' % fn)

   q.expectLine(lambda l: l.startswith('BusyBox'))
   waitScreen()
   checkScreen('clock1.png')

   click(.9, .9) # next
   checkScreen('clock2.png')

   click(.5, .9) # ok
   waitScreen()
   checkScreen('playback.png')

   click(.1, .1) # home
   checkScreen('home.png')
   click(.9, .1) # close

   click(.1, .9) # menu
   checkScreen('menu.png')
   click(.9, .1) # close
