#include <pspkernel.h>
#include <pspusb.h>
#include <pspusbbus.h>
#include <psputility.h>
#include <pspnet.h>
#include <pspnet_inet.h>
#include <pspnet_apctl.h>
#include <pspsdk.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "transport.h"
#include "usbasync.h"

#define CHAN PK_USB_CHANNEL
#define SCE_KERNEL_ERROR_EXCLUSIVE_LOAD 0x80020139
#define APCTL_TIMEOUT_US       (10 * 1000 * 1000)
#define USB_CONNECT_TIMEOUT_US (15 * 1000 * 1000)

static pk_log_fn g_log;

static void tlog(const char *fmt, ...)
{
	char buf[96];
	va_list ap;

	if (!g_log)
		return;
	va_start(ap, fmt);
	vsnprintf(buf, sizeof(buf), fmt, ap);
	va_end(ap);
	g_log(buf);
}

static long long now_us(void)
{
	return (long long)sceKernelGetSystemTimeWide();
}

/* Replaces the file name in argv0 ("ms0:/PSP/GAME/x/EBOOT.PBP"). */
static void sibling_path(char *out, int outlen, const char *argv0, const char *name)
{
	char *slash;

	strncpy(out, argv0, outlen - 1);
	out[outlen - 1] = 0;
	slash = strrchr(out, '/');
	snprintf(slash ? slash + 1 : out, outlen - (slash ? (slash + 1 - out) : 0), "%s", name);
}

/* ---- USB: usbhostfs async channel ---- */

static struct AsyncEndpoint g_endp;

static int usb_write(const void *data, int len)
{
	return usbAsyncWrite(CHAN, data, len);
}

static int usb_read(void *data, int len, int timeout_us)
{
	int n = usbAsyncReadWithTimeout(CHAN, data, len, timeout_us);
	return n < 0 ? 0 : n; /* timeouts come back as error codes */
}

static int usb_write_bulk(const void *data, int len)
{
	return usbWriteBulkData(CHAN, data, len);
}

/* A zero-length write fails until usbhostfs_pc is connected. We poll it
   because usbWaitForConnect() blocks forever when no PC ever answers. */
static int usb_reconnect(void)
{
	return usbAsyncWrite(CHAN, "", 0) < 0 ? -1 : 0;
}

static int usb_open(pk_transport_t *t, const char *argv0, int *fatal)
{
	char path[256];
	SceUID mod;
	int ret, status;
	long long deadline;

	*fatal = 0;
	sibling_path(path, sizeof(path), argv0, "usbhostfs.prx");
	mod = kuKernelLoadModule(path, 0, NULL);
	tlog("usb: kuKernelLoadModule 0x%08X", mod);
	/* A missing KUBridge or prx shows up as an error or 0 here. */
	if (mod <= 0 && (unsigned)mod != SCE_KERNEL_ERROR_EXCLUSIVE_LOAD)
		return -1;
	if (mod > 0) {
		ret = sceKernelStartModule(mod, 0, NULL, &status, NULL);
		if (ret < 0) {
			tlog("usb: sceKernelStartModule 0x%08X", ret);
			return -1;
		}
	}

	*fatal = 1;
	sceUsbStart(PSP_USBBUS_DRIVERNAME, 0, 0);
	sceUsbStart(HOSTFSDRIVER_NAME, 0, 0);
	ret = sceUsbActivate(HOSTFSDRIVER_PID);
	if (ret < 0) {
		tlog("usb: sceUsbActivate 0x%08X", ret);
		return ret;
	}
	ret = usbAsyncRegister(CHAN, &g_endp);
	if (ret < 0) {
		tlog("usb: usbAsyncRegister 0x%08X", ret);
		return ret;
	}

	tlog("usb: PC bekleniyor (15 sn)...");
	deadline = now_us() + USB_CONNECT_TIMEOUT_US;
	while (usb_reconnect() < 0) {
		if (now_us() >= deadline) {
			tlog("usb: PC baglanmadi, USB kapatiliyor");
			usbAsyncUnregister(CHAN);
			sceUsbDeactivate(HOSTFSDRIVER_PID);
			sceUsbStop(HOSTFSDRIVER_NAME, 0, 0);
			sceUsbStop(PSP_USBBUS_DRIVERNAME, 0, 0);
			*fatal = 0;
			return -1;
		}
		sceKernelDelayThread(100 * 1000);
	}

	t->name = "usb";
	snprintf(t->where, sizeof(t->where), "USB kanal %d", CHAN);
	t->write = usb_write;
	t->read = usb_read;
	t->write_bulk = usb_write_bulk;
	t->reconnect = usb_reconnect;
	return 0;
}

