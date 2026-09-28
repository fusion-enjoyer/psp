/*
 * pspkit M0: link spike.
 *
 * Proves the PSP <-> bridge link and measures it. USB (usbhostfs async
 * channel 4 -> usbhostfs_pc -> localhost:10004) is tried first; when USB is
 * not available (PPSSPP, no KUBridge) the app falls back to TCP. A tcp.cfg
 * file next to the EBOOT ("<host> <port>") forces TCP.
 *
 *   PSP -> PC   hello m0 <proto> <transport> fw=<hex>
 *               ping <seq> <t_us>          every 500 ms
 *               btn <name> <t_us>          on confirm button
 *               bulk <mode> <bytes>        followed by <bytes> raw bytes
 *               report <key=value ...>     after the automatic self-test
 *               frame <w> <h> <fmt> <bytes> followed by <bytes> of pixels
 *   PC -> PSP   pong <seq> <t_us>
 *               ack <name> <t_us>
 *               rate <text>
 *               msg <text>
 *               shot                       request a screenshot
 *
 * Round-trip times are measured on the PSP with the echoed timestamp.
 */
#include <pspkernel.h>
#include <pspdebug.h>
#include <pspdisplay.h>
#include <pspctrl.h>
#include <psputility.h>
#include <stdio.h>
#include <string.h>

#include "transport.h"

PSP_MODULE_INFO("pspkit_m0", PSP_MODULE_USER, 0, 1);
PSP_MAIN_THREAD_ATTR(PSP_THREAD_ATTR_USER | PSP_THREAD_ATTR_VFPU);
PSP_HEAP_SIZE_KB(-1024);

#define printf pspDebugScreenPrintf

#define PING_INTERVAL_US  500000
#define SELFTEST_AFTER    10       /* pongs before the automatic self-test */
#define STREAM_TEST_BYTES (64 * 1024)
#define BULK_TEST_BYTES   (256 * 1024)
#define STATUS_ROW        3

static transport_t g_t;
static unsigned char g_bulk[BULK_TEST_BYTES] __attribute__((aligned(64)));

static char g_rx[1024];
static int  g_rx_len;
static int  g_link_lost;

static unsigned int g_seq;
static int g_rtt_last = -1, g_rtt_min = -1, g_rtt_max = -1, g_rtt_count;
static long long g_rtt_sum;
static int g_btn_rtt = -1;
static int g_pongs;
static int g_stream_kbs = -1, g_bulk_kbs = -1;
static char g_rate_line[96] = "-";
static char g_psp_rate_line[96] = "-";
static char g_msg[64] = "-";
static int g_selftest_state; /* 0 waiting, 1 button sent, 2 done */

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
	int val = PSP_UTILITY_ACCEPT_CROSS;
	sceUtilityGetSystemParamInt(PSP_SYSTEMPARAM_ID_INT_UNKNOWN, &val);
	return val == PSP_UTILITY_ACCEPT_CIRCLE; /* Asia/Japan default */
}

static void send_line(const char *line)
{
	if (g_t.write(line, strlen(line)) < 0)
		g_link_lost = 1;
}

static void send_button(void)
{
	char line[48];
	snprintf(line, sizeof(line), "btn confirm %lld\n", now_us());
	send_line(line);
}

static void halt(const char *why)
{
	printf("\n  HATA: %s\n  docs/m0.md 'Bir sey ters giderse' bolumune bak.\n  Cikmak icin HOME.\n", why);
	sceKernelSleepThreadCB();
}

/* tcp.cfg next to the EBOOT forces TCP to "<host> <port>". */
static int read_tcp_cfg(const char *argv0, char *host, int hostlen, int *port)
{
	char path[256], fmt[16];
	char *slash;
	FILE *f;
	int ok;

	strncpy(path, argv0, sizeof(path) - 16);
	path[sizeof(path) - 16] = 0;
	slash = strrchr(path, '/');
	strcpy(slash ? slash + 1 : path, "tcp.cfg");
	if (!(f = fopen(path, "r")))
		return 0;
	snprintf(fmt, sizeof(fmt), "%%%ds %%d", hostlen - 1);
	ok = fscanf(f, fmt, host, port) == 2;
	fclose(f);
	return ok;
}

/* Streams the visible framebuffer to the bridge, which saves it as PNG. */
static void send_frame(void)
{
	void *top;
	int bufw, fmt, bpp, y;
	char line[64];

	if (sceDisplayGetFrameBuf(&top, &bufw, &fmt, PSP_DISPLAY_SETBUF_IMMEDIATE) < 0 || !top)
		return;
	bpp = fmt == PSP_DISPLAY_PIXEL_FORMAT_8888 ? 4 : 2;
	snprintf(line, sizeof(line), "frame %d %d %d %d\n", 480, 272, fmt, 480 * 272 * bpp);
	send_line(line);
	/* Uncached alias so we read what the display actually shows. */
	for (y = 0; y < 272; y++)
		g_t.write_bulk((unsigned char *)((unsigned int)top | 0x40000000) + y * bufw * bpp, 480 * bpp);
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
	} else if (strcmp(line, "shot") == 0) {
		send_frame();
	}
}

