/* Line protocol on top of a transport: "<cmd> <args...>\n" both ways. */
#ifndef PSPKIT_LINK_H
#define PSPKIT_LINK_H

#include "transport.h"

typedef void (*pk_line_fn)(char *line);
typedef void (*pk_event_fn)(void);

/* on_line gets every complete line from the bridge (without '\n').
   on_up runs whenever the link comes (back) up, e.g. to send "hello". */
void pk_link_init(pk_transport_t *t, pk_line_fn on_line, pk_event_fn on_up);
int  pk_link_send(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
/* Reads for up to timeout_us, dispatches lines, retries a lost link once a second. */
void pk_link_poll(int timeout_us);
int  pk_link_up(void);
const pk_transport_t *pk_link_transport(void);
/* Streams the displayed framebuffer ("frame <w> <h> <fmt> <bytes>" + pixels). */
void pk_link_send_frame(void);

#endif
