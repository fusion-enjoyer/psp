/*
 * pspkit M0: USB spike.
 *
 * Proves the PSP <-> PC link over usbhostfs async channel 4, which
 * usbhostfs_pc exposes on the PC as localhost TCP port 10004.
 *
 *   PSP -> PC   hello m0 <proto> <fw>
 *               ping <seq> <t_us>          every 500 ms
 *               btn <name> <t_us>          on confirm button
 *               bulk <mode> <bytes>        followed by <bytes> raw bytes
 *   PC -> PSP   pong <seq> <t_us>
 *               ack <name> <t_us>
 *               rate <mode> <bytes> <ms>
 *               msg <text>
 *
 * Round-trip times are measured on the PSP with the echoed timestamp.
 */
#include <pspkernel.h>
#include <pspdebug.h>
#include <pspdisplay.h>
#include <pspctrl.h>
#include <pspusb.h>
#include <pspusbbus.h>
#include <psputility.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "usbasync.h"

PSP_MODULE_INFO("pspkit_m0", PSP_MODULE_USER, 0, 1);
PSP_MAIN_THREAD_ATTR(PSP_THREAD_ATTR_USER | PSP_THREAD_ATTR_VFPU);

#define printf pspDebugScreenPrintf

#define CHAN              ASYNC_USER
#define PORT              (10000 + CHAN)
#define PING_INTERVAL_US  500000
#define ASYNC_TEST_BYTES  (64 * 1024)
#define BULK_TEST_BYTES   (256 * 1024)
#define SCE_KERNEL_ERROR_EXCLUSIVE_LOAD 0x80020139

static struct AsyncEndpoint g_endp;
static unsigned char g_bulk[BULK_TEST_BYTES] __attribute__((aligned(64)));

static char g_rx[1024];
static int  g_rx_len;

static unsigned int g_seq;
static int g_rtt_last = -1, g_rtt_min = -1, g_rtt_max = -1, g_rtt_count;
static long long g_rtt_sum;
static int g_btn_rtt = -1;
static char g_rate_line[96] = "-";
static char g_psp_rate_line[96] = "-";
static char g_msg[64] = "-";
static int g_pongs;

static int exit_callback(int arg1, int arg2, void *common)
{
	sceKernelExitGame();
	return 0;
}

static int callback_thread(SceSize args, void *argp)
{
	int cbid = sceKernelCreateCallback("Exit Callback", exit_callback, NULL);
	sceKernelRegisterExitCallback(cbid);
	sceKernelSleepThreadCB();
	return 0;
}

static void setup_callbacks(void)
{
	int thid = sceKernelCreateThread("update_thread", callback_thread, 0x11, 0xFA0, 0, 0);
	if (thid >= 0)
		sceKernelStartThread(thid, 0, 0);
}

static long long now_us(void)
{
	return (long long)sceKernelGetSystemTimeWide();
}

static int confirm_is_circle(void)
{
	int val = 1; /* PSP_UTILITY_ACCEPT_CROSS */
	sceUtilityGetSystemParamInt(PSP_SYSTEMPARAM_ID_INT_UNKNOWN, &val);
	return val == 0; /* 0 = circle confirms (Asia/Japan) */
}

static void send_line(const char *line)
{
	usbAsyncWrite(CHAN, line, strlen(line));
}

static void fail(const char *step, int ret)
{
	printf("\n  HATA: %s -> 0x%08X\n", step, ret);
	printf("  Bu kodu docs/m0.md'deki tabloyla karsilastir.\n");
	printf("  Cikmak icin HOME.\n");
	sceKernelSleepThreadCB();
}

