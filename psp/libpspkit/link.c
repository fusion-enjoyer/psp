#include <pspkernel.h>
#include <pspdisplay.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "link.h"

#define RETRY_US 1000000

static pk_transport_t *g_t;
static pk_line_fn g_on_line;
static pk_event_fn g_on_up;
static int g_up;
static long long g_next_retry;

static char g_rx[2048];
static int g_rx_len;

static long long now_us(void)
{
	return (long long)sceKernelGetSystemTimeWide();
}

static void set_down(void)
{
	g_up = 0;
	g_rx_len = 0;
	g_next_retry = now_us() + RETRY_US;
}

void pk_link_init(pk_transport_t *t, pk_line_fn on_line, pk_event_fn on_up)
{
	g_t = t;
	g_on_line = on_line;
	g_on_up = on_up;
	g_up = 1;
	if (g_on_up)
		g_on_up();
}

int pk_link_up(void)
{
	return g_up;
}

const pk_transport_t *pk_link_transport(void)
{
	return g_t;
}

int pk_link_send(const char *fmt, ...)
{
	char buf[256];
	va_list ap;
	int n;

	if (!g_up)
		return -1;
	va_start(ap, fmt);
	n = vsnprintf(buf, sizeof(buf) - 1, fmt, ap);
	va_end(ap);
	if (n < 0)
		return -1;
	if (n > (int)sizeof(buf) - 2)
		n = sizeof(buf) - 2;
	buf[n++] = '\n';
	if (g_t->write(buf, n) != n) {
		set_down();
		return -1;
	}
	return 0;
}

void pk_link_poll(int timeout_us)
{
	int n, i, start;

	if (!g_up) {
		if (now_us() >= g_next_retry) {
			if (g_t->reconnect() == 0) {
				g_up = 1;
				if (g_on_up)
					g_on_up();
			} else {
				g_next_retry = now_us() + RETRY_US;
			}
		}
		if (!g_up) {
			sceKernelDelayThread(timeout_us);
			return;
		}
	}

	n = g_t->read(g_rx + g_rx_len, sizeof(g_rx) - 1 - g_rx_len, timeout_us);
	if (n < 0) {
		set_down();
		return;
	}
	if (n == 0)
		return;
	g_rx_len += n;

	start = 0;
	for (i = 0; i < g_rx_len; i++) {
		if (g_rx[i] == '\n') {
			g_rx[i] = 0;
			if (i > start && g_rx[i - 1] == '\r')
				g_rx[i - 1] = 0;
			g_on_line(g_rx + start);
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

void pk_link_send_frame(void)
{
	void *top;
	int bufw, fmt, bpp, y;

	if (sceDisplayGetFrameBuf(&top, &bufw, &fmt, PSP_DISPLAY_SETBUF_IMMEDIATE) < 0 || !top)
		return;
	bpp = fmt == PSP_DISPLAY_PIXEL_FORMAT_8888 ? 4 : 2;
	if (pk_link_send("frame %d %d %d %d", 480, 272, fmt, 480 * 272 * bpp) < 0)
		return;
	/* Uncached alias so we read what the display actually shows. */
	for (y = 0; y < 272; y++)
		if (g_t->write_bulk((unsigned char *)((unsigned int)top | 0x40000000) + y * bufw * bpp,
				    480 * bpp) < 0) {
			set_down();
			return;
		}
}
