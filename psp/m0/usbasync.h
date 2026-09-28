/* User-side declarations for the usbhostfs.prx async API.
   Mirrors third_party/psplinkusb/usbhostfs/usbasync.h (BSD-3-Clause). */
#ifndef PSPKIT_USBASYNC_H
#define PSPKIT_USBASYNC_H

#include <pspkerneltypes.h>
#include <pspmodulemgr.h>

#define MAX_ASYNC_BUFFER   4096
#define ASYNC_USER         4      /* channels 0-3 are reserved for psplink */
#define HOSTFSDRIVER_NAME  "USBHostFSDriver"
#define HOSTFSDRIVER_PID   0x1C9

struct AsyncEndpoint
{
	unsigned char buffer[MAX_ASYNC_BUFFER];
	int read_pos;
	int write_pos;
	int size;
};

int  usbWaitForConnect(void);
int  usbAsyncRegister(unsigned int chan, struct AsyncEndpoint *endp);
int  usbAsyncUnregister(unsigned int chan);
int  usbAsyncWrite(unsigned int chan, const void *data, int len);
int  usbAsyncRead(unsigned int chan, unsigned char *data, int len);
int  usbAsyncReadWithTimeout(unsigned int chan, unsigned char *data, int len, int timeout);
void usbAsyncFlush(unsigned int chan);
int  usbWriteBulkData(int chan, const void *data, int len);

SceUID kuKernelLoadModule(const char *path, int flags, SceKernelLMOption *option);

#endif
