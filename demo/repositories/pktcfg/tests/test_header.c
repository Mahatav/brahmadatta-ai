/* Header validation: magic, version, reserved field, minimum length. */

#include "packet_builder.h"
#include "test_util.h"

int main(void)
{
    pkt_builder b;
    pkt_config *cfg = NULL;

    /* A header-only packet with zero entries is valid. */
    pb_init(&b);
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_INT(pkt_config_count(cfg), 0);
    pkt_config_free(cfg);
    cfg = NULL;

    /* Wrong magic. */
    pb_init(&b);
    b.buf[1] = 'X';
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_ERR_BAD_MAGIC);
    CHECK(cfg == NULL);

    /* Unsupported version. */
    pb_init(&b);
    b.buf[4] = 7;
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_ERR_BAD_VERSION);
    CHECK(cfg == NULL);

    /* Reserved field must be zero. */
    pb_init(&b);
    b.buf[7] = 0x80;
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_ERR_BAD_RESERVED);
    CHECK(cfg == NULL);

    /* Anything shorter than the header is truncated, including empty input. */
    pb_init(&b);
    CHECK_EQ_INT(pkt_parse(b.buf, PKT_HEADER_LEN - 1, &cfg), PKT_ERR_TRUNCATED);
    CHECK_EQ_INT(pkt_parse(b.buf, 0, &cfg), PKT_ERR_TRUNCATED);
    CHECK_EQ_INT(pkt_parse(NULL, 32, &cfg), PKT_ERR_TRUNCATED);

    /* Status strings are wired up for the evidence report. */
    CHECK_EQ_STR(pkt_status_str(PKT_OK), "ok");
    CHECK_EQ_STR(pkt_status_str(PKT_ERR_BAD_MAGIC), "bad magic");

    TEST_REPORT("test_header");
}
