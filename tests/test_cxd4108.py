import glob
import os
from PIL import Image, ImageChops
import textwrap
import time

from . import TestCase
from runner import archive, kernel_patch, onenand, qemu, zimage


class FirmwareDump:
 def __init__(self, dir):
  self._dir = dir

 def _readFile(self, name, dir=None):
  with open(os.path.join(dir or self._dir, name), 'rb') as f:
   return f.read()

 def getBootRom(self):
  return self._readFile('bootrom')

 def getBootPartition(self):
  return self._readFile('boot')

 def getPartition(self, i):
  if i not in [1, 2, 3, 5, 6]:
   raise Exception('Invalid partition')
  return archive.readFat(self._readFile('nflasha%d' % i))


class FirmwareUpdate(FirmwareDump):
 def __init__(self, updateDir, dumpDir):
  super().__init__(dumpDir)
  self._updateDir = updateDir

 def _readUpdateFile(self, name):
  return self._readFile(name, self._updateDir)

 def _readUpdateTar(self, name):
  p = archive.Archive()
  for fn in glob.iglob(os.path.join(self._updateDir, name)):
   with open(fn, 'rb') as f:
    p.writeAll(archive.readTar(f.read()))
  return p

 def getPartition(self, i):
  p = archive.Archive()

  if i == 2:
   for f in ['backup.tar', 'factory.tar']:
    p.writeAll(self._readUpdateTar(f))
   for f in ['Asys', 'Hsys']:
    p.write('/factory/%s.bin' % f, self._readFile('%s.bin' % f))
    p.write('/factory/%s2.bak' % f, self._readFile('%s.bin' % f))
   p.patch('/factory/Areg.bin', lambda d: p.read('/factory/Asys.bin')[:1] + d[1:])

  elif i == 3:
   p.writeAll(self._readUpdateTar('linuxset[1-9].tar'), '/boot')

  elif i == 5:
   for f in ['av.bin', 'sa.bin']:
    p.write('/%s' % f, self._readUpdateFile(f))

  elif i == 6:
   for f in ['bin.tar', 'fskapp.tar', 'fskapp[1-9].tar', 'fskfnt.tar', 'fskrel[1-9].tar', 'lib.tar']:
    p.writeAll(self._readUpdateTar(f))

  else:
   p = super().getPartition(i)

  return p


class TestCXD4108(TestCase):
 MACHINE = 'cxd4108'
 NAND_SIZE = 0x4000000

 def prepareBootRom(self):
  return self.firmware.getBootRom()

 def prepareBootPartition(self):
  return self.firmware.getBootPartition()

 def prepareUpdaterKernel(self, unpackZimage=False):
  kernel = self.firmware.getPartition(1).read('/boot/vmlinux')
  if unpackZimage:
   kernel = zimage.unpackZimage(kernel)
  return kernel

 def prepareUpdaterInitrd(self, shellOnly=False):
  initrd = archive.readCramfs(self.firmware.getPartition(1).read('/boot/initrd.img'))
  if shellOnly:
   initrd.write('/sbin/init', b'#!/bin/sh\nmount -t proc proc /proc\nwhile true; do sh; done\n')
  return archive.writeCramfs(initrd)

 def prepareMainKernel(self, patchConsoleEnable=False):
  kernel = self.firmware.getPartition(3).read('/boot/vmlinux')
  if patchConsoleEnable:
   kernel = kernel_patch.patchConsoleEnable(kernel)
  return kernel

 def prepareFlash1(self, kernel=None, initrd=None):
  nflasha1 = self.firmware.getPartition(1)
  if kernel:
   nflasha1.write('/boot/vmlinux', kernel)
  if initrd:
   nflasha1.write('/boot/initrd.img', initrd)
  return archive.writeFat(nflasha1, 0x200000)

 def prepareFlash2(self, readSettings=False, updaterMode=False, playbackMode=False, patchTouchscreenEnable=False, patchLensCoverEnable=False, ntscOnly=False):
  nflasha2 = archive.Archive()
  if readSettings:
   settings = self.firmware.getPartition(2)
   for fn in settings.files:
    if (fn.startswith('/backup/') or fn.startswith('/factory/')) and fn.endswith('.bin'):
     nflasha2.write(fn, settings.read(fn))
  if updaterMode:
   nflasha2.write('/updater/mode', b'')
  if playbackMode:
   nflasha2.patch('/factory/Areg.bin', lambda d: d[:0x100] + b'\x84' + d[0x101:])
  if patchTouchscreenEnable:
   nflasha2.patch('/factory/Asys.bin', lambda d: d[:0x2a5] + b'\x01' + d[0x2a6:])
  if patchLensCoverEnable:
   nflasha2.patch('/factory/Asys.bin', lambda d: d[:0x2a6] + b'\x01' + d[0x2a7:])
  if ntscOnly:
   nflasha2.patch('/factory/Hreg.bin', lambda d: d[:0x400] + b'\x02' + d[0x401:])
  return archive.writeFat(nflasha2, 0x180000)

 def prepareFlash3(self, kernel=None, rootfs=None):
  nflasha3 = self.firmware.getPartition(3)
  if kernel:
   nflasha3.write('/boot/vmlinux', kernel)
  if rootfs:
   nflasha3.write('/boot/rootfs.img', rootfs)
  return archive.writeFat(nflasha3, 0x400000)

 def prepareFlash5(self):
  nflasha5 = self.firmware.getPartition(5)
  return archive.writeFat(nflasha5, 0x380000)

 def prepareFlash6(self):
  nflasha6 = self.firmware.getPartition(6)
  return archive.writeFat(nflasha6, 0x1000000)

 def prepareFlash11(self):
  nflasha11 = archive.Archive()
  return archive.writeMbr([archive.writeFat(nflasha11, 0x7ffe00)])

 def prepareNand(self, boot=b'', partitions=[]):
  return onenand.writeNand(boot, archive.writeFlash(partitions), self.NAND_SIZE, 0x100000)

 def prepareQemuArgs(self, bootRom=None, kernel=None, initrd=None, nand=None, mmc=None):
  args = ['-icount', 'shift=4']
  if bootRom:
   args += ['-bios', bootRom]
  if kernel:
   args += ['-kernel', kernel]
  if initrd:
   args += ['-initrd', initrd]
  if nand:
   args += ['-drive', 'file=%s,if=mtd,format=raw' % nand]
   if mmc:
    args += ['-drive', 'file=%s,if=mtd,format=raw' % mmc]
  return args


