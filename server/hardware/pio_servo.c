/*
 * pio_servo - hardware-timed RC-servo pulses on ANY RP1 GPIO (Pi 5 / CM5)
 * using the RP1 PIO block through piolib (/dev/pio0).
 *
 * Why: the damper servo (MG90S) sits on GPIO8, which has no hardware PWM.
 * Software-timed PWM (lgpio tx_pwm) jitters by tens of microseconds under
 * Linux scheduling; on a 500..2400 us servo scale 1 deg ~= 10.6 us, so the
 * servo visibly shivers and sometimes never reaches its target. A PIO state
 * machine clocks the pulse edges itself (1 us resolution, zero jitter) - the
 * same quality of signal an Arduino's Timer1 gives.
 *
 * Signal model: each 20 ms period is ONE pulse of `pulse_us` at the ACTIVE
 * level followed by the IDLE level. Normal polarity: idle LOW, pulse HIGH.
 * --inverted: idle HIGH, pulse LOW (the sCure board buffers the servo line
 * through an inverting transistor stage, Q16, so the servo sees normal
 * pulses).
 *
 * The PIO program emits one pulse per 32-bit word pulled from its TX FIFO
 * and then BLOCKS at the idle level until the next word - so stopping the
 * feed ("release") always finishes the pulse in flight cleanly; the line is
 * never cut mid-pulse. While holding, this process keeps the 4-deep FIFO
 * topped up (~80 ms of buffered pulses), so its own scheduling jitter never
 * reaches the servo.
 *
 * Usage:   pio_servo <gpio> [--inverted] [--period-us N] [--pio IDX]
 *          pio_servo <gpio> [--inverted] --test <pulse_us> <hold_ms>
 *
 * stdin protocol (one command per line):
 *     P <pulse_us>   drive: emit pulses of <pulse_us> until R/Q/next P
 *     R              release: stop feeding, line goes to the idle level
 *     Q              quit (release first)
 * stdout: "READY gpio=<n> sm=<n> inverted=<0|1> period_us=<n>" once, then
 *         "OK" or "ERR <reason>" per command.
 *
 * Build: see build-pio-servo.sh (needs the piolib sources from
 *        https://github.com/raspberrypi/utils - BSD-3-Clause).
 */

#include <errno.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "piolib.h"

/* ------------------------------------------------------------------------
 * PIO program (hand-assembled, .side_set 1 non-optional, 1 instruction = 1 us
 * with clkdiv 200 on the 200 MHz RP1 sys clock):
 *
 *     .wrap_target
 *   0: pull block        side IDLE   ; wait for a word, line at idle level
 *   1: out  x, 16        side IDLE   ; x = pulse_us - 1
 *   2: out  y, 16        side IDLE   ; y = period_us - pulse_us - 4
 *   3: jmp  x--, 3       side ACTIVE ; ACTIVE for (x+1) us
 *   4: jmp  y--, 4       side IDLE   ; IDLE   for (y+1) us
 *     .wrap
 *
 * Period = 1 + 1 + 1 + (x+1) + (y+1) = pulse_us + y + 4 = period_us.
 * Word layout (shift right): low 16 bits = x, high 16 bits = y.
 * ---------------------------------------------------------------------- */
#define SIDE(v) ((uint16_t)((v) ? 0x1000 : 0x0000))

static uint16_t prog_instr[5];

static void build_program(bool inverted)
{
    const uint16_t idle = SIDE(inverted ? 1 : 0);
    const uint16_t active = SIDE(inverted ? 0 : 1);
    prog_instr[0] = 0x80A0 | idle;    /* pull block          */
    prog_instr[1] = 0x6030 | idle;    /* out x, 16           */
    prog_instr[2] = 0x6050 | idle;    /* out y, 16           */
    prog_instr[3] = 0x0043 | active;  /* jmp x--, 3          */
    prog_instr[4] = 0x0084 | idle;    /* jmp y--, 4          */
}

static const struct pio_program servo_program = {
    .instructions = prog_instr,
    .length = 5,
    .origin = -1,
};

/* ------------------------------------------------------------------------ */
static PIO g_pio = NULL;
static int g_sm = -1;
static uint g_offset = 0;
static uint g_gpio = 8;
static bool g_inverted = false;
static uint32_t g_period_us = 20000;
static uint32_t g_pulse_us = 0;       /* 0 = released */
static volatile sig_atomic_t g_quit = 0;

static void on_signal(int sig) { (void)sig; g_quit = 1; }

static int idle_level(void) { return g_inverted ? 1 : 0; }

static void set_idle_line(void)
{
    pio_sm_set_pins_with_mask(g_pio, g_sm, (uint32_t)idle_level() << g_gpio,
                              1u << g_gpio);
}

static uint32_t make_word(uint32_t pulse_us)
{
    uint32_t x = pulse_us - 1;
    uint32_t y = g_period_us - pulse_us - 4;
    return (y << 16) | (x & 0xFFFF);
}

/* Keep the TX FIFO full while driving; each word = one 20 ms period. */
static void feed(void)
{
    if (g_pulse_us == 0)
        return;
    uint32_t w = make_word(g_pulse_us);
    while (!pio_sm_is_tx_fifo_full(g_pio, g_sm))
        pio_sm_put(g_pio, g_sm, w);
}

static const char *cmd_drive(uint32_t pulse_us)
{
    if (pulse_us < 100 || pulse_us + 8 > g_period_us)
        return "pulse out of range";
    if (pulse_us != g_pulse_us) {
        /* Drop queued pulses of the OLD width so the new one takes effect
         * within one period; the pulse in flight completes untouched. */
        pio_sm_clear_fifos(g_pio, g_sm);
        g_pulse_us = pulse_us;
    }
    feed();
    return NULL;
}

