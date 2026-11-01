/* SN Systems ProDG libsn: stdio system-call stubs (dummy.c). fd 1/2 go to the UART, everything else
 * to the host file server (PC* calls). GCC 2.95 -O2. */

extern void InitializeUART(int baud);
extern int WriteUARTN(const void *buf, unsigned int len);
extern int PCwrite(int fd, const void *buf, unsigned int len);
extern int PCclose(int fd);
extern int PClseek(int fd, int ofs, int whence);
extern int PCread(int fd, void *buf, unsigned int len);

/* the original object's .data is 8-byte aligned (the DOL places it at ...9D0 after a 4-aligned end) */
asm(".section .data\n\t.balign 8\n\t.section .text");

struct stat_min {
	int st_dev;
	int st_mode;
};

// Serial output of the runtime: initialises the UART on the first call (InitializeUART(0)) and
// writes the bytes (what OSReport/printf text ends up as on the debug console).
int __sn_serialp(const void *buf, unsigned int len)
{
	static int first = 1;

	if (first) {
		first = 0;
		InitializeUART(0);
	}
	WriteUARTN(buf, len);
	return len;
}

static int sn_stdio_pad = 0; /* unnamed 4-byte .data word after first.183 */

// The stdio write syscall of the SN runtime: fd 1/2 (stdout/stderr, i.e. printf) go to the UART
// through __sn_serialp, fd 0 fails, any other fd is a host file (PCwrite).
int _write(int fd, const void *buf, unsigned int len)
{
	if (fd == 1 || fd == 2) {
		return __sn_serialp(buf, len);
	}
	if (fd == 0) {
		return -1;
	}
	return PCwrite(fd, buf, len);
}

// Alias of _write.
int write(int fd, const void *buf, unsigned int len)
{
	return _write(fd, buf, len);
}

// Closes a host file (PCclose).
int close(int fd)
{
	return PCclose(fd);
}

// Every fd reports as a character device (st_mode 0x2000) so newlib's stdio stays unbuffered-line.
int fstat(int fd, struct stat_min *st)
{
	st->st_mode = 0x2000;
	return 0;
}

// Seeks a host file (PClseek).
int lseek(int fd, int ofs, int whence)
{
	return PClseek(fd, ofs, whence);
}

// Reads a host file (PCread).
int read(int fd, void *buf, unsigned int len)
{
	return PCread(fd, buf, len);
}