class TestDscW90(TestCXD4108):
 FIRMWARE_DIR = 'firmware/DSC-W90'

 firmware = FirmwareDump(FIRMWARE_DIR)

 def prepareQemuArgs(self, bootRom=None, kernel=None, initrd=None, nand=None):
  args = super().prepareQemuArgs(bootRom=bootRom, kernel=kernel, initrd=initrd, nand=nand)

  # Power IC
  args += ['-device', 'bionz_mb89083,id=mb89083,bus=/sio0', '-connect-gpio', 'odev=gpio1,onum=1,idev=mb89083,iname=ssi-gpio-cs']

  # Battery auth
  args += ['-device', 'bionz_upd79f,id=upd79f,bus=/sio1', '-connect-gpio', 'odev=gpios,onum=4,idev=upd79f,iname=ssi-gpio-cs']

  # Buttons
  args += ['-device', 'bionz_buttons,id=buttons,bus=/adc0,keys0=druls,keys1=wtmh,keys=p', '-connect-gpio', 'odev=buttons,idev=mb89083,iname=play']

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


class TestDscT100(TestCXD4108):
 FIRMWARE_DIR = 'firmware/DSC-T100'
 FIRMWARE_DUMP_DIR = 'firmware/DSC-W90'
 SCREENSHOT_DIR = 'screenshots/DSC-T100'

 firmware = FirmwareUpdate(FIRMWARE_DIR, FIRMWARE_DUMP_DIR)

 def prepareQemuArgs(self, bootRom=None, nand=None):
  args = super().prepareQemuArgs(bootRom=bootRom, nand=nand)

  # Power IC
  args += ['-device', 'bionz_mb89083,id=mb89083,bus=/sio0', '-connect-gpio', 'odev=gpio1,onum=1,idev=mb89083,iname=ssi-gpio-cs']

  # Battery auth
  args += ['-device', 'bionz_upd79f,id=upd79f,bus=/sio1', '-connect-gpio', 'odev=gpios,onum=4,idev=upd79f,iname=ssi-gpio-cs']

  # Buttons
  args += ['-device', 'bionz_buttons,id=buttons,bus=/adc0,keys0=rluds,keys1=twhm,keys=p', '-connect-gpio', 'odev=buttons,idev=mb89083,iname=play']

  return args

 def testLoader1Main(self):
  files = {
   'rom.dat': self.prepareBootRom(),
   'nand.dat': self.prepareNand(
    boot=self.prepareBootPartition(),
    partitions=[
     b'',
     self.prepareFlash2(readSettings=True, patchLensCoverEnable=True, playbackMode=True, ntscOnly=True),
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


class TestDscG3(TestCXD4108):
 FIRMWARE_DIR = 'firmware/DSC-G3'
 FIRMWARE_DUMP_DIR = 'firmware/DSC-W90'
 SCREENSHOT_DIR = 'screenshots/DSC-G3'

 firmware = FirmwareUpdate(FIRMWARE_DIR, FIRMWARE_DUMP_DIR)

 def prepareQemuArgs(self, bootRom=None, nand=None, mmc=None):
  args = super().prepareQemuArgs(bootRom=bootRom, nand=nand, mmc=mmc)

  # Power IC
  args += ['-device', 'bionz_sc901572,id=sc901572,bus=/sio0', '-connect-gpio', 'odev=gpio1,onum=1,idev=sc901572,iname=ssi-gpio-cs']

  # Battery auth
  args += ['-device', 'bionz_upd79f,id=upd79f,bus=/sio1', '-connect-gpio', 'odev=gpios,onum=4,idev=upd79f,iname=ssi-gpio-cs']
  args += ['-device', 'analog_voltage,id=batt_sens,bus=/adc0,channel=5,value=128']

  # Buttons
  args += ['-device', 'bionz_buttons,id=buttons,bus=/adc0,keys0=tw,keys=p', '-connect-gpio', 'odev=buttons,idev=sc901572,iname=play']

  # Touch panel
  args += ['-device', 'bionz_touch_panel,id=touch_panel,bus=/adc0', '-connect-gpio', 'odev=gpio3,onum=5,idev=touch_panel,inum=0', '-connect-gpio', 'odev=gpio3,onum=6,idev=touch_panel,inum=1']

  return args


 def testLoader1Main(self):
  files = {
   'rom.dat': self.prepareBootRom(),
   'nand.dat': self.prepareNand(
    boot=self.prepareBootPartition(),
    partitions=[
     b'',
     self.prepareFlash2(readSettings=True, patchTouchscreenEnable=True, playbackMode=True, ntscOnly=True),
     self.prepareFlash3(kernel=self.prepareMainKernel(patchConsoleEnable=True)),
     b'',
     self.prepareFlash5(),
     self.prepareFlash6(),
    ],
   ),
   'mmc.dat': self.prepareFlash11(),
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