static void poll_rx(int timeout_us)
{
	int n, i, start;

	n = g_t.read(g_rx + g_rx_len, sizeof(g_rx) - 1 - g_rx_len, timeout_us);
	if (n < 0) {
		g_link_lost = 1;
		return;
	}
	if (n == 0)
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

/* "stream" uses the small-message path, "bulk" the large-transfer path. */
static int throughput_test(const char *mode, int bytes)
{
	char line[64];
	long long t0, t1;
	int ret, kbs;

	snprintf(line, sizeof(line), "bulk %s %d\n", mode, bytes);
	send_line(line);

	t0 = now_us();
	if (strcmp(mode, "stream") == 0)
		ret = g_t.write(g_bulk, bytes);
	else
		ret = g_t.write_bulk(g_bulk, bytes);
	t1 = now_us();

	if (ret != bytes) {
		snprintf(g_psp_rate_line, sizeof(g_psp_rate_line), "%s: hata %d", mode, ret);
		return -1;
	}
	/* On TCP send() returns once the data is buffered, so only the PC can
	   time the transfer; on USB the write completes on the wire. */
	if (strcmp(g_t.name, "tcp") == 0) {
		snprintf(g_psp_rate_line, sizeof(g_psp_rate_line), "%s %d B gonderildi (hiz: PC olcumu)", mode, bytes);
		return -1;
	}
	kbs = (int)((long long)bytes * 1000000 / 1024 / (t1 - t0 + 1));
	snprintf(g_psp_rate_line, sizeof(g_psp_rate_line), "%s %d B, %d ms, %d KB/s",
		 mode, bytes, (int)((t1 - t0) / 1000), kbs);
	return kbs;
}

static void selftest_step(void)
{
	char line[160];

	if (g_selftest_state == 0 && g_pongs >= SELFTEST_AFTER) {
		send_button();
		g_selftest_state = 1;
	} else if (g_selftest_state == 1 && g_btn_rtt >= 0) {
		g_stream_kbs = throughput_test("stream", STREAM_TEST_BYTES);
		g_bulk_kbs = throughput_test("bulk", BULK_TEST_BYTES);
		snprintf(line, sizeof(line),
			 /* *_send_kbs is how fast the PSP handed data off; on TCP that is
			    just the socket buffer, so the PC-side rate is the real one. */
			 "report transport=%s pongs=%d rtt_min_us=%d rtt_avg_us=%d rtt_max_us=%d btn_us=%d stream_send_kbs=%d bulk_send_kbs=%d\n",
			 g_t.name, g_pongs, g_rtt_min, (int)(g_rtt_sum / g_rtt_count), g_rtt_max,
			 g_btn_rtt, g_stream_kbs, g_bulk_kbs);
		send_line(line);
		g_selftest_state = 2;
	}
}

static void draw(int circle_confirms)
{
	const char *confirm = circle_confirms ? "O" : "X";

	pspDebugScreenSetXY(0, STATUS_ROW);
	printf("  Baglanti: %s  %-40s\n\n", g_t.name, g_t.where);
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
	printf("\n  PSP gonderim: %-49s\n", g_psp_rate_line);
	printf("  PC olcumu  : %-50s\n", g_rate_line);
	printf("  PC mesaji  : %-50s\n", g_msg);
	printf("  Oz-test    : %-50s\n", g_selftest_state == 2 ? "bitti, rapor PC'ye gonderildi" :
	       g_selftest_state == 1 ? "calisiyor..." : "10 pong sonra otomatik");
	printf("  %-60s\n", g_link_lost ? "BAGLANTI KOPTU" : "");
	printf("\n  %s: tus gecikmesi  TRIANGLE: stream 64KB  SQUARE: bulk 256KB\n", confirm);
	printf("  SELECT: istatistik sifirla   HOME: cikis\n");
}

int main(int argc, char *argv[])
{
	SceCtrlData pad;
	unsigned int prev = 0, pressed;
	long long next_ping;
	char line[96], host[32] = TCP_DEFAULT_HOST;
	int port = TCP_DEFAULT_PORT, circle, i, fatal = 0, ret;

	setup_callbacks();
	pspDebugScreenInit();
	sceCtrlSetSamplingCycle(0);
	sceCtrlSetSamplingMode(PSP_CTRL_MODE_DIGITAL);

	printf("\n  pspkit M0 - baglanti testi\n\n");
	if (argc < 1) {
		halt("argv[0] yok");
		return 0;
	}

	if (read_tcp_cfg(argv[0], host, sizeof(host), &port)) {
		printf("  tcp.cfg bulundu, USB atlaniyor\n");
		ret = transport_tcp_open(&g_t, host, port);
	} else if ((ret = transport_usb_open(&g_t, argv[0], &fatal)) < 0 && !fatal) {
		printf("  USB yok (PPSSPP ya da KUBridge yok), TCP deneniyor\n");
		ret = transport_tcp_open(&g_t, host, port);
	}
	if (ret < 0) {
		snprintf(line, sizeof(line), "%s acilamadi (0x%08X)", fatal ? "USB" : "TCP", ret);
		halt(line);
		return 0;
	}

	for (i = 0; i < BULK_TEST_BYTES; i++)
		g_bulk[i] = (unsigned char)(i & 0xFF);

	pspDebugScreenClear();
	printf("\n  pspkit M0 - baglanti testi\n");
	circle = confirm_is_circle();
	snprintf(line, sizeof(line), "hello m0 0 %s fw=%08X\n", g_t.name, sceKernelDevkitVersion());
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

		if (pressed & (circle ? PSP_CTRL_CIRCLE : PSP_CTRL_CROSS))
			send_button();
		if (pressed & PSP_CTRL_TRIANGLE)
			throughput_test("stream", STREAM_TEST_BYTES);
		if (pressed & PSP_CTRL_SQUARE)
			throughput_test("bulk", BULK_TEST_BYTES);
		if (pressed & PSP_CTRL_SELECT) {
			g_seq = 0; g_pongs = 0;
			g_rtt_last = g_rtt_min = g_rtt_max = g_btn_rtt = -1;
			g_rtt_count = 0; g_rtt_sum = 0;
		}

		poll_rx(16000); /* ~60 Hz loop, also our frame pacing */
		selftest_step();
		draw(circle);
	}

	return 0;
}
