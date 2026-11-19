# Read-only check of the AFE4950EVM from the board. Sends only identity queries and register READS.
# Usage: python3 evm_probe.py            (scans /dev/ttyACM*)
# Protocol taken from TI's AFE4950 EVM firmware source V3.0.0 (pcComm.c).
import os, sys, glob, time, select, termios

def open_port(p):
    fd = os.open(p, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = a[1] = a[3] = 0; a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL   # raw 8N1
    a[4] = a[5] = termios.B115200; a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a); termios.tcflush(fd, termios.TCIOFLUSH); return fd

def ask(fd, msg, wait=0.6, until=None):
    termios.tcflush(fd, termios.TCIFLUSH)
    os.write(fd, msg.encode()); out = b''; end = time.time() + wait
    while time.time() < end:
        if select.select([fd], [], [], 0.1)[0]:
            try: out += os.read(fd, 4096)
            except BlockingIOError: pass
        if until and out.endswith(until): break
    return out

def quiet(fd, secs=1.0):
    """If a capture was left running, the EVM firmware blocks until its data is read. Stop it and drain the stream."""
    os.write(fd, b'C:CAP_STOP'); end = time.time() + secs
    while time.time() < end:
        if select.select([fd], [], [], 0.1)[0]:
            try: os.read(fd, 65536); end = time.time() + 0.4
            except BlockingIOError: pass
    termios.tcflush(fd, termios.TCIOFLUSH)

if __name__ == '__main__':
    ports = sorted(glob.glob('/dev/ttyACM*')) or sys.exit('no /dev/ttyACM* found: check the EVM USB cable (J9/J10) and that it is powered')
    for p in ports:
        fd = open_port(p); quiet(fd); r = ask(fd, 'C:CDC?', 1.0)
        print(f'{p}: C:CDC? -> {r!r}')
        if b'REG_EDIT' in r:
            print('  DEVICE?        ->', ask(fd, 'DEVICE?'))
            print('  FIRMWARE_VER?  ->', ask(fd, 'FIRMWARE_VER?'))
            for a in (0x00, 0x01, 0x1D, 0x6D):
                print(f'  REG 0x{a:02X} read -> {ask(fd, "C:REG_R%02X1" % a)!r}')
        os.close(fd)
