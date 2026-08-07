/* Truncated packets are rejected rather than read past the end of the buffer. */

#include "packet_builder.h"
#include "test_util.h"

int main(void)
{
    pkt_builder b;
    pkt_config *cfg = NULL;

    /* Declares two entries, carries one. */
    pb_init(&b);
    pb_entry_str(&b, "mode", 0, "strict");
    pb_set_count(&b, 2);
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_ERR_TRUNCATED);
    CHECK(cfg == NULL);

    /* Entry header itself is cut short. */
    pb_init(&b);
    pb_entry_str(&b, "mode", 0, "strict");
    CHECK_EQ_INT(pkt_parse(b.buf, PKT_HEADER_LEN + 2, &cfg), PKT_ERR_TRUNCATED);
    CHECK(cfg == NULL);

    /* Name is cut short. */
    pb_init(&b);
    pb_entry_str(&b, "region", 0, "ap-south-1");
    CHECK_EQ_INT(pkt_parse(b.buf, PKT_HEADER_LEN + PKT_ENTRY_HDR + 3, &cfg),
                 PKT_ERR_TRUNCATED);
    CHECK(cfg == NULL);

    /* Value is cut short by a single byte. */
    pb_init(&b);
    pb_entry_str(&b, "region", 0, "ap-south-1");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len - 1, &cfg), PKT_ERR_TRUNCATED);
    CHECK(cfg == NULL);

    /* Declared value_len far past the end of the buffer. */
    pb_init(&b);
    pb_entry_str(&b, "mode", 0, "strict");
    b.buf[PKT_HEADER_LEN + 2] = 0xff;
    b.buf[PKT_HEADER_LEN + 3] = 0xff;
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_ERR_TRUNCATED);
    CHECK(cfg == NULL);

    /* The full packet is fine, so the cases above fail for the stated reason. */
    pb_init(&b);
    pb_entry_str(&b, "region", 0, "ap-south-1");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    pkt_config_free(cfg);

    TEST_REPORT("test_truncation");
}
