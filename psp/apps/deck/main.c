/*
 * pspkit Deck: a Stream Deck style macro pad on the PSP.
 *
 * Every tile is bound to a physical button and drawn where that button sits
 * on the PSP: d-pad cross on the left, face buttons on the right, SELECT and
 * START in the middle. Holding L, R or both switches to another layer, so 10
 * buttons x 4 layers = 40 actions, all one press away. The analog stick is a
 * dial (volume, scroll) chosen per layer. The bridge on the PC owns the
 * config and runs the actions; this app only draws and reports input.
 *
 *   PSP -> bridge  hello deck <proto> <transport> fw=<hex> circle=<0|1>
 *                  press <layer> <button> <t_us>
 *                  analog <layer> <x> <y>       -127..127, while held
 *                  ping <t_us>
 *   bridge -> PSP  clear
 *                  tile <layer> <button> <rrggbb> <flags> <label>   flags: 1 active
 *                  analog <layer> <label>
 *                  title <text>
 *                  toast <rrggbb> <text>
 *                  ack <t_us>                   echo of press, for latency
 *                  shot                         send a screenshot
 *                  sim <layer> <button>         act as if pressed (testing)
 *
 * Labels use '|' for line breaks. Layers: normal, l, r, lr.
 */
#include <pspkernel.h>
#include <pspctrl.h>
#include <psppower.h>
#include <psputility.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gfx.h"
#include "link.h"
#include "transport.h"

PSP_MODULE_INFO("pspkit_deck", PSP_MODULE_USER, 1, 0);
PSP_MAIN_THREAD_ATTR(PSP_THREAD_ATTR_USER | PSP_THREAD_ATTR_VFPU);
PSP_HEAP_SIZE_KB(-1024);

#define PROTO_VERSION     1
#define NLAYER            4
#define ANALOG_DEAD       40
#define ANALOG_PERIOD_US  100000
#define PING_PERIOD_US    2000000
#define FLASH_US          150000
#define POWER_TICK_US     5000000
#define LABEL_ADV         7        /* px per character in tile labels */

enum { B_UP, B_DOWN, B_LEFT, B_RIGHT, B_TRIANGLE, B_CIRCLE, B_CROSS, B_SQUARE,
       B_START, B_SELECT, NBTN };

static const char *BTN_NAME[NBTN] = { "up", "down", "left", "right", "triangle",
	"circle", "cross", "square", "start", "select" };
static const unsigned BTN_MASK[NBTN] = { PSP_CTRL_UP, PSP_CTRL_DOWN, PSP_CTRL_LEFT,
	PSP_CTRL_RIGHT, PSP_CTRL_TRIANGLE, PSP_CTRL_CIRCLE, PSP_CTRL_CROSS,
	PSP_CTRL_SQUARE, PSP_CTRL_START, PSP_CTRL_SELECT };
static const int BTN_GLYPH[NBTN] = { GLYPH_UP, GLYPH_DOWN, GLYPH_LEFT, GLYPH_RIGHT,
	GLYPH_TRIANGLE, GLYPH_CIRCLE, GLYPH_CROSS, GLYPH_SQUARE, GLYPH_START, GLYPH_SELECT };
static const char *LAYER_NAME[NLAYER] = { "normal", "l", "r", "lr" };
static const char *LAYER_TITLE[NLAYER] = { "NORMAL", "L", "R", "L+R" };

/* Controller-shaped layout: 3x3 cross/diamond clusters with a middle column. */
#define TOP_H   22
#define BOT_Y   250
#define TILE_W  64
#define TILE_H  70
#define GAP     4
#define ROW(r)  (26 + (r) * (TILE_H + GAP))
#define LCOL(c) (6 + (c) * (TILE_W + GAP))
#define RCOL(c) (274 + (c) * (TILE_W + GAP))
#define MID_X   212
#define MID_W   56

typedef struct { int x, y, w, h; } rect_t;

static const rect_t BTN_RECT[NBTN] = {
	[B_UP]       = { LCOL(1), ROW(0), TILE_W, TILE_H },
	[B_DOWN]     = { LCOL(1), ROW(2), TILE_W, TILE_H },
	[B_LEFT]     = { LCOL(0), ROW(1), TILE_W, TILE_H },
	[B_RIGHT]    = { LCOL(2), ROW(1), TILE_W, TILE_H },
	[B_TRIANGLE] = { RCOL(1), ROW(0), TILE_W, TILE_H },
	[B_CROSS]    = { RCOL(1), ROW(2), TILE_W, TILE_H },
	[B_SQUARE]   = { RCOL(0), ROW(1), TILE_W, TILE_H },
	[B_CIRCLE]   = { RCOL(2), ROW(1), TILE_W, TILE_H },
	[B_SELECT]   = { MID_X, ROW(0), MID_W, TILE_H },
	[B_START]    = { MID_X, ROW(2), MID_W, TILE_H },
};

