/* PSP <-> bridge transport. The same app talks to the bridge over USB
   (usbhostfs async channel, real hardware) or TCP (PPSSPP, later Wi-Fi). */
#ifndef PSPKIT_TRANSPORT_H
#define PSPKIT_TRANSPORT_H

#define TCP_DEFAULT_HOST "127.0.0.1"
#define TCP_DEFAULT_PORT 10200

typedef struct transport
{
	const char *name; /* "usb" or "tcp" */
	char where[48];   /* human readable endpoint for the status screen */
	int (*write)(const void *data, int len);
	/* Returns bytes read, 0 on timeout, < 0 on error. */
	int (*read)(void *data, int len, int timeout_us);
	/* Large transfer path (usbhostfs bulk on USB, plain send on TCP). */
	int (*write_bulk)(const void *data, int len);
} transport_t;

/* Loads usbhostfs.prx next to argv0 and brings the USB link up, waiting up to
   15 s for usbhostfs_pc. Returns < 0 when USB is unavailable (no KUBridge, no
   PC answering, PPSSPP) so the caller can fall back to TCP; *fatal is set when
   USB exists but a driver step failed. */
int transport_usb_open(transport_t *t, const char *argv0, int *fatal);

/* Brings up the network (PPSSPP fakes the access point) and connects. */
int transport_tcp_open(transport_t *t, const char *host, int port);

#endif
