import binascii
import ctypes
import fcntl
import sys
import uuid
import random
import time

from influxdb import InfluxDBClient

from attributes import attributes

class ata_command(ctypes.Structure):
  """ATA Command Pass-Through
     http://www.t10.org/ftp/t10/document.04/04-262r8.pdf"""

  _fields_ = [
      ('opcode', ctypes.c_ubyte),
      ('protocol', ctypes.c_ubyte),
      ('flags', ctypes.c_ubyte),
      ('features', ctypes.c_ubyte),
      ('sector_count', ctypes.c_ubyte),
      ('lba_low', ctypes.c_ubyte),
      ('lba_mid', ctypes.c_ubyte),
      ('lba_high', ctypes.c_ubyte),
      ('device', ctypes.c_ubyte),
      ('command', ctypes.c_ubyte),
      ('reserved', ctypes.c_ubyte),
      ('control', ctypes.c_ubyte) ]


class SgioHdr(ctypes.Structure):
  """<scsi/sg.h> sg_io_hdr_t."""

  _fields_ = [
      ('interface_id', ctypes.c_int),
      ('dxfer_direction', ctypes.c_int),
      ('cmd_len', ctypes.c_ubyte),
      ('mx_sb_len', ctypes.c_ubyte),
      ('iovec_count', ctypes.c_ushort),
      ('dxfer_len', ctypes.c_uint),
      ('dxferp', ctypes.c_void_p),
      ('cmdp', ctypes.c_void_p),
      ('sbp', ctypes.c_void_p),
      ('timeout', ctypes.c_uint),
      ('flags', ctypes.c_uint),
      ('pack_id', ctypes.c_int),
      ('usr_ptr', ctypes.c_void_p),
      ('status', ctypes.c_ubyte),
      ('masked_status', ctypes.c_ubyte),
      ('msg_status', ctypes.c_ubyte),
      ('sb_len_wr', ctypes.c_ubyte),
      ('host_status', ctypes.c_ushort),
      ('driver_status', ctypes.c_ushort),
      ('resid', ctypes.c_int),
      ('duration', ctypes.c_uint),
      ('info', ctypes.c_uint)]

def IndexGenerator(n):
  while n < 361:
    yield n
    n += 12

def GetSmartsSgIo(dev, verbose=False):
  if dev[0] != '/':
    dev = '/dev/' + dev

  # Instantiate the InfluxDB client if not printing to stdout.
  client = None
  if not verbose:
    client = InfluxDBClient(host='localhost', port=8086, username='admin', password='admin')
    data = []

  # Build the CDB
  ata_cmd = ata_command(opcode=0xa1,  # ATA PASS-THROUGH (12)
                   protocol=0x0c,  # FPDMA
                   # flags field
                   # OFF_LINE = 0 (0 seconds offline)
                   # CK_COND = 0 (don't copy sense data in response)
                   # T_DIR = 1 (transfer from the ATA device)
                   # BYT_BLOK = 1 (length is in blocks, not bytes)
                   # T_LENGTH = 2 (transfer length in the SECTOR_COUNT field)
                   flags=0x0e,
                   features=0xd0,  # SMART READ DATA
                   sector_count=1,
                   lba_low=0, lba_mid=0x4f, lba_high=0xc2,
                   device=0,
                   command=0xb0,  # Read S.M.A.R.T Log
                   reserved=0, control=0)

  ASCII_S = 83
  SG_DXFER_FROM_DEV = -3
  sense = ctypes.c_buffer(64)
  return_buffer = ctypes.c_buffer(512)

  sgio = SgioHdr(interface_id=ASCII_S, dxfer_direction=SG_DXFER_FROM_DEV,
                 cmd_len=ctypes.sizeof(ata_cmd),
                 mx_sb_len=ctypes.sizeof(sense), iovec_count=0,
                 dxfer_len=ctypes.sizeof(return_buffer),
                 dxferp=ctypes.cast(return_buffer, ctypes.c_void_p),
                 cmdp=ctypes.addressof(ata_cmd),
                 sbp=ctypes.cast(sense, ctypes.c_void_p), timeout=20000,
                 flags=0, pack_id=0, usr_ptr=None, status=0, masked_status=0,
                 msg_status=0, sb_len_wr=0, host_status=0, driver_status=0,
                 resid=0, duration=0, info=0)
  SG_IO = 0x2285  # <scsi/sg.h>

  with open(dev, 'r') as fd:
    if(fcntl.ioctl(fd, SG_IO, ctypes.addressof(sgio)) != 0):
      print("fcntl failed")
      return None

    if not verbose:
      time_stamp = int(time.time() * 1000) # milliseconds

    # return_buffer format as defined on pg 91 of
    # http://t13.org/Documents/UploadedDocuments/docs2006/D1699r3f-ATA8-ACS.pdf
    if verbose:
      print("ID\t\tONLINE-OFFLINE\t\tRAW-VALUE\t\tDESCRIPTION")
    for index in IndexGenerator(2):
      id = int(binascii.b2a_hex(return_buffer[index]), 16)
      if id == 0:
        continue
      if verbose:
        print("{}\t\t".format(id), end="")

      if(int(binascii.b2a_hex(return_buffer[index + 1]), 16) & 2):
        if verbose:
          print("ONLINE+OFFLINE\t\t", end="")
      else:
        if verbose:
          print("OFFLINE       \t\t", end="")

      raw = 0
      # Temperature is parsed differently than other values, in that no shifting is needed to get the values.
      if id == 194:
        temp = int(binascii.b2a_hex(return_buffer[index + 5]), 16)
        temp_min = int(binascii.b2a_hex(return_buffer[index + 7]), 16)
        temp_max = int(binascii.b2a_hex(return_buffer[index + 9]), 16)
        if verbose:
          print('{} (Min/Max {}/{})\t'.format(temp, temp_min, temp_max), end="")
        raw = temp
      else:
        raw = int(binascii.b2a_hex(return_buffer[index + 5]), 16) | int(binascii.b2a_hex(return_buffer[index + 6]), 16) << 8 | int(binascii.b2a_hex(return_buffer[index+7]), 16) << 16 | int(binascii.b2a_hex(return_buffer[index+8]), 16) << 24 | int(binascii.b2a_hex(return_buffer[index+9]), 16) << 32 | int(binascii.b2a_hex(return_buffer[index+10]), 16) << 40
        if verbose:  
          print('{}\t\t\t'.format(raw), end="")
      if verbose:
        print(attributes.get(id, "Unknown"))
      else:
        data.append(
          {
            "measurement": "smart",
            "tags": {
              "id": id
            },
            "fields": {
              "value": raw,
              "description": attributes.get(id, "Unknown")
            },
            "time": time_stamp
          }
        )
  if not verbose:                       
    client.write_points(data, database='smart_mon', time_precision='ms', protocol='json')
    print("Sent info to DB.")
  return


if __name__ == '__main__':
  verbose = False
  if len(sys.argv) > 2:
    verbose = (sys.argv[2].lower() == 'true')

  if not verbose:
    while(True):
      GetSmartsSgIo(sys.argv[1], verbose)
  else:
    GetSmartsSgIo(sys.argv[1], verbose)