#define COL_BG     RGB(0x12, 0x14, 0x19)
#define COL_BAR    RGB(0x1B, 0x1E, 0x25)
#define COL_DIM    RGB(0x2A, 0x2E, 0x37)
#define COL_DIM2   RGB(0x4A, 0x50, 0x5C)
#define COL_TEXT   RGB(0xEE, 0xF0, 0xF4)
#define COL_MUTED  RGB(0x8A, 0x90, 0x9C)
#define COL_OK     RGB(0x3D, 0xDC, 0x84)
#define COL_BAD    RGB(0xF0, 0x4E, 0x4E)
#define COL_WHITE  RGB(0xFF, 0xFF, 0xFF)
#define COL_BLACK  RGB(0x10, 0x10, 0x10)

typedef struct {
	int used;
	u32 color;
	int flags;
	char label[48];
} tile_t;

static pk_transport_t g_t;
static tile_t g_tiles[NLAYER][NBTN];
static char g_analog[NLAYER][24];
static char g_title[32] = "Deck";
static char g_toast[64];
static u32 g_toast_color;
static long long g_toast_until;
static long long g_flash_until[NBTN];
static int g_latency_us = -1;
static int g_circle_confirms;
static int g_layer;

static char g_log[12][80];
static int g_log_n;

static long long now_us(void)
{
	return (long long)sceKernelGetSystemTimeWide();
}

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

static int find_name(const char **names, int n, const char *s)
{
	int i;
	for (i = 0; i < n; i++)
		if (strcmp(names[i], s) == 0)
			return i;
	return -1;
}

static void toast(u32 color, const char *text)
{
	snprintf(g_toast, sizeof(g_toast), "%s", text);
	g_toast_color = color;
	g_toast_until = now_us() + 2500000;
}

/* ---- boot screen ---- */

static void boot_log(const char *msg)
{
	int i;

	if (g_log_n == 12) {
		memmove(g_log[0], g_log[1], sizeof(g_log[0]) * 11);
		g_log_n = 11;
	}
	snprintf(g_log[g_log_n++], sizeof(g_log[0]), "%s", msg);

	gfx_clear(COL_BG);
	gfx_text(16, 16, "pspkit Deck", COL_TEXT, 2);
	for (i = 0; i < g_log_n; i++)
		gfx_text(16, 52 + i * 14, g_log[i], i == g_log_n - 1 ? COL_TEXT : COL_MUTED, 1);
	gfx_flip();
}

/* ---- protocol ---- */

static void send_hello(void)
{
	pk_link_send("hello deck %d %s fw=%08X circle=%d", PROTO_VERSION, g_t.name,
		     sceKernelDevkitVersion(), g_circle_confirms);
}

static void fire(int layer, int b)
{
	g_flash_until[b] = now_us() + FLASH_US;
	if (!g_tiles[layer][b].used) {
		toast(COL_MUTED, "Bu tusa aksiyon atanmamis");
		return;
	}
	if (pk_link_send("press %s %s %lld", LAYER_NAME[layer], BTN_NAME[b], now_us()) < 0)
		toast(COL_BAD, "Kopru yok, basis gonderilemedi");
}

static void on_line(char *line)
{
	char cmd[12], a[12], b[12];
	unsigned color;
	int flags, n = 0, l, bt;
	long long t;

	if (sscanf(line, "%11s", cmd) != 1)
		return;

	if (strcmp(cmd, "tile") == 0 &&
	    sscanf(line, "tile %11s %11s %6x %d %n", a, b, &color, &flags, &n) == 4 && n > 0) {
		l = find_name(LAYER_NAME, NLAYER, a);
		bt = find_name(BTN_NAME, NBTN, b);
		if (l < 0 || bt < 0)
			return;
		g_tiles[l][bt].used = 1;
		g_tiles[l][bt].color = gfx_hex(color);
		g_tiles[l][bt].flags = flags;
		snprintf(g_tiles[l][bt].label, sizeof(g_tiles[l][bt].label), "%s", line + n);
	} else if (strcmp(cmd, "clear") == 0) {
		memset(g_tiles, 0, sizeof(g_tiles));
		memset(g_analog, 0, sizeof(g_analog));
	} else if (strcmp(cmd, "analog") == 0 && sscanf(line, "analog %11s %n", a, &n) == 1 && n > 0) {
		if ((l = find_name(LAYER_NAME, NLAYER, a)) >= 0)
			snprintf(g_analog[l], sizeof(g_analog[l]), "%s", line + n);
	} else if (strcmp(cmd, "title") == 0 && strlen(line) > 6) {
		snprintf(g_title, sizeof(g_title), "%s", line + 6);
	} else if (strcmp(cmd, "toast") == 0 && sscanf(line, "toast %6x %n", &color, &n) == 1 && n > 0) {
		toast(gfx_hex(color), line + n);
	} else if (strcmp(cmd, "ack") == 0 && sscanf(line, "ack %lld", &t) == 1) {
		g_latency_us = (int)(now_us() - t);
	} else if (strcmp(cmd, "shot") == 0) {
		pk_link_send_frame();
	} else if (strcmp(cmd, "sim") == 0 && sscanf(line, "sim %11s %11s", a, b) == 2) {
		l = find_name(LAYER_NAME, NLAYER, a);
		bt = find_name(BTN_NAME, NBTN, b);
		if (l >= 0 && bt >= 0) {
			g_layer = l;
			fire(l, bt);
		}
	}
}

