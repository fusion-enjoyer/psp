#include <pspkernel.h>
#include <pspdebug.h>
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
#include <stdio.h>
#include <string.h>

#include "transport.h"
#include "usbasync.h"

#define printf pspDebugScreenPrintf

#define CHAN ASYNC_USER
#define SCE_KERNEL_ERROR_EXCLUSIVE_LOAD 0x80020139
#define APCTL_TIMEOUT_US (10 * 1000 * 1000)
#define USB_CONNECT_TIMEOUT_US (15 * 1000 * 1000)

/* ---- USB: usbhostfs async channel ---- */

static struct AsyncEndpoint g_endp;

static int usb_write(const void *data, int len)
{
	return usbAsyncWrite(CHAN, data, len);
}

static int usb_read(void *data, int len, int timeout_us)
{
	int n = usbAsyncReadWithTimeout(CHAN, data, len, timeout_us);
	return n < 0 ? 0 : n; /* a timeout is reported as an error code */
}

static int usb_write_bulk(const void *data, int len)
{
	return usbWriteBulkData(CHAN, data, len);
}

int transport_usb_open(transport_t *t, const char *argv0, int *fatal)
{
	char path[256];
	char *slash;
	SceUID mod;
	int ret, status;
	long long deadline;

	*fatal = 0;
	strncpy(path, argv0, sizeof(path) - 32);
	path[sizeof(path) - 32] = 0;
	slash = strrchr(path, '/');
	strcpy(slash ? slash + 1 : path, "usbhostfs.prx");

	printf("  [usb] %s\n", path);
	mod = kuKernelLoadModule(path, 0, NULL);
	printf("  [usb] kuKernelLoadModule: 0x%08X\n", mod);
	/* A missing KUBridge (no CFW, PPSSPP) shows up as an error or 0 here. */
	if (mod <= 0 && (unsigned)mod != SCE_KERNEL_ERROR_EXCLUSIVE_LOAD)
		return -1;
	if (mod > 0) {
		ret = sceKernelStartModule(mod, 0, NULL, &status, NULL);
		printf("  [usb] sceKernelStartModule: 0x%08X\n", ret);
		if (ret < 0)
			return -1;
	}

	*fatal = 1;
	ret = sceUsbStart(PSP_USBBUS_DRIVERNAME, 0, 0);
	printf("  [usb] sceUsbStart(bus): 0x%08X\n", ret);
	ret = sceUsbStart(HOSTFSDRIVER_NAME, 0, 0);
	printf("  [usb] sceUsbStart(hostfs): 0x%08X\n", ret);
	ret = sceUsbActivate(HOSTFSDRIVER_PID);
	printf("  [usb] sceUsbActivate(0x1C9): 0x%08X\n", ret);
	if (ret < 0)
		return ret;

	ret = usbAsyncRegister(CHAN, &g_endp);
	printf("  [usb] usbAsyncRegister(%d): 0x%08X\n", CHAN, ret);
	if (ret < 0)
		return ret;

	/* usbWaitForConnect() blocks forever when no PC ever answers (PPSSPP
	   emulates the USB stack but has no host side), so poll instead: a
	   zero-length write fails until usbhostfs_pc has connected. */
	printf("  [usb] PC bekleniyor (%d sn): usbhostfs_pc calistir...\n", USB_CONNECT_TIMEOUT_US / 1000000);
	deadline = (long long)sceKernelGetSystemTimeWide() + USB_CONNECT_TIMEOUT_US;
	while (usbAsyncWrite(CHAN, "", 0) < 0) {
		if ((long long)sceKernelGetSystemTimeWide() >= deadline) {
			printf("  [usb] PC baglanmadi, USB kapatiliyor\n");
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
	snprintf(t->where, sizeof(t->where), "kanal %d -> PC localhost:%d", CHAN, 10000 + CHAN);
	t->write = usb_write;
	t->read = usb_read;
	t->write_bulk = usb_write_bulk;
	return 0;
}

/* ---- TCP ---- */

static int g_sock = -1;

static int tcp_write(const void *data, int len)
{
	const char *p = data;
	int sent = 0;

	while (sent < len) {
		int n = send(g_sock, p + sent, len - sent, 0);
		if (n <= 0)
			return sent ? sent : -1;
		sent += n;
	}
	return sent;
}

static int tcp_read(void *data, int len, int timeout_us)
{
	fd_set set;
	struct timeval tv;
	int n;

	FD_ZERO(&set);
	FD_SET(g_sock, &set);
	tv.tv_sec = timeout_us / 1000000;
	tv.tv_usec = timeout_us % 1000000;
	if (select(g_sock + 1, &set, NULL, NULL, &tv) <= 0)
		return 0;
	n = recv(g_sock, data, len, 0);
	return n == 0 ? -1 : n; /* 0 from recv means the bridge closed */
}

static int apctl_connect(void)
{
	int state = 0, last = -1, ret;
	long long deadline = (long long)sceKernelGetSystemTimeWide() + APCTL_TIMEOUT_US;

	ret = sceNetApctlConnect(1);
	printf("  [tcp] sceNetApctlConnect(1): 0x%08X\n", ret);
	if (ret < 0)
		return ret;

	while ((long long)sceKernelGetSystemTimeWide() < deadline) {
		ret = sceNetApctlGetState(&state);
		if (ret < 0)
			return ret;
		if (state != last) {
			printf("  [tcp] erisim noktasi durumu %d/4\n", state);
			last = state;
		}
		if (state == PSP_NET_APCTL_STATE_GOT_IP)
			return 0;
		sceKernelDelayThread(50 * 1000);
	}
	printf("  [tcp] erisim noktasi zaman asimi\n");
	return -1;
}

int transport_tcp_open(transport_t *t, const char *host, int port)
{
	struct sockaddr_in addr;
	int ret, one = 1;

	sceUtilityLoadNetModule(PSP_NET_MODULE_COMMON);
	sceUtilityLoadNetModule(PSP_NET_MODULE_INET);

	ret = pspSdkInetInit();
	printf("  [tcp] pspSdkInetInit: 0x%08X\n", ret);
	if (ret < 0)
		return ret;
	if ((ret = apctl_connect()) < 0)
		return ret;

	g_sock = socket(PF_INET, SOCK_STREAM, 0);
	if (g_sock < 0) {
		printf("  [tcp] socket: %d\n", g_sock);
		return -1;
	}
	setsockopt(g_sock, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));

	memset(&addr, 0, sizeof(addr));
	addr.sin_family = AF_INET;
	addr.sin_port = htons(port);
	addr.sin_addr.s_addr = inet_addr(host);

	printf("  [tcp] %s:%d baglaniliyor (kopru: echo.py --listen)\n", host, port);
	while (connect(g_sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
		/* Keep retrying so the app can be started before the bridge. */
		close(g_sock);
		sceKernelDelayThread(1000 * 1000);
		g_sock = socket(PF_INET, SOCK_STREAM, 0);
		setsockopt(g_sock, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
	}

	t->name = "tcp";
	snprintf(t->where, sizeof(t->where), "%s:%d", host, port);
	t->write = tcp_write;
	t->read = tcp_read;
	t->write_bulk = tcp_write;
	return 0;
}
