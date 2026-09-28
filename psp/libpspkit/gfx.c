#include <pspdisplay.h>
#include <string.h>

#include "gfx.h"

#define BUF_W    512
#define VRAM     0x04000000u
#define UNCACHED 0x40000000u
#define FRAME_SZ (BUF_W * GFX_H * 4)

extern u8 msx[]; /* pspsdk debug font, 8x8, bit 7 = leftmost pixel */

static int g_draw; /* index of the buffer we draw into */
static u32 *g_px;

static u32 *buffer(int i)
{
	return (u32 *)(VRAM + UNCACHED + i * FRAME_SZ);
}

u32 gfx_mix(u32 a, u32 b, int t)
{
	u32 r = (((a & 0xFF) * t) + ((b & 0xFF) * (256 - t))) >> 8;
	u32 g = ((((a >> 8) & 0xFF) * t) + (((b >> 8) & 0xFF) * (256 - t))) >> 8;
	u32 bl = ((((a >> 16) & 0xFF) * t) + (((b >> 16) & 0xFF) * (256 - t))) >> 8;
	return 0xFF000000u | (bl << 16) | (g << 8) | r;
}

u32 gfx_hex(u32 rrggbb)
{
	return RGB((rrggbb >> 16) & 0xFF, (rrggbb >> 8) & 0xFF, rrggbb & 0xFF);
}

int gfx_is_light(u32 c)
{
	int r = c & 0xFF, g = (c >> 8) & 0xFF, b = (c >> 16) & 0xFF;
	return (r * 299 + g * 587 + b * 114) / 1000 > 150;
}

void gfx_init(void)
{
	sceDisplaySetMode(0, GFX_W, GFX_H);
	memset(buffer(0), 0, FRAME_SZ);
	memset(buffer(1), 0, FRAME_SZ);
	sceDisplaySetFrameBuf((void *)VRAM, BUF_W, PSP_DISPLAY_PIXEL_FORMAT_8888, PSP_DISPLAY_SETBUF_NEXTFRAME);
	g_draw = 1;
	g_px = buffer(g_draw);
}

void gfx_flip(void)
{
	sceDisplaySetFrameBuf((void *)(VRAM + g_draw * FRAME_SZ), BUF_W,
			      PSP_DISPLAY_PIXEL_FORMAT_8888, PSP_DISPLAY_SETBUF_NEXTFRAME);
	sceDisplayWaitVblankStart();
	g_draw ^= 1;
	g_px = buffer(g_draw);
}

static inline void plot(int x, int y, u32 c)
{
	if ((unsigned)x < GFX_W && (unsigned)y < GFX_H)
		g_px[y * BUF_W + x] = c;
}

void gfx_clear(u32 color)
{
	gfx_rect(0, 0, GFX_W, GFX_H, color);
}

void gfx_rect(int x, int y, int w, int h, u32 color)
{
	int i, j;

	if (x < 0) { w += x; x = 0; }
	if (y < 0) { h += y; y = 0; }
	if (x + w > GFX_W) w = GFX_W - x;
	if (y + h > GFX_H) h = GFX_H - y;
	for (j = 0; j < h; j++) {
		u32 *row = g_px + (y + j) * BUF_W + x;
		for (i = 0; i < w; i++)
			row[i] = color;
	}
}

void gfx_frame(int x, int y, int w, int h, int t, u32 color)
{
	gfx_rect(x, y, w, t, color);
	gfx_rect(x, y + h - t, w, t, color);
	gfx_rect(x, y + t, t, h - 2 * t, color);
	gfx_rect(x + w - t, y + t, t, h - 2 * t, color);
}

void gfx_line(int x0, int y0, int x1, int y1, u32 color)
{
	int dx = x1 > x0 ? x1 - x0 : x0 - x1, sx = x0 < x1 ? 1 : -1;
	int dy = y1 > y0 ? y0 - y1 : y1 - y0, sy = y0 < y1 ? 1 : -1;
	int err = dx + dy, e2;

	for (;;) {
		plot(x0, y0, color);
		if (x0 == x1 && y0 == y1)
			break;
		e2 = 2 * err;
		if (e2 >= dy) { err += dy; x0 += sx; }
		if (e2 <= dx) { err += dx; y0 += sy; }
	}
}

void gfx_circle(int cx, int cy, int r, u32 color)
{
	int x = r, y = 0, err = 1 - r;

	while (x >= y) {
		plot(cx + x, cy + y, color); plot(cx - x, cy + y, color);
		plot(cx + x, cy - y, color); plot(cx - x, cy - y, color);
		plot(cx + y, cy + x, color); plot(cx - y, cy + x, color);
		plot(cx + y, cy - x, color); plot(cx - y, cy - x, color);
		y++;
		if (err < 0) {
			err += 2 * y + 1;
		} else {
			x--;
			err += 2 * (y - x) + 1;
		}
	}
}