/* ---- drawing ---- */

/* Splits a label on '|' and wraps each part to max_chars; returns line count. */
static int wrap_label(const char *label, char out[][12], int max_lines, int max_chars)
{
	char buf[48], *part, *save = NULL;
	int n = 0;

	snprintf(buf, sizeof(buf), "%s", label);
	for (part = strtok_r(buf, "|", &save); part && n < max_lines; part = strtok_r(NULL, "|", &save)) {
		while (*part && n < max_lines) {
			int len = strlen(part), cut = len;
			if (len > max_chars) {
				cut = max_chars;
				while (cut > 0 && part[cut] != ' ')
					cut--;
				if (cut == 0)
					cut = max_chars;
			}
			snprintf(out[n++], 12, "%.*s", cut, part);
			part += cut;
			while (*part == ' ')
				part++;
		}
	}
	return n;
}

static void draw_tile(int b)
{
	const rect_t *r = &BTN_RECT[b];
	tile_t *t = &g_tiles[g_layer][b];
	int pressed = now_us() < g_flash_until[b];
	char lines[3][12];
	int n, i, ty, max_chars = (r->w - 4) / LABEL_ADV;
	u32 bg, fg, accent;

	if (!t->used) {
		gfx_frame(r->x, r->y, r->w, r->h, 1, pressed ? COL_MUTED : COL_DIM);
		gfx_glyph(BTN_GLYPH[b], r->x + r->w / 2, r->y + r->h / 2, 14, COL_DIM2);
		return;
	}

	if (t->flags & 1) {
		bg = t->color;
		fg = gfx_is_light(t->color) ? COL_BLACK : COL_WHITE;
		accent = fg;
	} else {
		bg = gfx_mix(t->color, COL_BG, 64);
		fg = COL_TEXT;
		accent = t->color;
	}
	if (pressed)
		bg = gfx_mix(COL_WHITE, bg, 70);

	gfx_rect(r->x, r->y, r->w, r->h, bg);
	gfx_frame(r->x, r->y, r->w, r->h, pressed ? 3 : 2, pressed ? COL_WHITE : t->color);
	if (b == B_START || b == B_SELECT)
		gfx_glyph(BTN_GLYPH[b], r->x + r->w / 2, r->y + 10, 10, accent);
	else
		gfx_glyph(BTN_GLYPH[b], r->x + 11, r->y + 11, 10, accent);

	n = wrap_label(t->label, lines, 3, max_chars);
	ty = r->y + 26 + (3 - n) * 6;
	for (i = 0; i < n; i++)
		gfx_text_center_adv(r->x + r->w / 2, ty + i * 12, lines[i], fg, 1, LABEL_ADV);
}

