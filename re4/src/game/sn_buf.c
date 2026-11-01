/* SN ProDG libc: one zero-initialised static word is all that survived of this unit. */
static int sn_buf = 0;

/* Address of the surviving static word (keeps it in .sdata; never called by the game). */
int *_sn_buf_ptr(void)
{
    return &sn_buf;
}
