/* PSP <-> bridge transport. The same app talks to the bridge over USB
   (usbhostfs async channel, real hardware) or TCP (PPSSPP, later Wi-Fi). */
#ifndef PSPKIT_TRANSPORT_H
#define PSPKIT_TRANSPORT_H

#define PK_TCP_DEFAULT_HOST "127.0.0.1"
#define PK_TCP_DEFAULT_PORT 10200
#define PK_USB_CHANNEL      4     /* usbhostfs_pc exposes it on localhost:10004 */

typedef void (*pk_log_fn)(const char *msg);

typedef struct pk_transport
{
	const char *name; /* "usb" or "tcp" */
	char where[48];   /* human readable endpoint */
	int (*write)(const void *data, int len);
	/* Returns bytes read, 0 on timeout, < 0 when the link is gone. */
	int (*read)(void *data, int len, int timeout_us);
	/* Large transfer path (usbhostfs bulk on USB, plain send on TCP). */
	int (*write_bulk)(const void *data, int len);
	/* One non-blocking attempt to bring a lost link back; 0 when it is up. */
	int (*reconnect)(void);
} pk_transport_t;

/* Opens the link: tcp.cfg next to the EBOOT ("<host> <port>") forces TCP,
   otherwise USB is tried for up to 15 s and TCP is the fallback.
   Progress is reported through log (may be NULL). Returns < 0 on failure. */
int pk_transport_open(pk_transport_t *t, const char *argv0, pk_log_fn log);

#endif