static void cmd_release(void)
{
    g_pulse_us = 0;
    pio_sm_clear_fifos(g_pio, g_sm);   /* SM finishes its pulse, then idles */
}

static int setup(uint pio_idx)
{
    build_program(g_inverted);
    g_pio = pio_open(pio_idx);
    if (!g_pio || PIO_IS_ERR(g_pio)) {
        fprintf(stderr, "pio_open(%u) failed (err %d) - is /dev/pio%u present and "
                "are we root/gpio?\n", pio_idx,
                g_pio ? (int)PIO_ERR_VAL(g_pio) : -1, pio_idx);
        g_pio = NULL;
        return -1;
    }
    g_sm = pio_claim_unused_sm(g_pio, false);
    if (g_sm < 0) {
        fprintf(stderr, "no free PIO state machine\n");
        return -1;
    }
    if (!pio_can_add_program(g_pio, &servo_program)) {
        fprintf(stderr, "no room for PIO program\n");
        return -1;
    }
    g_offset = pio_add_program(g_pio, &servo_program);

    pio_sm_config c = pio_get_default_sm_config();
    sm_config_set_wrap(&c, g_offset + 0, g_offset + 4);
    sm_config_set_sideset(&c, 1, false, false);
    sm_config_set_sideset_pins(&c, g_gpio);
    sm_config_set_set_pins(&c, g_gpio, 1);
    sm_config_set_out_shift(&c, true, false, 32);   /* shift right, no autopull */
    sm_config_set_clkdiv(&c, 200.0f);               /* 200 MHz / 200 = 1 us/instr */

    pio_gpio_init(g_pio, g_gpio);
    pio_sm_set_consecutive_pindirs(g_pio, g_sm, g_gpio, 1, true);
    pio_sm_init(g_pio, g_sm, g_offset, &c);
    set_idle_line();
    pio_sm_set_enabled(g_pio, g_sm, true);          /* blocks at 'pull' = idle */
    return 0;
}

static void teardown(void)
{
    if (!g_pio)
        return;
    cmd_release();
    /* Let a pulse in flight finish (max one period) before leaving. */
    usleep(g_period_us + 1000);
    pio_sm_set_enabled(g_pio, g_sm, false);
    set_idle_line();
    pio_remove_program(g_pio, &servo_program, g_offset);
    pio_sm_unclaim(g_pio, g_sm);
    pio_close(g_pio);
    g_pio = NULL;
}

static void usage(void)
{
    fprintf(stderr,
            "usage: pio_servo <gpio> [--inverted] [--period-us N] [--pio IDX]\n"
            "       pio_servo <gpio> [--inverted] --test <pulse_us> <hold_ms>\n");
}

int main(int argc, char **argv)
{
    uint pio_idx = 0;
    long test_pulse = -1, test_hold = 0;

    if (argc < 2) { usage(); return 2; }
    g_gpio = (uint)strtoul(argv[1], NULL, 0);
    for (int i = 2; i < argc; i++) {
        if (!strcmp(argv[i], "--inverted")) g_inverted = true;
        else if (!strcmp(argv[i], "--period-us") && i + 1 < argc)
            g_period_us = (uint32_t)strtoul(argv[++i], NULL, 0);
        else if (!strcmp(argv[i], "--pio") && i + 1 < argc)
            pio_idx = (uint)strtoul(argv[++i], NULL, 0);
        else if (!strcmp(argv[i], "--test") && i + 2 < argc) {
            test_pulse = strtol(argv[++i], NULL, 0);
            test_hold = strtol(argv[++i], NULL, 0);
        } else { usage(); return 2; }
    }
    if (g_period_us < 2000 || g_period_us > 65000) {
        fprintf(stderr, "period must be 2000..65000 us\n");
        return 2;
    }

    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    signal(SIGHUP, on_signal);
    signal(SIGPIPE, SIG_IGN);

    if (setup(pio_idx) < 0)
        return 1;

    if (test_pulse >= 0) {                 /* one-shot: drive, hold, release */
        const char *err = cmd_drive((uint32_t)test_pulse);
        if (err) { fprintf(stderr, "ERR %s\n", err); teardown(); return 1; }
        long waited = 0;
        while (waited < test_hold && !g_quit) {
            feed();
            usleep(20000);
            waited += 20;
        }
        teardown();
        return 0;
    }

    printf("READY gpio=%u sm=%d inverted=%d period_us=%u\n",
           g_gpio, g_sm, g_inverted ? 1 : 0, g_period_us);
    fflush(stdout);

    char line[128];
    struct pollfd pfd = { .fd = STDIN_FILENO, .events = POLLIN };
    while (!g_quit) {
        feed();
        int r = poll(&pfd, 1, 20);         /* top up the FIFO every 20 ms */
        if (r < 0) {
            if (errno == EINTR) continue;
            break;
        }
        if (r == 0) continue;
        if (pfd.revents & (POLLHUP | POLLERR | POLLNVAL))
            break;                         /* parent went away: release+exit */
        if (!fgets(line, sizeof line, stdin))
            break;
        char *p = line;
        while (*p == ' ' || *p == '\t') p++;
        const char *err = NULL;
        switch (*p) {
        case 'P': case 'p': {
            char *end = NULL;
            long v = strtol(p + 1, &end, 10);
            if (end == p + 1 || v <= 0) err = "bad pulse";
            else err = cmd_drive((uint32_t)v);
            break;
        }
        case 'R': case 'r': cmd_release(); break;
        case 'Q': case 'q': g_quit = 1; break;
        case '\n': case '\0': continue;
        default: err = "unknown command"; break;
        }
        if (err) printf("ERR %s\n", err); else printf("OK\n");
        fflush(stdout);
    }
    teardown();
    return 0;
}
