/* Minimal double-buffered software renderer: 480x272, 32-bit ABGR in VRAM. */
#ifndef PSPKIT_GFX_H
#define PSPKIT_GFX_H

#include <psptypes.h>

#define GFX_W 480
#define GFX_H 272
#define RGB(r, g, b) (0xFF000000u | ((u32)(b) << 16) | ((u32)(g) << 8) | (u32)(r))

/* Mixes a over b; t is 0..256 (256 = all a). */
u32  gfx_mix(u32 a, u32 b, int t);
/* 0xRRGGBB (as sent by the bridge) to a display color. */
u32  gfx_hex(u32 rrggbb);
int  gfx_is_light(u32 color);

void gfx_init(void);
void gfx_flip(void);          /* shows the drawn frame, waits for vblank */
void gfx_clear(u32 color);
void gfx_rect(int x, int y, int w, int h, u32 color);
void gfx_frame(int x, int y, int w, int h, int thick, u32 color);
void gfx_line(int x0, int y0, int x1, int y1, u32 color);
void gfx_circle(int cx, int cy, int r, u32 color);
void gfx_tri(int x0, int y0, int x1, int y1, int x2, int y2, u32 color); /* filled */

/* 8x8 font scaled by an integer; returns the advance in pixels. */
int  gfx_text(int x, int y, const char *s, u32 color, int scale);
int  gfx_text_width(const char *s, int scale);
void gfx_text_center(int cx, int y, const char *s, u32 color, int scale);
/* Same with a custom advance per character (the font leaves the last column
   mostly empty, so 7 px packs one more character into narrow tiles). */
int  gfx_text_adv(int x, int y, const char *s, u32 color, int scale, int adv);
void gfx_text_center_adv(int cx, int y, const char *s, u32 color, int scale, int adv);

/* PSP button glyphs, centered, sized to fit an s x s box. */
enum { GLYPH_UP, GLYPH_DOWN, GLYPH_LEFT, GLYPH_RIGHT, GLYPH_TRIANGLE,
       GLYPH_CIRCLE, GLYPH_CROSS, GLYPH_SQUARE, GLYPH_START, GLYPH_SELECT };
void gfx_glyph(int glyph, int cx, int cy, int s, u32 color);

#endif