/* Load usbhostfs.prx from the EBOOT's folder and start the USB drivers. */
static int start_usb(const char *argv0)
{
	char path[256];
	char *slash;
	SceUID mod;
	int ret, status;

	strncpy(path, argv0, sizeof(path) - 32);
	path[sizeof(path) - 32] = 0;
	slash = strrchr(path, '/');
	strcpy(slash ? slash + 1 : path, "usbhostfs.prx");

	printf("  usbhostfs.prx yukleniyor...\n  %s\n", path);
	mod = kuKernelLoadModule(path, 0, NULL);
	if (mod < 0 && (unsigned)mod != SCE_KERNEL_ERROR_EXCLUSIVE_LOAD) {
		fail("kuKernelLoadModule", mod);
		return -1;
	}
	if (mod >= 0) {
		ret = sceKernelStartModule(mod, 0, NULL, &status, NULL);
		if (ret < 0) {
			fail("sceKernelStartModule", ret);
			return -1;
		}
	}
	printf("  modul: 0x%08X\n", mod);

	ret = sceUsbStart(PSP_USBBUS_DRIVERNAME, 0, 0);
	printf("  sceUsbStart(bus): 0x%08X\n", ret);
	ret = sceUsbStart(HOSTFSDRIVER_NAME, 0, 0);
	printf("  sceUsbStart(hostfs): 0x%08X\n", ret);
	ret = sceUsbActivate(HOSTFSDRIVER_PID);
	printf("  sceUsbActivate(0x1C9): 0x%08X\n", ret);
	if (ret < 0) {
		fail("sceUsbActivate", ret);
		return -1;
	}

	ret = usbAsyncRegister(CHAN, &g_endp);
	printf("  usbAsyncRegister(%d): %d\n", CHAN, ret);
	if (ret < 0) {
		fail("usbAsyncRegister", ret);
		return -1;
	}
	return 0;
}

static void handle_line(char *line)
{
	unsigned int seq;
	long long t;
	char name[16];

	if (sscanf(line, "pong %u %lld", &seq, &t) == 2) {
		int rtt = (int)(now_us() - t);
		g_rtt_last = rtt;
		if (g_rtt_min < 0 || rtt < g_rtt_min) g_rtt_min = rtt;
		if (rtt > g_rtt_max) g_rtt_max = rtt;
		g_rtt_sum += rtt;
		g_rtt_count++;
		g_pongs++;
	} else if (sscanf(line, "ack %15s %lld", name, &t) == 2) {
		g_btn_rtt = (int)(now_us() - t);
	} else if (strncmp(line, "rate ", 5) == 0) {
		snprintf(g_rate_line, sizeof(g_rate_line), "%s", line + 5);
	} else if (strncmp(line, "msg ", 4) == 0) {
		snprintf(g_msg, sizeof(g_msg), "%s", line + 4);
	}
}

static void poll_rx(int timeout_us)
{
	int n, i, start;

	n = usbAsyncReadWithTimeout(CHAN, (unsigned char *)g_rx + g_rx_len,
				    sizeof(g_rx) - 1 - g_rx_len, timeout_us);
	if (n <= 0)
		return;
	g_rx_len += n;

	start = 0;
	for (i = 0; i < g_rx_len; i++) {
		if (g_rx[i] == '\n') {
			g_rx[i] = 0;
			handle_line(g_rx + start);
			start = i + 1;
		}
	}
	if (start > 0) {
		memmove(g_rx, g_rx + start, g_rx_len - start);
		g_rx_len -= start;
	} else if (g_rx_len >= (int)sizeof(g_rx) - 1) {
		g_rx_len = 0; /* line too long, drop it */
	}
}

static void throughput_test(const char *mode, int bytes)
{
	char line[64];
	long long t0, t1;
	int ret;

	snprintf(line, sizeof(line), "bulk %s %d\n", mode, bytes);
	send_line(line);

	t0 = now_us();
	if (strcmp(mode, "async") == 0)
		ret = usbAsyncWrite(CHAN, g_bulk, bytes);
	else
		ret = usbWriteBulkData(CHAN, g_bulk, bytes);
	t1 = now_us();

	if (ret != bytes) {
		snprintf(g_psp_rate_line, sizeof(g_psp_rate_line), "%s: hata %d", mode, ret);
		return;
	}
	snprintf(g_psp_rate_line, sizeof(g_psp_rate_line), "%s %d B, %d ms, %d KB/s",
		 mode, bytes, (int)((t1 - t0) / 1000),
		 (int)((long long)bytes * 1000000 / 1024 / (t1 - t0 + 1)));
}