/* ---- TCP ---- */

static int g_sock = -1;
static struct sockaddr_in g_addr;

static int tcp_write(const void *data, int len)
{
	const char *p = data;
	int sent = 0;

	if (g_sock < 0)
		return -1;
	while (sent < len) {
		int n = send(g_sock, p + sent, len - sent, 0);
		if (n <= 0)
			return -1;
		sent += n;
	}
	return sent;
}

static int tcp_read(void *data, int len, int timeout_us)
{
	fd_set set;
	struct timeval tv;
	int n;

	if (g_sock < 0)
		return -1;
	FD_ZERO(&set);
	FD_SET(g_sock, &set);
	tv.tv_sec = timeout_us / 1000000;
	tv.tv_usec = timeout_us % 1000000;
	if (select(g_sock + 1, &set, NULL, NULL, &tv) <= 0)
		return 0;
	n = recv(g_sock, data, len, 0);
	return n <= 0 ? -1 : n; /* 0 from recv means the bridge closed */
}

static int tcp_reconnect(void)
{
	int one = 1;

	if (g_sock >= 0)
		close(g_sock);
	g_sock = socket(PF_INET, SOCK_STREAM, 0);
	if (g_sock < 0)
		return -1;
	setsockopt(g_sock, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
	if (connect(g_sock, (struct sockaddr *)&g_addr, sizeof(g_addr)) < 0) {
		close(g_sock);
		g_sock = -1;
		return -1;
	}
	return 0;
}

static int apctl_connect(void)
{
	int state = 0, ret;
	long long deadline = now_us() + APCTL_TIMEOUT_US;

	ret = sceNetApctlConnect(1);
	if (ret < 0) {
		tlog("tcp: sceNetApctlConnect 0x%08X", ret);
		return ret;
	}
	while (now_us() < deadline) {
		if ((ret = sceNetApctlGetState(&state)) < 0)
			return ret;
		if (state == PSP_NET_APCTL_STATE_GOT_IP)
			return 0;
		sceKernelDelayThread(50 * 1000);
	}
	tlog("tcp: erisim noktasi zaman asimi");
	return -1;
}

static int tcp_open(pk_transport_t *t, const char *host, int port)
{
	int ret;

	sceUtilityLoadNetModule(PSP_NET_MODULE_COMMON);
	sceUtilityLoadNetModule(PSP_NET_MODULE_INET);
	if ((ret = pspSdkInetInit()) < 0) {
		tlog("tcp: pspSdkInetInit 0x%08X", ret);
		return ret;
	}
	if ((ret = apctl_connect()) < 0)
		return ret;

	memset(&g_addr, 0, sizeof(g_addr));
	g_addr.sin_family = AF_INET;
	g_addr.sin_port = htons(port);
	g_addr.sin_addr.s_addr = inet_addr(host);

	tlog("tcp: %s:%d bekleniyor (pspkit kopru)", host, port);
	while (tcp_reconnect() < 0)
		sceKernelDelayThread(1000 * 1000);

	t->name = "tcp";
	snprintf(t->where, sizeof(t->where), "%s:%d", host, port);
	t->write = tcp_write;
	t->read = tcp_read;
	t->write_bulk = tcp_write;
	t->reconnect = tcp_reconnect;
	return 0;
}

static int read_tcp_cfg(const char *argv0, char *host, int hostlen, int *port)
{
	char path[256], fmt[16];
	FILE *f;
	int ok;

	sibling_path(path, sizeof(path), argv0, "tcp.cfg");
	if (!(f = fopen(path, "r")))
		return 0;
	snprintf(fmt, sizeof(fmt), "%%%ds %%d", hostlen - 1);
	ok = fscanf(f, fmt, host, port) == 2;
	fclose(f);
	return ok;
}

int pk_transport_open(pk_transport_t *t, const char *argv0, pk_log_fn log)
{
	char host[32] = PK_TCP_DEFAULT_HOST;
	int port = PK_TCP_DEFAULT_PORT, fatal = 0, ret;

	g_log = log;
	if (read_tcp_cfg(argv0, host, sizeof(host), &port)) {
		tlog("tcp.cfg: %s:%d, USB atlaniyor", host, port);
		return tcp_open(t, host, port);
	}
	ret = usb_open(t, argv0, &fatal);
	if (ret >= 0 || fatal)
		return ret;
	tlog("USB yok, TCP deneniyor");
	return tcp_open(t, host, port);
}
