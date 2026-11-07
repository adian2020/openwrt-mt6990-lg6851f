// SPDX-License-Identifier: GPL-2.0-only
/* Send an SMS through the stock Quectel RIL API used by sample_sms. */

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>

enum {
	QL_SMS_FORMAT_GSM7 = 0,
	/* ql_ril_service 0x41c2b8 selects UCS2 for format 2 and passes the
	 * content to AT+EMGS as a hex string. Format 1 is binary, not UCS2. */
	QL_SMS_FORMAT_UCS2 = 2,
	QL_SMS_PHONE_SIZE = 256,
	QL_SMS_CONTENT_SIZE = 1440,
};

struct ql_sms_message {
	int32_t format;
	char phone_number[QL_SMS_PHONE_SIZE];
	int32_t content_length;
	uint8_t content[QL_SMS_CONTENT_SIZE];
};

extern int ql_sms_init(int sim_id);
extern int ql_sms_release(void);
extern int ql_sms_send_msg(struct ql_sms_message *message);

_Static_assert(sizeof(struct ql_sms_message) == 1704, "qlril SMS ABI size");
_Static_assert(offsetof(struct ql_sms_message, content_length) == 260,
	       "qlril SMS ABI length offset");
_Static_assert(offsetof(struct ql_sms_message, content) == 264,
	       "qlril SMS ABI content offset");

int main(int argc, char **argv)
{
	struct ql_sms_message message = { .format = QL_SMS_FORMAT_GSM7 };
	size_t number_len, content_len;
	int init_ret, send_ret, release_ret, lockfd;
	int ucs2 = argc == 4 && !strcmp(argv[1], "--ucs2");
	const char *number = ucs2 ? argv[2] : argc > 1 ? argv[1] : "";
	const char *content = ucs2 ? argv[3] : argc > 2 ? argv[2] : "";

	if (argc != 3 && !ucs2) {
		fprintf(stderr, "usage: %s NUMBER TEXT | --ucs2 NUMBER UTF16BE_HEX\n", argv[0]);
		return 2;
	}

	number_len = strlen(number);
	content_len = strlen(content);
	if (number_len - (number[0] == '+') < 3 || number_len - (number[0] == '+') > 20 ||
	    !content_len || content_len > (ucs2 ? 280 : 160) ||
	    (ucs2 && content_len % 4)) {
		fprintf(stderr, "invalid SMS number or content length\n");
		return 2;
	}

	for (size_t i = number[0] == '+' ? 1 : 0; i < number_len; i++)
		if (number[i] < '0' || number[i] > '9') return 2;
	memcpy(message.phone_number, number, number_len + 1);
	if (ucs2) {
		message.format = QL_SMS_FORMAT_UCS2;
		for (size_t i = 0; i < content_len; i++)
			if (!((content[i]>='0'&&content[i]<='9')||(content[i]>='a'&&content[i]<='f')||(content[i]>='A'&&content[i]<='F'))) return 2;
		memcpy(message.content, content, content_len);
		message.content_length = (int32_t)content_len;
	} else {
		for (size_t i=0; i<content_len; i++) if(content[i]<32 || content[i]>126) return 2;
		memcpy(message.content, content, content_len);
		message.content_length = (int32_t)content_len;
	}
	lockfd = open("/var/lock/lg6851f-sms-operation.lock", O_CREAT | O_RDWR | O_CLOEXEC, 0600);
	if (lockfd < 0 || flock(lockfd, LOCK_EX | LOCK_NB)) return 75;

	init_ret = ql_sms_init(0);
	if (init_ret) {
		fprintf(stderr, "ql_sms_init failed: 0x%08x\n", init_ret);
		return 3;
	}

	send_ret = ql_sms_send_msg(&message);
	release_ret = ql_sms_release();
	if (send_ret) {
		fprintf(stderr, "ql_sms_send_msg failed: 0x%08x\n", send_ret);
		return 4;
	}
	if (release_ret) {
		fprintf(stderr, "ql_sms_release failed: 0x%08x\n", release_ret);
		/* Submission already succeeded; reporting failure could resend it. */
	}

	puts("SMS submitted through official qlril API");
	return 0;
}