static void draw(int circle_confirms)
{
	const char *confirm = circle_confirms ? "O" : "X";

	pspDebugScreenSetXY(0, 12);
	printf("  Kanal %d  ->  PC localhost:%d\n\n", CHAN, PORT);
	printf("  ping gonderilen: %-8u pong alinan: %-8d\n", g_seq, g_pongs);
	if (g_rtt_count > 0)
		printf("  RTT ms  son %-6.1f min %-6.1f ort %-6.1f max %-6.1f\n",
		       g_rtt_last / 1000.0f, g_rtt_min / 1000.0f,
		       (float)(g_rtt_sum / g_rtt_count) / 1000.0f, g_rtt_max / 1000.0f);
	else
		printf("  RTT ms  (PC'de tools/m0/echo.py calisiyor mu?)          \n");
	if (g_btn_rtt >= 0)
		printf("  Tus -> PC -> PSP: %.1f ms                              \n", g_btn_rtt / 1000.0f);
	else
		printf("  Tus -> PC -> PSP: -  (%s'e bas)                         \n", confirm);
	printf("\n  PSP olcumu : %-50s\n", g_psp_rate_line);
	printf("  PC olcumu  : %-50s\n", g_rate_line);
	printf("  PC mesaji  : %-50s\n", g_msg);
	printf("\n  %s: tus gecikmesi  TRIANGLE: async 64KB  SQUARE: bulk 256KB\n", confirm);
	printf("  SELECT: istatistik sifirla   HOME: cikis\n");
}

int main(int argc, char *argv[])
{
	SceCtrlData pad;
	unsigned int prev = 0, pressed;
	long long next_ping;
	char line[96];
	int circle, i;

	setup_callbacks();
	pspDebugScreenInit();
	sceCtrlSetSamplingCycle(0);
	sceCtrlSetSamplingMode(PSP_CTRL_MODE_DIGITAL);

	printf("\n  pspkit M0 - USB testi\n\n");
	if (argc < 1 || start_usb(argv[0]) < 0)
		return 0;

	for (i = 0; i < BULK_TEST_BYTES; i++)
		g_bulk[i] = (unsigned char)(i & 0xFF);

	printf("\n  PC bekleniyor: usbhostfs_pc calistir...\n");
	usbWaitForConnect();
	printf("  USB bagli.\n");

	circle = confirm_is_circle();
	snprintf(line, sizeof(line), "hello m0 0 fw=%08X\n", sceKernelDevkitVersion());
	send_line(line);

	next_ping = now_us();
	for (;;) {
		long long t = now_us();

		if (t >= next_ping) {
			snprintf(line, sizeof(line), "ping %u %lld\n", ++g_seq, t);
			send_line(line);
			next_ping = t + PING_INTERVAL_US;
		}

		sceCtrlPeekBufferPositive(&pad, 1);
		pressed = pad.Buttons & ~prev;
		prev = pad.Buttons;

		if (pressed & (circle ? PSP_CTRL_CIRCLE : PSP_CTRL_CROSS)) {
			snprintf(line, sizeof(line), "btn confirm %lld\n", now_us());
			send_line(line);
		}
		if (pressed & PSP_CTRL_TRIANGLE)
			throughput_test("async", ASYNC_TEST_BYTES);
		if (pressed & PSP_CTRL_SQUARE)
			throughput_test("bulk", BULK_TEST_BYTES);
		if (pressed & PSP_CTRL_SELECT) {
			g_seq = 0; g_pongs = 0;
			g_rtt_last = g_rtt_min = g_rtt_max = g_btn_rtt = -1;
			g_rtt_count = 0; g_rtt_sum = 0;
		}

		poll_rx(16000); /* ~60 Hz loop, also our frame pacing */
		draw(circle);
	}

	return 0;
}
