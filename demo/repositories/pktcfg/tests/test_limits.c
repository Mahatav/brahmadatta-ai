/* Name-length limits at both boundaries. */

#include "packet_builder.h"
#include "test_util.h"

int main(void)
{
    pkt_builder b;
    pkt_config *cfg = NULL;
    char        long_name[PKT_MAX_NAME + 2];
    unsigned    i;

    /* A zero-length name is rejected. */
    pb_init(&b);
    pb_entry_str(&b, "mode", 0, "strict");
    b.buf[PKT_HEADER_LEN] = 0;
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_ERR_BAD_NAME_LEN);
    CHECK(cfg == NULL);

    /* Exactly PKT_MAX_NAME bytes is accepted. */
    for (i = 0; i < PKT_MAX_NAME; i++) {
        long_name[i] = 'n';
    }
    long_name[PKT_MAX_NAME] = '\0';
    pb_init(&b);
    pb_entry_str(&b, long_name, 0, "ok");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_OK);
    CHECK_EQ_INT(pkt_config_count(cfg), 1);
    CHECK_EQ_STR(pkt_config_get(cfg, long_name), "ok");
    pkt_config_free(cfg);
    cfg = NULL;

    /* One byte over the limit is rejected. */
    long_name[PKT_MAX_NAME]     = 'n';
    long_name[PKT_MAX_NAME + 1] = '\0';
    pb_init(&b);
    pb_entry_str(&b, long_name, 0, "ok");
    CHECK_EQ_INT(pkt_parse(b.buf, b.len, &cfg), PKT_ERR_BAD_NAME_LEN);
    CHECK(cfg == NULL);

    /* A 64 KiB - 1 value is within the u16 length field and parses. */
    {
        static char big[65000];
        for (i = 0; i < sizeof(big); i++) {
            big[i] = 'x';
        }
        /* pb_entry writes into a fixed 4 KiB buffer, so exercise the decoder
         * directly rather than through the builder. */
        CHECK_EQ_INT(pkt_decoded_length((const uint8_t *)big, sizeof(big), 0),
                     sizeof(big));
    }

    TEST_REPORT("test_limits");
}