static void draw_frame(void)
{
	const pk_transport_t *t = pk_link_transport();
	char buf[48];
	int b, up = pk_link_up();
	long long now = now_us();

	gfx_clear(COL_BG);

	/* top bar: title, link, latency, layer chips */
	gfx_rect(0, 0, GFX_W, TOP_H, COL_BAR);
	gfx_text(8, 7, g_title, COL_TEXT, 1);
	gfx_rect(170, 8, 6, 6, up ? COL_OK : COL_BAD);
	if (up && g_latency_us >= 0)
		snprintf(buf, sizeof(buf), "%s  %d ms", t->name, (g_latency_us + 500) / 1000);
	else
		snprintf(buf, sizeof(buf), "%s", up ? t->name : "baglanti yok");
	gfx_text(182, 7, buf, up ? COL_MUTED : COL_BAD, 1);
	gfx_rect(420, 4, 24, 14, (g_layer & 1) ? COL_TEXT : COL_DIM);
	gfx_text_center(432, 7, "L", (g_layer & 1) ? COL_BLACK : COL_MUTED, 1);
	gfx_rect(448, 4, 24, 14, (g_layer & 2) ? COL_TEXT : COL_DIM);
	gfx_text_center(460, 7, "R", (g_layer & 2) ? COL_BLACK : COL_MUTED, 1);

	for (b = 0; b < NBTN; b++)
		draw_tile(b);

	/* middle: current layer */
	gfx_frame(MID_X, ROW(1), MID_W, TILE_H, 1, COL_DIM);
	gfx_text_center(MID_X + MID_W / 2, ROW(1) + 12, "katman", COL_MUTED, 1);
	gfx_text_center(MID_X + MID_W / 2, ROW(1) + 32, LAYER_TITLE[g_layer],
			COL_TEXT, g_layer == 0 ? 1 : 2);

	/* left center: what the analog stick does on this layer */
	gfx_circle(LCOL(1) + TILE_W / 2, ROW(1) + 24, 12, COL_DIM2);
	gfx_circle(LCOL(1) + TILE_W / 2, ROW(1) + 24, 5, COL_DIM2);
	gfx_text_center(LCOL(1) + TILE_W / 2, ROW(1) + 46,
			g_analog[g_layer][0] ? g_analog[g_layer] : "-", COL_MUTED, 1);

	/* right center: brand */
	gfx_text_center(RCOL(1) + TILE_W / 2, ROW(1) + 31, "pspkit", COL_DIM2, 1);

	/* bottom bar: toast, link warning or hints */
	gfx_rect(0, BOT_Y, GFX_W, GFX_H - BOT_Y, COL_BAR);
	if (!up)
		gfx_text(8, BOT_Y + 8, "Kopru baglantisi yok, yeniden deneniyor...", COL_BAD, 1);
	else if (now < g_toast_until)
		gfx_text(8, BOT_Y + 8, g_toast, g_toast_color, 1);
	else
		gfx_text(8, BOT_Y + 8, "L / R / L+R basili tut: katman degistir", COL_MUTED, 1);
}

/* ---- main ---- */

static int confirm_is_circle(void)
{
	int val = PSP_UTILITY_ACCEPT_CROSS;
	sceUtilityGetSystemParamInt(PSP_SYSTEMPARAM_ID_INT_UNKNOWN, &val);
	return val == PSP_UTILITY_ACCEPT_CIRCLE;
}

int main(int argc, char *argv[])
{
	SceCtrlData pad;
	unsigned prev = 0, pressed;
	long long next_analog = 0, next_ping = 0, next_power = 0;
	int b;

	setup_callbacks();
	gfx_init();
	sceCtrlSetSamplingCycle(0);
	sceCtrlSetSamplingMode(PSP_CTRL_MODE_ANALOG);
	g_circle_confirms = confirm_is_circle();

	boot_log("Kopruye baglaniliyor...");
	if (argc < 1 || pk_transport_open(&g_t, argv[0], boot_log) < 0) {
		boot_log("Baglanti acilamadi. Cikmak icin HOME.");
		sceKernelSleepThreadCB();
		return 0;
	}
	pk_link_init(&g_t, on_line, send_hello);

	for (;;) {
		long long now = now_us();

		sceCtrlPeekBufferPositive(&pad, 1);
		g_layer = ((pad.Buttons & PSP_CTRL_LTRIGGER) ? 1 : 0) |
			  ((pad.Buttons & PSP_CTRL_RTRIGGER) ? 2 : 0);
		pressed = pad.Buttons & ~prev;
		prev = pad.Buttons;
		for (b = 0; b < NBTN; b++)
			if (pressed & BTN_MASK[b])
				fire(g_layer, b);

		if (now >= next_analog) {
			int ax = (int)pad.Lx - 128, ay = (int)pad.Ly - 128;
			if (abs(ax) > ANALOG_DEAD || abs(ay) > ANALOG_DEAD) {
				pk_link_send("analog %s %d %d", LAYER_NAME[g_layer],
					     ax > 127 ? 127 : ax, ay > 127 ? 127 : ay);
				next_analog = now + ANALOG_PERIOD_US;
			}
		}
		if (now >= next_ping) {
			pk_link_send("ping %lld", now);
			next_ping = now + PING_PERIOD_US;
		}
		/* A desk appliance should not dim or sleep while it is in use. */
		if (now >= next_power) {
			scePowerTick(PSP_POWER_TICK_ALL);
			next_power = now + POWER_TICK_US;
		}

		pk_link_poll(1000);
		draw_frame();
		gfx_flip();
	}
	return 0;
}
