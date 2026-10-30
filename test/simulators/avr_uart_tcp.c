/*
 * avr_uart_tcp: run an AVR ELF in simavr with UART0 on a TCP socket, paced to real time.
 *   avr_uart_tcp <mcu> <freq_hz> <firmware.elf> <port>
 * One client at a time; a new connection replaces the old one. Like Renode's
 * CreateServerSocketTerminal, so the PC tool reaches it as socket://localhost:<port>.
 */
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#include <simavr/avr_uart.h>
#include <simavr/sim_avr.h>
#include <simavr/sim_elf.h>
#include <simavr/sim_irq.h>

static int client = -1;
static int xon = 1;
static unsigned char inbuf[4096];
static size_t in_head, in_tail;

static void uart_out(struct avr_irq_t *irq, uint32_t value, void *param)
{
    (void)irq; (void)param;
    unsigned char b = (unsigned char)value;
    if (client >= 0 && send(client, &b, 1, MSG_NOSIGNAL) < 0) {
        close(client);
        client = -1;
    }
}

static void uart_xon(struct avr_irq_t *irq, uint32_t value, void *param) { (void)irq; (void)value; (void)param; xon = 1; }
static void uart_xoff(struct avr_irq_t *irq, uint32_t value, void *param) { (void)irq; (void)value; (void)param; xon = 0; }

static double now(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

int main(int argc, char **argv)
{
    if (argc != 5) {
        fprintf(stderr, "usage: %s <mcu> <freq_hz> <firmware.elf> <port>\n", argv[0]);
        return 2;
    }
    signal(SIGPIPE, SIG_IGN);
    elf_firmware_t fw = {0};
    if (elf_read_firmware(argv[3], &fw)) { fprintf(stderr, "cannot read %s\n", argv[3]); return 1; }
    avr_t *avr = avr_make_mcu_by_name(argv[1]);
    if (!avr) { fprintf(stderr, "unknown mcu %s\n", argv[1]); return 1; }
    avr_init(avr);
    avr_load_firmware(avr, &fw);
    avr->frequency = strtoul(argv[2], NULL, 10);
    avr->log = 0;

    uint32_t flags = 0;
    avr_ioctl(avr, AVR_IOCTL_UART_SET_FLAGS('0'), &flags);
    avr_irq_t *in = avr_io_getirq(avr, AVR_IOCTL_UART_GETIRQ('0'), UART_IRQ_INPUT);
    avr_irq_register_notify(avr_io_getirq(avr, AVR_IOCTL_UART_GETIRQ('0'), UART_IRQ_OUTPUT), uart_out, NULL);
    avr_irq_register_notify(avr_io_getirq(avr, AVR_IOCTL_UART_GETIRQ('0'), UART_IRQ_OUT_XON), uart_xon, NULL);
    avr_irq_register_notify(avr_io_getirq(avr, AVR_IOCTL_UART_GETIRQ('0'), UART_IRQ_OUT_XOFF), uart_xoff, NULL);

    int server = socket(AF_INET, SOCK_STREAM, 0);
    int one = 1;
    setsockopt(server, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    struct sockaddr_in addr = {.sin_family = AF_INET, .sin_port = htons(atoi(argv[4])),
                               .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
    if (bind(server, (struct sockaddr *)&addr, sizeof addr) || listen(server, 1)) { perror("bind"); return 1; }
    fcntl(server, F_SETFL, O_NONBLOCK);
    fprintf(stderr, "avr_uart_tcp: %s @ %lu Hz, UART0 on port %s\n", argv[1], (unsigned long)avr->frequency, argv[4]);

    double start = now();
    for (unsigned long step = 0;; step++) {
        int state = avr_run(avr);
        if (state == cpu_Done || state == cpu_Crashed) { fprintf(stderr, "avr_uart_tcp: cpu stopped (%d)\n", state); return 1; }
        if (step % 256)
            continue;
        int c = accept(server, NULL, NULL);
        if (c >= 0) {
            if (client >= 0) close(client);
            client = c;
            fcntl(client, F_SETFL, O_NONBLOCK);
            setsockopt(client, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
            in_head = in_tail = 0;
        }
        if (client >= 0 && in_tail - in_head < sizeof inbuf / 2) {
            ssize_t n = recv(client, inbuf + (in_tail % sizeof inbuf), 64, 0);
            if (n > 0) in_tail += n;
            else if (n == 0 || (errno != EAGAIN && errno != EWOULDBLOCK)) { close(client); client = -1; }
        }
        while (xon && in_head < in_tail)
            avr_raise_irq(in, inbuf[(in_head++) % sizeof inbuf]);
        if (in_head == in_tail) in_head = in_tail = 0;
        /* pace to real time: firmware timers and the baud rate then mean what they say */
        double ahead = (double)avr->cycle / avr->frequency - (now() - start);
        if (ahead > 0.002) usleep((useconds_t)(ahead * 1e6));
    }
}