static int edge(int ax, int ay, int bx, int by, int px, int py)
{
	return (bx - ax) * (py - ay) - (by - ay) * (px - ax);
}

void gfx_tri(int x0, int y0, int x1, int y1, int x2, int y2, u32 color)
{
	int minx = x0, maxx = x0, miny = y0, maxy = y0, x, y;
	int area = edge(x0, y0, x1, y1, x2, y2);

	if (area == 0)
		return;
	if (x1 < minx) minx = x1;
	if (x2 < minx) minx = x2;
	if (x1 > maxx) maxx = x1;
	if (x2 > maxx) maxx = x2;
	if (y1 < miny) miny = y1;
	if (y2 < miny) miny = y2;
	if (y1 > maxy) maxy = y1;
	if (y2 > maxy) maxy = y2;
	for (y = miny; y <= maxy; y++)
		for (x = minx; x <= maxx; x++) {
			int w0 = edge(x1, y1, x2, y2, x, y);
			int w1 = edge(x2, y2, x0, y0, x, y);
			int w2 = edge(x0, y0, x1, y1, x, y);
			if (area > 0 ? (w0 >= 0 && w1 >= 0 && w2 >= 0) : (w0 <= 0 && w1 <= 0 && w2 <= 0))
				plot(x, y, color);
		}
}

int gfx_text(int x, int y, const char *s, u32 color, int scale)
{
	return gfx_text_adv(x, y, s, color, scale, 8 * scale);
}

int gfx_text_adv(int x, int y, const char *s, u32 color, int scale, int adv)
{
	int x0 = x, i, j;

	for (; *s; s++, x += adv) {
		const u8 *f = &msx[(u8)*s * 8];
		for (j = 0; j < 8; j++)
			for (i = 0; i < 8; i++)
				if (f[j] & (0x80 >> i))
					gfx_rect(x + i * scale, y + j * scale, scale, scale, color);
	}
	return x - x0;
}

int gfx_text_width(const char *s, int scale)
{
	return (int)strlen(s) * 8 * scale;
}

void gfx_text_center(int cx, int y, const char *s, u32 color, int scale)
{
	gfx_text(cx - gfx_text_width(s, scale) / 2, y, s, color, scale);
}

void gfx_text_center_adv(int cx, int y, const char *s, u32 color, int scale, int adv)
{
	int n = (int)strlen(s);
	gfx_text_adv(cx - (n * adv - (adv - 7 * scale)) / 2, y, s, color, scale, adv);
}

void gfx_glyph(int glyph, int cx, int cy, int s, u32 c)
{
	int h = s / 2, k;

	switch (glyph) {
	case GLYPH_UP:    gfx_tri(cx, cy - h, cx - h, cy + h / 2, cx + h, cy + h / 2, c); break;
	case GLYPH_DOWN:  gfx_tri(cx, cy + h, cx + h, cy - h / 2, cx - h, cy - h / 2, c); break;
	case GLYPH_LEFT:  gfx_tri(cx - h, cy, cx + h / 2, cy + h, cx + h / 2, cy - h, c); break;
	case GLYPH_RIGHT: gfx_tri(cx + h, cy, cx - h / 2, cy - h, cx - h / 2, cy + h, c); break;
	case GLYPH_TRIANGLE:
		for (k = 0; k < 2; k++) {
			gfx_line(cx, cy - h + k, cx - h + k, cy + h - 1 - k, c);
			gfx_line(cx, cy - h + k, cx + h - k, cy + h - 1 - k, c);
			gfx_line(cx - h + k, cy + h - 1 - k, cx + h - k, cy + h - 1 - k, c);
		}
		break;
	case GLYPH_CIRCLE:
		gfx_circle(cx, cy, h, c);
		gfx_circle(cx, cy, h - 1, c);
		break;
	case GLYPH_CROSS:
		for (k = -1; k <= 0; k++) {
			gfx_line(cx - h + k + 1, cy - h, cx + h + k, cy + h - 1, c);
			gfx_line(cx + h + k, cy - h, cx - h + k + 1, cy + h - 1, c);
		}
		break;
	case GLYPH_SQUARE:
		gfx_frame(cx - h, cy - h, s, s, 2, c);
		break;
	case GLYPH_START:
		gfx_text_center(cx, cy - 4, "STA", c, 1);
		break;
	case GLYPH_SELECT:
		gfx_text_center(cx, cy - 4, "SEL", c, 1);
		break;
	}
}
