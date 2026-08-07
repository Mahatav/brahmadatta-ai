/* Escape decoding for entries carrying PKT_FLAG_ESCAPED.
 *
 * Rule under test: `\n` `\r` `\0` `\\` decode to one byte; `\xHH` inserts one
 * raw byte and is never re-interpreted afterwards; an unrecognised escape
 * yields the escaped character itself; a trailing backslash is a literal
 * backslash. Tab handling lives in test_tab_expansion.c.
 */

#include "packet_builder.h"
#include "test_util.h"

int main(void)
{
    pkt_builder b;
    pkt_config *cfg = NULL;

    /* Without the flag, backslashes are ordinary bytes. */
    pb_init(&b);
    pb_entry_str(&b, "path", 0, "C:\\\\logs");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_STR(cfg->entries[0].value, "C:\\\\logs");
    pkt_config_free(cfg);
    cfg = NULL;

    /* With the flag, the same bytes collapse to a single backslash. */
    pb_init(&b);
    pb_entry_str(&b, "path", PKT_FLAG_ESCAPED, "C:\\\\logs");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_STR(cfg->entries[0].value, "C:\\logs");
    CHECK_EQ_INT(cfg->entries[0].value_len, 7);
    pkt_config_free(cfg);
    cfg = NULL;

    /* Newline and carriage return. */
    pb_init(&b);
    pb_entry_str(&b, "banner", PKT_FLAG_ESCAPED, "one\\ntwo\\r");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_STR(cfg->entries[0].value, "one\ntwo\r");
    CHECK_EQ_INT(cfg->entries[0].value_len, 8);
    pkt_config_free(cfg);
    cfg = NULL;

    /* Hex escapes, including an embedded NUL that value_len still accounts for. */
    pb_init(&b);
    pb_entry_str(&b, "raw", PKT_FLAG_ESCAPED, "\\x41\\x00\\x42");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_INT(cfg->entries[0].value_len, 3);
    CHECK_EQ_MEM(cfg->entries[0].value, "A\0B", 3);
    pkt_config_free(cfg);
    cfg = NULL;

    /* `\0` is the short form of the same thing. */
    pb_init(&b);
    pb_entry_str(&b, "raw", PKT_FLAG_ESCAPED, "a\\0b");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_INT(cfg->entries[0].value_len, 3);
    CHECK_EQ_MEM(cfg->entries[0].value, "a\0b", 3);
    pkt_config_free(cfg);
    cfg = NULL;

    /* Malformed hex escapes stay literal rather than consuming the next bytes. */
    pb_init(&b);
    pb_entry_str(&b, "raw", PKT_FLAG_ESCAPED, "\\xZZ");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_STR(cfg->entries[0].value, "\\xZZ");
    CHECK_EQ_INT(cfg->entries[0].value_len, 4);
    pkt_config_free(cfg);
    cfg = NULL;

    /* A truncated hex escape at the very end of the value. */
    pb_init(&b);
    pb_entry_str(&b, "raw", PKT_FLAG_ESCAPED, "\\x4");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_STR(cfg->entries[0].value, "\\x4");
    pkt_config_free(cfg);
    cfg = NULL;

    /* Unknown escape yields the escaped character; trailing backslash is literal. */
    pb_init(&b);
    pb_entry_str(&b, "misc", PKT_FLAG_ESCAPED, "a\\qb\\");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_STR(cfg->entries[0].value, "aqb\\");
    CHECK_EQ_INT(cfg->entries[0].value_len, 4);
    pkt_config_free(cfg);

    TEST_REPORT("test_escapes");
}
